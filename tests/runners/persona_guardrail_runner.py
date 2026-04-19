from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from letta_client import Letta
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from prompts.persona import HUMAN_TEMPLATE, PERSONAS
from prompts.system_prompts import (
    CHAT_V20260418_PROMPT,
)
from tests.shared.config_defaults import (
    DEFAULT_CLIENT_TIMEOUT_SECONDS,
    DEFAULT_CONTEXT_WINDOW_LIMIT,
    DEFAULT_EMBEDDING_HANDLE,
    DEFAULT_FORBIDDEN_REPLY_SUBSTRINGS,
    DEFAULT_LETTA_BASE_URL,
    DEFAULT_PROMPT_KEY,
    DEFAULT_TIMEZONE,
    RUN_INDEX_CSV,
    RUN_INDEX_FIELDS,
    RUN_INDEX_JSONL,
)
from utils.message_parser import chat, get_agent_memory_dict

PROMPT_MAP: dict[str, str] = {
    "chat_v20260418": CHAT_V20260418_PROMPT,
}


def _safe_name(value: str) -> str:
    lowered = value.lower().strip()
    lowered = re.sub(r"[^a-z0-9_-]+", "_", lowered)
    lowered = re.sub(r"_+", "_", lowered)
    return lowered.strip("_") or "test"


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            text = getattr(item, "text", None)
            if isinstance(text, str) and text:
                parts.append(text)
        if parts:
            return " ".join(parts)
        return str(value)
    return str(value)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _fetch_user_turns_from_agent(client: Letta, source_agent_id: str) -> list[str]:
    turns: list[str] = []
    messages = list(client.agents.messages.list(agent_id=source_agent_id))
    for msg in messages:
        if getattr(msg, "message_type", "") != "user_message":
            continue
        text = _as_text(getattr(msg, "content", "")).strip()
        if text:
            turns.append(text)
    return turns


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _create_agent(client: Letta, create_args: dict[str, Any]):
    return client.agents.create(**create_args)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _delete_agent(client: Letta, agent_id: str) -> None:
    client.agents.delete(agent_id=agent_id)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=12),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _chat_with_retry(client: Letta, agent_id: str, user_input: str) -> dict[str, Any]:
    return chat(client, agent_id, input=user_input)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"Config must be a JSON object: {path}")
    return payload


def _resolve_turns(config_path: Path, config: dict[str, Any], client: Letta) -> list[str]:
    raw_turns = config.get("turns", [])
    if raw_turns:
        if not isinstance(raw_turns, list):
            raise ValueError(f"turns must be a list in {config_path}")
        return [str(turn).strip() for turn in raw_turns if str(turn).strip()]

    turns_file = config.get("turns_file")
    if turns_file:
        turns_path = (config_path.parent / str(turns_file)).resolve()
        payload = _load_json(turns_path)
        file_turns = payload.get("turns", [])
        if not isinstance(file_turns, list):
            raise ValueError(f"turns_file does not contain a 'turns' list: {turns_path}")
        return [str(turn).strip() for turn in file_turns if str(turn).strip()]

    source_agent_id = str(config.get("source_agent_id", "")).strip()
    if source_agent_id:
        return _fetch_user_turns_from_agent(client, source_agent_id)

    raise ValueError(f"No turns provided in {config_path}. Use turns, turns_file, or source_agent_id.")


def _forbidden_hits(text: str, forbidden_substrings: list[str]) -> list[str]:
    lowered = text.lower()
    return [needle for needle in forbidden_substrings if needle.lower() in lowered]


def _extract_last_assistant_reply(sequence: list[dict[str, Any]]) -> str:
    assistant_contents = [
        str(step.get("content", ""))
        for step in sequence
        if step.get("type") == "assistant" and str(step.get("content", "")).strip()
    ]
    if not assistant_contents:
        return ""
    return assistant_contents[-1]


def _extract_tool_calls(sequence: list[dict[str, Any]]) -> list[str]:
    names = [str(step.get("name", "")).strip() for step in sequence if step.get("type") == "tool_call"]
    return [name for name in names if name]


def _normalize_check_settings(config_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    raw_checks = config.get("checks")
    checks: dict[str, Any] = raw_checks if isinstance(raw_checks, dict) else {}

    forbidden_substrings = checks.get("forbidden_reply_substrings") or DEFAULT_FORBIDDEN_REPLY_SUBSTRINGS
    if not isinstance(forbidden_substrings, list):
        raise ValueError(f"forbidden_reply_substrings must be a list in {config_path}")

    return {
        "forbidden_substrings": [str(item) for item in forbidden_substrings if str(item).strip()],
        "strict_forbidden": bool(checks.get("strict_forbidden", True)),
        "require_human_memory_change": bool(checks.get("require_human_memory_change", False)),
    }


def _build_create_args(
    *,
    config: dict[str, Any],
    test_name: str,
    prompt_key: str,
    persona_key: str,
    model_handle: str,
    human_block_label: str,
    embedding_override: str | None,
) -> tuple[dict[str, Any], str | None, str]:
    embedding_handle = str(config.get("embedding", "")).strip() or DEFAULT_EMBEDDING_HANDLE
    if embedding_override:
        embedding_handle = embedding_override

    agent_name = str(config.get("agent_name") or f"suite-{_safe_name(test_name)}-{int(time.time())}")

    create_args: dict[str, Any] = {
        "name": agent_name,
        "system": PROMPT_MAP[prompt_key],
        "model": model_handle,
        "timezone": str(config.get("timezone", DEFAULT_TIMEZONE)),
        "context_window_limit": int(config.get("context_window_limit", DEFAULT_CONTEXT_WINDOW_LIMIT)),
        "memory_blocks": [
            {
                "label": "persona",
                "value": str(config.get("persona_value", PERSONAS[persona_key])),
            },
            {
                "label": human_block_label,
                "value": str(config.get("human_template", HUMAN_TEMPLATE)),
            },
        ],
    }

    if embedding_handle:
        create_args["embedding"] = embedding_handle

    return create_args, embedding_handle, agent_name


def _run_turn_sequence(
    *,
    client: Letta,
    agent_id: str,
    turns: list[str],
    human_block_label: str,
    forbidden_substrings: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    turn_records: list[dict[str, Any]] = []
    all_forbidden_hits: list[dict[str, Any]] = []

    for index, user_turn in enumerate(turns, 1):
        turn_start = time.time()
        chat_result = _chat_with_retry(client, agent_id, user_turn)
        sequence = chat_result.get("sequence", [])
        assistant_reply = _extract_last_assistant_reply(sequence)
        turn_hits = _forbidden_hits(assistant_reply, forbidden_substrings)

        if turn_hits:
            all_forbidden_hits.append(
                {
                    "turn_index": index,
                    "user_input": user_turn,
                    "assistant_reply": assistant_reply,
                    "hits": turn_hits,
                }
            )

        old_human = str(chat_result.get("memory_diff", {}).get("old", {}).get(human_block_label, ""))
        new_human = str(chat_result.get("memory_diff", {}).get("new", {}).get(human_block_label, ""))

        turn_records.append(
            {
                "turn_index": index,
                "user_input": user_turn,
                "assistant_reply": assistant_reply,
                "total_steps": int(chat_result.get("total_steps", 0)),
                "tool_calls": _extract_tool_calls(sequence),
                "human_memory_before_turn": old_human,
                "human_memory_after_turn": new_human,
                "memory_changed_this_turn": old_human != new_human,
                "forbidden_hits": turn_hits,
                "duration_seconds": round(time.time() - turn_start, 3),
                "sequence": sequence,
            }
        )

    return turn_records, all_forbidden_hits


def _write_result_artifact(output_dir: Path, test_name: str, result: dict[str, Any]) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{_safe_name(test_name)}.json"
    output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(output_file)


def _append_run_index(output_root: Path, row: dict[str, Any]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    csv_path = output_root / RUN_INDEX_CSV
    jsonl_path = output_root / RUN_INDEX_JSONL

    row_for_storage = {field: row.get(field, "") for field in RUN_INDEX_FIELDS}

    csv_exists = csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=RUN_INDEX_FIELDS)
        if not csv_exists:
            writer.writeheader()
        writer.writerow(row_for_storage)

    with jsonl_path.open("a", encoding="utf-8") as jsonl_file:
        jsonl_file.write(json.dumps(row_for_storage, ensure_ascii=False) + "\n")


def _discover_config_files(config_inputs: list[str], project_root: Path) -> list[Path]:
    if not config_inputs:
        default_dir = project_root / "tests" / "configs" / "suites"
        if not default_dir.exists():
            return []
        return sorted(default_dir.glob("*.json"))

    files: list[Path] = []
    for raw in config_inputs:
        path = Path(raw)
        if not path.is_absolute():
            path = (project_root / path).resolve()
        if path.is_dir():
            files.extend(sorted(path.glob("*.json")))
            continue
        if path.is_file():
            files.append(path)
            continue
        raise FileNotFoundError(f"Config path does not exist: {raw}")
    return files


def _run_single_config(
    *,
    config_path: Path,
    client: Letta,
    output_dir: Path,
    keep_agent_arg: bool,
    embedding_override: str | None,
    model_override: str | None,
) -> dict[str, Any]:
    """
    High-level map:
    1) Load and validate configuration knobs.
    2) Create isolated test agent and snapshot start memory.
    3) Replay all user turns and capture per-turn evidence.
    4) Evaluate strict expectations and compile final payload.
    5) Persist artifact and return structured result.
    """
    # Step 1: Load + validate config essentials.
    config = _load_json(config_path)
    test_name = str(config.get("name") or config_path.stem)

    prompt_key = str(config.get("prompt_key", DEFAULT_PROMPT_KEY))
    if prompt_key not in PROMPT_MAP:
        raise ValueError(f"Unknown prompt_key '{prompt_key}' in {config_path}")

    persona_key = str(config.get("persona_key", "chat_linxiaotang"))
    if persona_key not in PERSONAS:
        raise ValueError(f"Unknown persona_key '{persona_key}' in {config_path}")

    model_handle = str(config.get("model", "")).strip()
    if model_override:
        model_handle = model_override
    if not model_handle:
        raise ValueError(f"Missing model in {config_path}")

    human_block_label = str(config.get("human_block_label", "human"))
    turns = _resolve_turns(config_path, config, client)
    if not turns:
        raise ValueError(f"No user turns resolved for {config_path}")

    checks = _normalize_check_settings(config_path, config)
    forbidden_substrings = checks["forbidden_substrings"]
    strict_forbidden = bool(checks["strict_forbidden"])
    require_human_memory_change = bool(checks["require_human_memory_change"])

    create_args, embedding_handle, agent_name = _build_create_args(
        config=config,
        test_name=test_name,
        prompt_key=prompt_key,
        persona_key=persona_key,
        model_handle=model_handle,
        human_block_label=human_block_label,
        embedding_override=embedding_override,
    )

    run_started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    run_started_ts = time.time()
    agent_id: str | None = None

    try:
        # Step 2: Create isolated agent + capture starting memory.
        agent = _create_agent(client, create_args)
        agent_id = str(getattr(agent, "id", ""))

        memory_before_map = get_agent_memory_dict(client, agent_id)
        human_before = str(memory_before_map.get(human_block_label, ""))

        # Step 3: Replay turns and collect per-turn timings/replies/memory transitions.
        turn_records, all_forbidden_hits = _run_turn_sequence(
            client=client,
            agent_id=agent_id,
            turns=turns,
            human_block_label=human_block_label,
            forbidden_substrings=forbidden_substrings,
        )

        # Step 4: Build final evaluation and result payload.
        memory_after_map = get_agent_memory_dict(client, agent_id)
        human_after = str(memory_after_map.get(human_block_label, ""))

        memory_changed = human_before != human_after
        has_forbidden = len(all_forbidden_hits) > 0

        passed = True
        if strict_forbidden and has_forbidden:
            passed = False
        if require_human_memory_change and not memory_changed:
            passed = False

        assistant_replies = [record["assistant_reply"] for record in turn_records]

        result: dict[str, Any] = {
            "test_name": test_name,
            "config_file": str(config_path),
            "run_started_at": run_started_at,
            "run_finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "duration_seconds": round(time.time() - run_started_ts, 3),
            "agent": {
                "id": agent_id,
                "name": agent_name,
                "model": model_handle,
                "embedding": embedding_handle,
                "prompt_key": prompt_key,
                "persona_key": persona_key,
            },
            "inputs": turns,
            "outputs": {
                "assistant_replies": assistant_replies,
                "turns": turn_records,
                "human_memory_before": human_before,
                "human_memory_after": human_after,
                "human_memory_changed": memory_changed,
            },
            "evaluation": {
                "pass": passed,
                "strict_forbidden": strict_forbidden,
                "require_human_memory_change": require_human_memory_change,
                "forbidden_reply_substrings": forbidden_substrings,
                "forbidden_hits": all_forbidden_hits,
            },
        }

        # Step 5: Persist artifact for this config.
        result["output_file"] = _write_result_artifact(output_dir, test_name, result)
        return result
    finally:
        keep_agent = bool(config.get("keep_agent", False)) or keep_agent_arg
        if agent_id and not keep_agent:
            try:
                _delete_agent(client, agent_id)
            except Exception as exc:
                print(f"[WARN] Failed to delete test agent {agent_id}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run config-driven Letta conversation suites.")
    parser.add_argument(
        "--config",
        action="append",
        default=[],
        help="Config file or directory. Can be used multiple times. Defaults to tests/configs/suites/*.json",
    )
    parser.add_argument(
        "--output-dir",
        default="tests/outputs/persona_guardrail",
        help="Directory where run artifacts are written.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_LETTA_BASE_URL,
        help="Letta API base URL.",
    )
    parser.add_argument(
        "--client-timeout",
        type=float,
        default=DEFAULT_CLIENT_TIMEOUT_SECONDS,
        help="HTTP timeout (seconds) for Letta client requests.",
    )
    parser.add_argument(
        "--keep-agent",
        action="store_true",
        help="Do not delete test agents after each run.",
    )
    parser.add_argument(
        "--embedding",
        default="",
        help="Override embedding handle for all configs in this run.",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Override model handle for all configs in this run.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[2]
    config_files = _discover_config_files(args.config, project_root)
    if not config_files:
        print("No config files found. Provide --config path(s) or add tests/configs/suites/*.json")
        return 1

    run_tag = time.strftime("%Y%m%d_%H%M%S")
    run_output_dir = (project_root / args.output_dir / run_tag).resolve()
    run_output_dir.mkdir(parents=True, exist_ok=True)

    client = Letta(base_url=args.base_url, timeout=args.client_timeout)

    summary: dict[str, Any] = {
        "run_tag": run_tag,
        "letta_base_url": args.base_url,
        "client_timeout": args.client_timeout,
        "embedding_override": args.embedding or None,
        "model_override": args.model or None,
        "config_count": len(config_files),
        "results": [],
    }
    run_started_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    print(f"Running {len(config_files)} config(s) -> {run_output_dir}")
    for config_path in config_files:
        print(f"\n=== Running {config_path.name} ===")
        try:
            result = _run_single_config(
                config_path=config_path,
                client=client,
                output_dir=run_output_dir,
                keep_agent_arg=args.keep_agent,
                embedding_override=(args.embedding.strip() or None),
                model_override=(args.model.strip() or None),
            )
            summary["results"].append(
                {
                    "test_name": result["test_name"],
                    "config_file": str(config_path),
                    "model": result["agent"]["model"],
                    "embedding": result["agent"]["embedding"],
                    "prompt_key": result["agent"]["prompt_key"],
                    "pass": result["evaluation"]["pass"],
                    "output_file": result["output_file"],
                    "forbidden_hits": len(result["evaluation"]["forbidden_hits"]),
                    "human_memory_changed": result["outputs"]["human_memory_changed"],
                    "duration_seconds": result["duration_seconds"],
                }
            )
            print(f"PASS={result['evaluation']['pass']} output={result['output_file']}")
        except Exception as exc:
            summary["results"].append(
                {
                    "test_name": config_path.stem,
                    "config_file": str(config_path),
                    "model": args.model.strip() or "",
                    "embedding": args.embedding.strip() or DEFAULT_EMBEDDING_HANDLE,
                    "prompt_key": "",
                    "pass": False,
                    "error": str(exc),
                    "output_file": "",
                    "forbidden_hits": 0,
                    "human_memory_changed": False,
                    "duration_seconds": 0,
                }
            )
            print(f"FAILED: {exc}")

    output_root = (project_root / args.output_dir).resolve()
    for item in summary["results"]:
        _append_run_index(
            output_root,
            {
                "run_tag": run_tag,
                "run_started_at": run_started_at,
                "test_name": item.get("test_name", ""),
                "config_file": item.get("config_file", ""),
                "model": item.get("model", ""),
                "embedding": item.get("embedding", ""),
                "prompt_key": item.get("prompt_key", ""),
                "pass": item.get("pass", False),
                "forbidden_hits": item.get("forbidden_hits", 0),
                "human_memory_changed": item.get("human_memory_changed", False),
                "duration_seconds": item.get("duration_seconds", 0),
                "output_file": item.get("output_file", ""),
                "error": item.get("error", ""),
            },
        )

    summary_file = run_output_dir / "summary.json"
    summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSummary written to: {summary_file}")

    failures = [item for item in summary["results"] if not item.get("pass")]
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
