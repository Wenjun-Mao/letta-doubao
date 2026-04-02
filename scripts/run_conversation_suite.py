from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from letta_client import Letta
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from prompts.persona import HUMAN_TEMPLATE, PERSONAS
from prompts.system_prompts import (
    AGGRESSIVE_MEMORY_PROMPT,
    CUSTOM_V1_PROMPT,
    MEMGPT_V2_CHAT_PROMPT,
    STRUCTURED_MEMORY_PROMPT,
    TOOLS_FIRST_PROMPT,
)
from utils.message_parser import chat, get_agent_memory_dict

PROMPT_MAP: dict[str, str] = {
    "custom_v1": CUSTOM_V1_PROMPT,
    "memgpt_v2_chat": MEMGPT_V2_CHAT_PROMPT,
    "aggressive_memory": AGGRESSIVE_MEMORY_PROMPT,
    "structured_memory": STRUCTURED_MEMORY_PROMPT,
    "tools_first": TOOLS_FIRST_PROMPT,
}

DEFAULT_FORBIDDEN_REPLY_SUBSTRINGS = [
    "我是ai",
    "我是一个ai",
    "作为ai",
    "语言模型",
    "大语言模型",
    "虚拟助手",
    "我是虚拟",
    "虚拟的",
    "机器人",
]


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
) -> dict[str, Any]:
    config = _load_json(config_path)
    test_name = str(config.get("name") or config_path.stem)

    prompt_key = str(config.get("prompt_key", "custom_v1"))
    if prompt_key not in PROMPT_MAP:
        raise ValueError(f"Unknown prompt_key '{prompt_key}' in {config_path}")

    persona_key = str(config.get("persona_key", "linxiaotang"))
    if persona_key not in PERSONAS:
        raise ValueError(f"Unknown persona_key '{persona_key}' in {config_path}")

    model_handle = str(config.get("model", "")).strip()
    if not model_handle:
        raise ValueError(f"Missing model in {config_path}")

    embedding_handle = str(config.get("embedding", "")).strip() or None
    if embedding_override:
        embedding_handle = embedding_override
    agent_name = str(config.get("agent_name") or f"suite-{_safe_name(test_name)}-{int(time.time())}")
    turns = _resolve_turns(config_path, config, client)
    if not turns:
        raise ValueError(f"No user turns resolved for {config_path}")

    raw_checks = config.get("checks")
    checks: dict[str, Any] = raw_checks if isinstance(raw_checks, dict) else {}
    forbidden_substrings = checks.get("forbidden_reply_substrings", DEFAULT_FORBIDDEN_REPLY_SUBSTRINGS)
    if not isinstance(forbidden_substrings, list):
        raise ValueError(f"forbidden_reply_substrings must be a list in {config_path}")
    forbidden_substrings = [str(item) for item in forbidden_substrings if str(item).strip()]
    strict_forbidden = bool(checks.get("strict_forbidden", True))
    require_human_memory_change = bool(checks.get("require_human_memory_change", False))
    human_block_label = str(config.get("human_block_label", "human"))

    create_args: dict[str, Any] = {
        "name": agent_name,
        "system": PROMPT_MAP[prompt_key],
        "model": model_handle,
        "timezone": str(config.get("timezone", "Asia/Shanghai")),
        "context_window_limit": int(config.get("context_window_limit", 16384)),
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

    run_started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    run_started_ts = time.time()
    agent_id: str | None = None

    turn_records: list[dict[str, Any]] = []
    all_forbidden_hits: list[dict[str, Any]] = []

    try:
        agent = _create_agent(client, create_args)
        agent_id = str(getattr(agent, "id", ""))

        memory_before_map = get_agent_memory_dict(client, agent_id)
        human_before = str(memory_before_map.get(human_block_label, ""))

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

        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{_safe_name(test_name)}.json"
        output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        result["output_file"] = str(output_file)
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
        default="tests/outputs",
        help="Directory where run artifacts are written.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("LETTA_BASE_URL", "http://localhost:8283"),
        help="Letta API base URL.",
    )
    parser.add_argument(
        "--client-timeout",
        type=float,
        default=300.0,
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
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
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
        "config_count": len(config_files),
        "results": [],
    }

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
            )
            summary["results"].append(
                {
                    "test_name": result["test_name"],
                    "pass": result["evaluation"]["pass"],
                    "output_file": result["output_file"],
                    "forbidden_hits": len(result["evaluation"]["forbidden_hits"]),
                    "human_memory_changed": result["outputs"]["human_memory_changed"],
                }
            )
            print(f"PASS={result['evaluation']['pass']} output={result['output_file']}")
        except Exception as exc:
            summary["results"].append(
                {
                    "test_name": config_path.stem,
                    "pass": False,
                    "error": str(exc),
                }
            )
            print(f"FAILED: {exc}")

    summary_file = run_output_dir / "summary.json"
    summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSummary written to: {summary_file}")

    failures = [item for item in summary["results"] if not item.get("pass")]
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
