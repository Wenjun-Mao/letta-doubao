from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

CSV_FIELDS = [
    "run_id",
    "round",
    "status",
    "pass",
    "elapsed_seconds",
    "model",
    "prompt_key",
    "persona_key",
    "embedding",
    "fixture_key",
    "turn_count",
    "assistant_reply_count",
    "forbidden_hit_count",
    "human_memory_changed",
    "expected_facts_passed",
    "missing_expected_facts",
    "memory_tool_call_count",
    "total_tool_call_count",
    "judge_enabled",
    "judge_ok",
    "judge_pass",
    "judge_score",
    "agent_id",
    "archived",
    "purged",
    "error",
]


class ArtifactWriter:
    def __init__(self, *, csv_path: Path, jsonl_path: Path):
        self.csv_path = csv_path
        self.jsonl_path = jsonl_path
        self._csv_handle = None
        self._jsonl_handle = None
        self._writer = None

    def __enter__(self) -> ArtifactWriter:
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        self._csv_handle = self.csv_path.open("w", encoding="utf-8-sig", newline="")
        self._jsonl_handle = self.jsonl_path.open("w", encoding="utf-8", newline="\n")
        self._writer = csv.DictWriter(self._csv_handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        self._writer.writeheader()
        self._csv_handle.flush()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._csv_handle:
            self._csv_handle.close()
        if self._jsonl_handle:
            self._jsonl_handle.close()

    def write_round(self, row: dict[str, Any], raw_record: dict[str, Any]) -> None:
        if self._writer is None or self._csv_handle is None or self._jsonl_handle is None:
            raise RuntimeError("ArtifactWriter must be used as a context manager")
        self._writer.writerow(row)
        self._csv_handle.flush()
        self._jsonl_handle.write(json.dumps(raw_record, ensure_ascii=False, sort_keys=True) + "\n")
        self._jsonl_handle.flush()


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def build_summary(
    *,
    run_id: str,
    csv_path: Path,
    jsonl_path: Path,
    summary_path: Path,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    passed = sum(1 for row in rows if bool(row.get("pass")))
    errors = sum(1 for row in rows if row.get("status") == "error")
    return {
        "run_id": run_id,
        "rounds_total": len(rows),
        "rounds_passed": passed,
        "rounds_failed": len(rows) - passed,
        "errors": errors,
        "pass_rate": round(passed / len(rows), 3) if rows else 0.0,
        "csv_path": str(csv_path),
        "jsonl_path": str(jsonl_path),
        "summary_path": str(summary_path),
        "failed_rounds": [row.get("round") for row in rows if not bool(row.get("pass"))],
    }


def print_summary(summary: dict[str, Any]) -> None:
    print(f"run_id: {summary['run_id']}")
    print(
        "rounds: "
        f"{summary['rounds_passed']}/{summary['rounds_total']} passed "
        f"(errors={summary['errors']})"
    )
    print(f"csv: {summary['csv_path']}")
    print(f"jsonl: {summary['jsonl_path']}")
    print(f"summary: {summary['summary_path']}")

