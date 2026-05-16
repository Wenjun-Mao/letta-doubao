from __future__ import annotations

import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .artifacts import ArtifactWriter, build_summary, print_summary, write_summary
from .client import AgentPlatformApiClient
from .config import ChatMemoryEvalConfig, router_model_key_from_agent_handle, router_v1_base_url
from .fixtures import ConversationFixture, load_fixture
from .judge import judge_round
from .scoring import (
    DEFAULT_FORBIDDEN_REPLY_SUBSTRINGS,
    assistant_replies,
    deterministic_round_score,
    memory_tool_calls,
    tool_calls,
)


def run_evaluation(config: ChatMemoryEvalConfig, *, now: datetime | None = None) -> dict[str, Any]:
    run_timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    run_id = f"chat-memory-eval-{run_timestamp}-{uuid4().hex[:8]}"
    csv_path = config.output_dir / f"chat_memory_eval_{run_timestamp}.csv"
    jsonl_path = config.output_dir / f"chat_memory_eval_{run_timestamp}.jsonl"
    summary_path = config.output_dir / f"chat_memory_eval_{run_timestamp}_summary.json"
    config.output_dir.mkdir(parents=True, exist_ok=True)

    fixture = load_fixture(config.fixtures_dir, config.fixture_key)
    rows: list[dict[str, Any]] = []
    client_timeout = max(config.timeout_seconds + 60, 90)
    with AgentPlatformApiClient(
        base_url=config.api_base_url,
        timeout_seconds=client_timeout,
        retry_count=config.api_retry_count,
    ) as api:
        validate_chat_options(api.options(), config)
        total = config.rounds
        print(f"[INFO] Running {total} chat-memory rounds with {len(fixture.turns)} turns each.")
        print(f"[INFO] Streaming CSV to {csv_path}")
        with ArtifactWriter(csv_path=csv_path, jsonl_path=jsonl_path) as writer:
            for round_index in range(1, total + 1):
                print(f"[{round_index}/{total}] starting")
                row, raw = run_round(api=api, config=config, fixture=fixture, run_id=run_id, round_index=round_index)
                rows.append(row)
                writer.write_round(row, raw)
                print(
                    f"[{round_index}/{total}] status={row['status']} pass={row['pass']} "
                    f"elapsed={row['elapsed_seconds']}s"
                )
                if config.stop_on_error and row["status"] == "error":
                    break

    summary = build_summary(
        run_id=run_id,
        csv_path=csv_path,
        jsonl_path=jsonl_path,
        summary_path=summary_path,
        rows=rows,
    )
    summary["config"] = _config_payload(config)
    summary["fixture"] = _fixture_payload(fixture)
    write_summary(summary_path, summary)
    print_summary(summary)
    return summary


def validate_chat_options(payload: dict[str, Any], config: ChatMemoryEvalConfig) -> None:
    models = _option_keys(payload.get("models", []))
    prompts = _option_keys(payload.get("prompts", []))
    personas = _option_keys(payload.get("personas", []))
    embeddings = _option_keys(payload.get("embeddings", []))
    if config.model not in models:
        raise ValueError(f"model '{config.model}' is not available from /api/v1/options?scenario=chat")
    if config.prompt_key not in prompts:
        raise ValueError(f"prompt_key '{config.prompt_key}' is not available from /api/v1/options?scenario=chat")
    if config.persona_key not in personas:
        raise ValueError(f"persona_key '{config.persona_key}' is not available from /api/v1/options?scenario=chat")
    if config.embedding and config.embedding not in embeddings:
        raise ValueError(f"embedding '{config.embedding}' is not available from /api/v1/options?scenario=chat")


def run_round(
    *,
    api: AgentPlatformApiClient,
    config: ChatMemoryEvalConfig,
    fixture: ConversationFixture,
    run_id: str,
    round_index: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.time()
    agent_id = ""
    archived = False
    purged = False
    row: dict[str, Any]
    raw: dict[str, Any]
    try:
        created = api.create_agent(_create_agent_payload(config, round_index))
        agent_id = str(created.get("id", "") or "")
        if not agent_id:
            raise RuntimeError("Agent creation did not return id")

        turn_records, assistant_texts, initial_human_memory = _run_turns(
            api=api,
            agent_id=agent_id,
            config=config,
            fixture=fixture,
        )
        state = api.persistent_state(agent_id)
        final_human_memory = _human_memory_from_state(state) or _last_human_memory(turn_records)
        score = deterministic_round_score(
            assistant_texts=assistant_texts,
            initial_human_memory=initial_human_memory,
            final_human_memory=final_human_memory,
            expected_facts=fixture.expected_facts,
            forbidden_reply_substrings=_forbidden_substrings(fixture),
        )
        judge_payload = _run_judge_if_enabled(
            config=config,
            fixture=fixture,
            turn_records=turn_records,
            final_human_memory=final_human_memory,
        )

        row = _round_row(
            run_id=run_id,
            round_index=round_index,
            config=config,
            fixture=fixture,
            status="ok",
            passed=bool(score["pass"]),
            elapsed_seconds=time.time() - started,
            agent_id=agent_id,
            archived=False,
            purged=False,
            score=score,
            judge_payload=judge_payload,
            turn_records=turn_records,
            error="",
        )
        raw = {
            **row,
            "turns": turn_records,
            "initial_human_memory": initial_human_memory,
            "final_human_memory": final_human_memory,
            "deterministic_score": score,
            "judge": judge_payload,
            "persistent_state": state,
        }
    except Exception as exc:
        row = _error_row(run_id, round_index, config, fixture, time.time() - started, agent_id, str(exc))
        raw = {**row, "error": str(exc)}
    finally:
        if agent_id and not config.keep_agents:
            try:
                api.archive_agent(agent_id)
                archived = True
                api.purge_agent(agent_id)
                purged = True
            except Exception as exc:
                print(f"[WARN] Failed to archive/purge eval agent {agent_id}: {exc}")
            row["archived"] = archived
            row["purged"] = purged
            raw["archived"] = archived
            raw["purged"] = purged
    return row, raw


def _run_turns(
    *,
    api: AgentPlatformApiClient,
    agent_id: str,
    config: ChatMemoryEvalConfig,
    fixture: ConversationFixture,
) -> tuple[list[dict[str, Any]], list[str], str]:
    turn_records: list[dict[str, Any]] = []
    all_assistant_texts: list[str] = []
    initial_human_memory = ""
    for turn_index, user_input in enumerate(fixture.turns, 1):
        turn_started = time.time()
        result = api.chat(
            agent_id=agent_id,
            message=user_input,
            timeout_seconds=config.timeout_seconds,
            retry_count=config.retry_count,
        )
        sequence = result.get("sequence", [])
        if not isinstance(sequence, list):
            sequence = []
        memory_diff = result.get("memory_diff", {})
        if not isinstance(memory_diff, dict):
            memory_diff = {}
        old_human = str((memory_diff.get("old") or {}).get("human", "") if isinstance(memory_diff.get("old"), dict) else "")
        new_human = str((memory_diff.get("new") or {}).get("human", "") if isinstance(memory_diff.get("new"), dict) else "")
        if turn_index == 1:
            initial_human_memory = old_human
        replies = assistant_replies(sequence)
        all_assistant_texts.extend(replies)
        record = {
            "turn_index": turn_index,
            "user_input": user_input,
            "assistant_replies": replies,
            "elapsed_seconds": round(time.time() - turn_started, 3),
            "memory_changed_this_turn": old_human.strip() != new_human.strip(),
            "human_memory_before_turn": old_human,
            "human_memory_after_turn": new_human,
            "tool_calls": tool_calls(sequence),
            "memory_tool_calls": memory_tool_calls(sequence),
            "sequence": sequence,
        }
        turn_records.append(record)
    return turn_records, all_assistant_texts, initial_human_memory


def _run_judge_if_enabled(
    *,
    config: ChatMemoryEvalConfig,
    fixture: ConversationFixture,
    turn_records: list[dict[str, Any]],
    final_human_memory: str,
) -> dict[str, Any]:
    if not config.judge_enabled:
        return {"ok": False, "skipped": True}
    model_key = config.judge_model_key or router_model_key_from_agent_handle(config.model)
    return judge_round(
        router_v1_base_url=router_v1_base_url(config),
        router_api_key=config.model_router_api_key,
        model_key=model_key,
        fixture=_fixture_payload(fixture),
        turn_records=turn_records,
        final_human_memory=final_human_memory,
        timeout_seconds=config.judge_timeout_seconds,
    )


def _create_agent_payload(config: ChatMemoryEvalConfig, round_index: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "scenario": "chat",
        "name": f"chat-memory-eval-r{round_index}-{int(time.time())}",
        "model": config.model,
        "prompt_key": config.prompt_key,
        "persona_key": config.persona_key,
    }
    if config.embedding:
        payload["embedding"] = config.embedding
    return payload


def _round_row(**kwargs: Any) -> dict[str, Any]:
    score = kwargs["score"]
    judge_payload = kwargs["judge_payload"]
    turn_records = kwargs["turn_records"]
    memory_tool_count = sum(len(item.get("memory_tool_calls", [])) for item in turn_records)
    tool_count = sum(len(item.get("tool_calls", [])) for item in turn_records)
    return {
        "run_id": kwargs["run_id"],
        "round": kwargs["round_index"],
        "status": kwargs["status"],
        "pass": kwargs["passed"],
        "elapsed_seconds": round(float(kwargs["elapsed_seconds"]), 3),
        "model": kwargs["config"].model,
        "prompt_key": kwargs["config"].prompt_key,
        "persona_key": kwargs["config"].persona_key,
        "embedding": kwargs["config"].embedding,
        "fixture_key": kwargs["fixture"].key,
        "turn_count": len(turn_records),
        "assistant_reply_count": sum(len(item.get("assistant_replies", [])) for item in turn_records),
        "forbidden_hit_count": int(score.get("forbidden_hit_count", 0)),
        "human_memory_changed": bool(score.get("human_memory_changed", False)),
        "expected_facts_passed": bool(score.get("expected_facts_passed", False)),
        "missing_expected_facts": ",".join(score.get("missing_expected_facts", [])),
        "memory_tool_call_count": memory_tool_count,
        "total_tool_call_count": tool_count,
        "judge_enabled": kwargs["config"].judge_enabled,
        "judge_ok": bool(judge_payload.get("ok", False)),
        "judge_pass": judge_payload.get("pass", ""),
        "judge_score": judge_payload.get("score", ""),
        "agent_id": kwargs["agent_id"],
        "archived": kwargs["archived"],
        "purged": kwargs["purged"],
        "error": kwargs["error"],
    }


def _error_row(
    run_id: str,
    round_index: int,
    config: ChatMemoryEvalConfig,
    fixture: ConversationFixture,
    elapsed_seconds: float,
    agent_id: str,
    error: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "round": round_index,
        "status": "error",
        "pass": False,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "model": config.model,
        "prompt_key": config.prompt_key,
        "persona_key": config.persona_key,
        "embedding": config.embedding,
        "fixture_key": fixture.key,
        "turn_count": len(fixture.turns),
        "assistant_reply_count": 0,
        "forbidden_hit_count": 0,
        "human_memory_changed": False,
        "expected_facts_passed": False,
        "missing_expected_facts": "",
        "memory_tool_call_count": 0,
        "total_tool_call_count": 0,
        "judge_enabled": config.judge_enabled,
        "judge_ok": False,
        "judge_pass": "",
        "judge_score": "",
        "agent_id": agent_id,
        "archived": False,
        "purged": False,
        "error": error,
    }


def _option_keys(items: object) -> set[str]:
    if not isinstance(items, list):
        return set()
    return {str(item.get("key", "") or "").strip() for item in items if isinstance(item, dict)}


def _human_memory_from_state(state: dict[str, Any]) -> str:
    blocks = state.get("memory_blocks", [])
    if not isinstance(blocks, list):
        return ""
    for block in blocks:
        if isinstance(block, dict) and str(block.get("label", "") or "") == "human":
            return str(block.get("value", "") or "")
    return ""


def _last_human_memory(turn_records: list[dict[str, Any]]) -> str:
    for item in reversed(turn_records):
        value = str(item.get("human_memory_after_turn", "") or "")
        if value:
            return value
    return ""


def _forbidden_substrings(fixture: ConversationFixture) -> tuple[str, ...]:
    if fixture.forbidden_reply_substrings:
        return fixture.forbidden_reply_substrings
    return DEFAULT_FORBIDDEN_REPLY_SUBSTRINGS


def _fixture_payload(fixture: ConversationFixture) -> dict[str, Any]:
    return {
        "key": fixture.key,
        "description": fixture.description,
        "turns": list(fixture.turns),
        "expected_facts": [asdict(item) for item in fixture.expected_facts],
        "forbidden_reply_substrings": list(_forbidden_substrings(fixture)),
    }


def _config_payload(config: ChatMemoryEvalConfig) -> dict[str, Any]:
    payload = asdict(config)
    for key, value in list(payload.items()):
        if isinstance(value, Path):
            payload[key] = str(value)
    if payload.get("model_router_api_key"):
        payload["model_router_api_key"] = "***"
    return payload
