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
from prompts.system_prompts import CHAT_V20260418_PROMPT
from tests.shared.config_defaults import (
    DEFAULT_CLIENT_TIMEOUT_SECONDS,
    DEFAULT_CONTEXT_WINDOW_LIMIT,
    DEFAULT_EMBEDDING_HANDLE,
    DEFAULT_FORBIDDEN_REPLY_SUBSTRINGS,
    DEFAULT_LETTA_BASE_URL,
    DEFAULT_PROMPT_KEY,
    DEFAULT_TEST_MODEL_HANDLE,
    DEFAULT_TIMEZONE,
)
from utils.message_parser import chat, get_agent_memory_dict

DEFAULT_TURNS = [
    "你好，我叫张伟",
]

RUN_INDEX_CSV = "run_index.csv"
RUN_INDEX_JSONL = "run_index.jsonl"
RUN_INDEX_FIELDS = [
    "run_tag",
    "run_started_at",
    "rounds_total",
    "rounds_passed",
    "rounds_failed",
    "failed_rounds",
    "pass_rate",
    "total_run_duration_seconds",
    "total_round_duration_seconds",
    "average_round_duration_seconds",
    "model",
    "embedding",
    "turns_count",
    "output_file",
    "error",
]


def _load_turns(project_root: Path, explicit_turns: list[str], turns_file: str) -> list[str]:
    if explicit_turns:
        cleaned = [turn.strip() for turn in explicit_turns if turn.strip()]
        if cleaned:
            return cleaned

    if turns_file.strip():
        path = Path(turns_file)
        if not path.is_absolute():
            path = (project_root / path).resolve()

        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            raw_turns = payload.get("turns", [])
        elif isinstance(payload, list):
            raw_turns = payload
        else:
            raise ValueError(f"Unsupported turns payload in {path}")

        if not isinstance(raw_turns, list):
            raise ValueError(f"turns must be a list in {path}")

        cleaned = [str(turn).strip() for turn in raw_turns if str(turn).strip()]
        if cleaned:
            return cleaned

    return list(DEFAULT_TURNS)


def _extract_last_assistant_reply(sequence: list[dict[str, Any]]) -> str:
    replies = [
        str(step.get("content", ""))
        for step in sequence
        if step.get("type") == "assistant" and str(step.get("content", "")).strip()
    ]
    if not replies:
        return ""
    return replies[-1]


def _extract_name_from_human(human_block_text: str) -> str:
    match = re.search(r"姓名\s*[:：]\s*([^\r\n]+)", human_block_text)
    if not match:
        return ""
    return match.group(1).strip()


def _forbidden_hits(text: str, forbidden_substrings: list[str]) -> list[str]:
    lowered = text.lower()
    return [needle for needle in forbidden_substrings if needle.lower() in lowered]


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


def _build_create_args(
    *,
    round_index: int,
    model_handle: str,
    timezone_name: str,
    context_window_limit: int,
    persona_key: str,
    human_block_label: str,
    human_template: str,
    embedding_handle: str,
) -> dict[str, Any]:
    return {
        "name": f"mem-update-r{round_index}-{int(time.time())}",
        "system": CHAT_V20260418_PROMPT,
        "model": model_handle,
        "timezone": timezone_name,
        "context_window_limit": context_window_limit,
        "memory_blocks": [
            {
                "label": "persona",
                "value": PERSONAS[persona_key],
            },
            {
                "label": human_block_label,
                "value": human_template,
            },
        ],
        "embedding": embedding_handle,
    }


def _run_single_round(
    *,
    client: Letta,
    args: argparse.Namespace,
    turns: list[str],
    round_index: int,
) -> dict[str, Any]:
    agent_id: str | None = None
    started = time.time()

    try:
        create_args = _build_create_args(
            round_index=round_index,
            model_handle=args.model,
            timezone_name=args.timezone,
            context_window_limit=args.context_window_limit,
            persona_key=args.persona_key,
            human_block_label=args.human_block_label,
            human_template=args.human_template,
            embedding_handle=args.embedding,
        )
        agent = _create_agent(client, create_args)
        agent_id = str(getattr(agent, "id", ""))

        memory_before = get_agent_memory_dict(client, agent_id)
        human_before = str(memory_before.get(args.human_block_label, ""))

        turn_records: list[dict[str, Any]] = []
        all_forbidden_hits: list[dict[str, Any]] = []

        for turn_index, user_turn in enumerate(turns, 1):
            turn_started = time.time()
            result = _chat_with_retry(client, agent_id, user_turn)
            sequence = result.get("sequence", [])
            assistant_reply = _extract_last_assistant_reply(sequence)
            hits = _forbidden_hits(assistant_reply, args.forbidden_reply_substrings)

            if hits:
                all_forbidden_hits.append(
                    {
                        "turn_index": turn_index,
                        "user_input": user_turn,
                        "assistant_reply": assistant_reply,
                        "hits": hits,
                    }
                )

            human_before_turn = str(result.get("memory_diff", {}).get("old", {}).get(args.human_block_label, ""))
            human_after_turn = str(result.get("memory_diff", {}).get("new", {}).get(args.human_block_label, ""))

            turn_records.append(
                {
                    "turn_index": turn_index,
                    "user_input": user_turn,
                    "assistant_reply": assistant_reply,
                    "memory_changed_this_turn": human_before_turn != human_after_turn,
                    "duration_seconds": round(time.time() - turn_started, 3),
                    "forbidden_hits": hits,
                    "sequence": sequence,
                }
            )

        memory_after = get_agent_memory_dict(client, agent_id)
        human_after = str(memory_after.get(args.human_block_label, ""))
        extracted_name = _extract_name_from_human(human_after)

        first_turn_changed = turn_records[0]["memory_changed_this_turn"] if turn_records else False
        memory_changed = human_before != human_after
        expected_name_recorded = bool(args.expected_name.strip()) and args.expected_name in human_after

        passed = True
        if args.require_first_turn_change and not first_turn_changed:
            passed = False
        if args.require_memory_change and not memory_changed:
            passed = False
        if args.require_expected_name and not expected_name_recorded:
            passed = False
        if args.strict_forbidden and all_forbidden_hits:
            passed = False

        return {
            "round": round_index,
            "agent_id": agent_id,
            "pass": passed,
            "duration_seconds": round(time.time() - started, 3),
            "turn_count": len(turns),
            "inputs": turns,
            "outputs": {
                "turns": turn_records,
                "human_memory_before": human_before,
                "human_memory_after": human_after,
                "human_memory_changed": memory_changed,
                "name_extracted": extracted_name,
                "expected_name_recorded": expected_name_recorded,
                "first_turn_memory_changed": first_turn_changed,
            },
            "evaluation": {
                "strict_forbidden": args.strict_forbidden,
                "require_first_turn_change": args.require_first_turn_change,
                "require_memory_change": args.require_memory_change,
                "require_expected_name": args.require_expected_name,
                "forbidden_hits": all_forbidden_hits,
            },
        }
    finally:
        if agent_id and not args.keep_agent:
            try:
                _delete_agent(client, agent_id)
            except Exception as exc:
                print(f"[WARN] Failed to delete test agent {agent_id}: {exc}")


def _run_round_with_retries(
    *,
    client: Letta,
    args: argparse.Namespace,
    turns: list[str],
    round_index: int,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    max_attempts = max(1, int(args.round_retries) + 1)
    last_result: dict[str, Any] | None = None

    for attempt in range(1, max_attempts + 1):
        result = _run_single_round(
            client=client,
            args=args,
            turns=turns,
            round_index=round_index,
        )
        last_result = result
        forbidden_hits_count = len(result.get("evaluation", {}).get("forbidden_hits", []))
        attempts.append(
            {
                "attempt": attempt,
                "pass": bool(result.get("pass")),
                "duration_seconds": float(result.get("duration_seconds", 0.0)),
                "forbidden_hits": forbidden_hits_count,
                "first_turn_memory_changed": bool(
                    result.get("outputs", {}).get("first_turn_memory_changed", False)
                ),
                "human_memory_changed": bool(result.get("outputs", {}).get("human_memory_changed", False)),
                "expected_name_recorded": bool(result.get("outputs", {}).get("expected_name_recorded", False)),
            }
        )

        result["attempt"] = attempt

        if result.get("pass"):
            if attempt > 1:
                result["recovered_after_retry"] = True
            result["attempts"] = attempts
            result["attempts_used"] = attempt
            return result

    if last_result is None:
        raise RuntimeError("No round attempt result was produced")

    last_result["attempt"] = max_attempts
    last_result["recovered_after_retry"] = False
    last_result["attempts"] = attempts
    last_result["attempts_used"] = max_attempts
    return last_result


def _write_summary(output_dir: Path, payload: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / "memory_update_summary.json"
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return file_path


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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run fresh-agent memory update rounds and verify name persistence.",
    )
    parser.add_argument("--rounds", type=int, default=10, help="How many fresh agents to run.")
    parser.add_argument("--model", default=DEFAULT_TEST_MODEL_HANDLE, help="Model handle.")
    parser.add_argument("--persona-key", default="chat_linxiaotang", help="Persona key in prompts/persona.py")
    parser.add_argument("--embedding", default=DEFAULT_EMBEDDING_HANDLE, help="Embedding handle.")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE, help="Agent timezone.")
    parser.add_argument(
        "--context-window-limit",
        type=int,
        default=DEFAULT_CONTEXT_WINDOW_LIMIT,
        help="Agent context window limit.",
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
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--output-dir",
        default="tests/outputs/memory_update",
        help="Output directory where run artifacts are written.",
    )
    parser.add_argument(
        "--turn",
        action="append",
        default=[],
        help="User turn text. Can be passed multiple times.",
    )
    parser.add_argument(
        "--turns-file",
        default="",
        help="JSON file containing turns list or {\"turns\": [...]} payload.",
    )
    parser.add_argument(
        "--expected-name",
        default="张伟",
        help="Expected user name that must appear in final human memory.",
    )
    parser.add_argument(
        "--human-block-label",
        default="human",
        help="Memory block label for user facts.",
    )
    parser.add_argument(
        "--human-template",
        default=HUMAN_TEMPLATE,
        help="Initial human memory template.",
    )
    parser.add_argument(
        "--require-first-turn-change",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require memory to mutate on the first turn.",
    )
    parser.add_argument(
        "--require-memory-change",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require final human memory to differ from initial memory.",
    )
    parser.add_argument(
        "--require-expected-name",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require expected name to appear in final human memory.",
    )
    parser.add_argument(
        "--strict-forbidden",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fail rounds where assistant replies contain forbidden self-disclosure text.",
    )
    parser.add_argument(
        "--forbidden-reply-substring",
        action="append",
        default=[],
        help="Additional forbidden substring. Can be passed multiple times.",
    )
    parser.add_argument(
        "--keep-agent",
        action="store_true",
        help="Keep agents after each round for manual inspection.",
    )
    parser.add_argument(
        "--round-retries",
        type=int,
        default=2,
        help="How many retries to allow per failed round.",
    )

    args = parser.parse_args()

    if args.rounds < 1:
        raise ValueError("--rounds must be >= 1")
    if args.round_retries < 0:
        raise ValueError("--round-retries must be >= 0")

    if args.persona_key not in PERSONAS:
        raise ValueError(f"Unknown persona key: {args.persona_key}")

    project_root = Path(__file__).resolve().parents[2]
    turns = _load_turns(project_root, args.turn, args.turns_file)

    forbidden = list(DEFAULT_FORBIDDEN_REPLY_SUBSTRINGS)
    forbidden.extend(item for item in args.forbidden_reply_substring if item.strip())
    args.forbidden_reply_substrings = forbidden

    run_tag = time.strftime("%Y%m%d_%H%M%S")
    output_root = (project_root / args.output_dir).resolve()
    run_output_dir = (output_root / run_tag).resolve()

    client = Letta(base_url=args.base_url, timeout=args.client_timeout)

    started = time.time()
    run_started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    rounds: list[dict[str, Any]] = []
    for round_index in range(1, args.rounds + 1):
        print(f"Running round {round_index}/{args.rounds}...")
        rounds.append(
            _run_round_with_retries(
                client=client,
                args=args,
                turns=turns,
                round_index=round_index,
            )
        )

    passed_rounds = [item for item in rounds if item.get("pass")]
    failed_rounds = [int(item.get("round", 0)) for item in rounds if not item.get("pass")]
    total_round_duration_seconds = round(sum(float(item.get("duration_seconds", 0.0)) for item in rounds), 3)
    total_run_duration_seconds = round(time.time() - started, 3)
    average_round_duration_seconds = round(total_round_duration_seconds / len(rounds), 3) if rounds else 0.0

    summary: dict[str, Any] = {
        "test_type": "fresh_agent_memory_update",
        "run_tag": run_tag,
        "run_started_at": run_started_at,
        "duration_seconds": total_run_duration_seconds,
        "config": {
            "rounds": args.rounds,
            "model": args.model,
            "prompt_key": DEFAULT_PROMPT_KEY,
            "persona_key": args.persona_key,
            "embedding": args.embedding,
            "timezone": args.timezone,
            "context_window_limit": args.context_window_limit,
            "base_url": args.base_url,
            "expected_name": args.expected_name,
            "turns": turns,
            "strict_forbidden": args.strict_forbidden,
            "round_retries": args.round_retries,
            "require_first_turn_change": args.require_first_turn_change,
            "require_memory_change": args.require_memory_change,
            "require_expected_name": args.require_expected_name,
        },
        "results": rounds,
        "aggregate": {
            "rounds_total": args.rounds,
            "rounds_passed": len(passed_rounds),
            "rounds_failed": len(failed_rounds),
            "failed_rounds": failed_rounds,
            "pass_rate": round(len(passed_rounds) / args.rounds, 3),
            "total_run_duration_seconds": total_run_duration_seconds,
            "total_round_duration_seconds": total_round_duration_seconds,
            "average_round_duration_seconds": average_round_duration_seconds,
        },
    }

    summary_file = _write_summary(run_output_dir, summary)

    _append_run_index(
        output_root,
        {
            "run_tag": run_tag,
            "run_started_at": summary["run_started_at"],
            "rounds_total": summary["aggregate"]["rounds_total"],
            "rounds_passed": summary["aggregate"]["rounds_passed"],
            "rounds_failed": summary["aggregate"]["rounds_failed"],
            "failed_rounds": ",".join(str(item) for item in summary["aggregate"]["failed_rounds"]),
            "pass_rate": summary["aggregate"]["pass_rate"],
            "total_run_duration_seconds": summary["aggregate"]["total_run_duration_seconds"],
            "total_round_duration_seconds": summary["aggregate"]["total_round_duration_seconds"],
            "average_round_duration_seconds": summary["aggregate"]["average_round_duration_seconds"],
            "model": args.model,
            "embedding": args.embedding,
            "turns_count": len(turns),
            "output_file": str(summary_file),
            "error": "",
        },
    )

    print(f"Summary written to: {summary_file}")
    print(
        f"Pass rate: {summary['aggregate']['rounds_passed']}/{summary['aggregate']['rounds_total']}"
    )

    return 0 if len(passed_rounds) == args.rounds else 1


if __name__ == "__main__":
    raise SystemExit(main())
