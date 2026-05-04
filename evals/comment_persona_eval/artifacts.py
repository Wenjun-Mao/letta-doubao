from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

CSV_FIELDS = [
    "run_id",
    "round",
    "persona_key",
    "persona_label",
    "persona_description",
    "status",
    "elapsed_seconds",
    "content",
    "content_length",
    "finish_reason",
    "content_source",
    "usage_prompt_tokens",
    "usage_completion_tokens",
    "usage_total_tokens",
    "error",
    "model_key",
    "prompt_key",
    "task_shape",
    "cache_prompt",
    "enable_thinking",
    "temperature",
    "top_p",
    "top_k",
    "max_tokens",
    "timeout_seconds",
    "retry_count",
    "reasoning_length",
    "usage_reasoning_tokens",
    "timings_cache_n",
    "timings_prompt_n",
    "timings_predicted_n",
]


class ArtifactWriter:
    """Append CSV and JSONL records as each eval attempt finishes."""

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

    def write_attempt(self, row: dict[str, Any], raw_record: dict[str, Any]) -> None:
        if self._writer is None or self._csv_handle is None or self._jsonl_handle is None:
            raise RuntimeError("ArtifactWriter must be used as a context manager")
        self._writer.writerow(row)
        self._csv_handle.flush()
        self._jsonl_handle.write(json.dumps(raw_record, ensure_ascii=False, sort_keys=True) + "\n")
        self._jsonl_handle.flush()


def write_artifacts(
    *,
    csv_path: Path,
    jsonl_path: Path,
    rows: list[dict[str, Any]],
    raw_records: list[dict[str, Any]],
) -> None:
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    with jsonl_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in raw_records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def build_summary(run_id: str, csv_path: Path, jsonl_path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    successes = sum(1 for row in rows if row.get("status") == "ok")
    failures = len(rows) - successes
    slowest = sorted(rows, key=lambda row: float(row.get("elapsed_seconds", 0)), reverse=True)[:5]
    return {
        "run_id": run_id,
        "total_attempts": len(rows),
        "successes": successes,
        "failures": failures,
        "csv_path": str(csv_path),
        "jsonl_path": str(jsonl_path),
        "slowest": [
            {
                "persona_key": row.get("persona_key", ""),
                "round": row.get("round", ""),
                "elapsed_seconds": row.get("elapsed_seconds", 0),
                "status": row.get("status", ""),
            }
            for row in slowest
        ],
    }


def print_summary(summary: dict[str, Any]) -> None:
    print(f"run_id: {summary['run_id']}")
    print(f"attempts: {summary['total_attempts']}  successes: {summary['successes']}  failures: {summary['failures']}")
    print(f"csv: {summary['csv_path']}")
    print(f"jsonl: {summary['jsonl_path']}")
    if summary.get("slowest"):
        print("slowest:")
        for item in summary["slowest"]:
            print(
                f"  {item['persona_key']} round={item['round']} "
                f"elapsed={item['elapsed_seconds']}s status={item['status']}"
            )


def row_id(row: dict[str, Any]) -> str:
    return f"{row['run_id']}::{row['round']}::{row['persona_key']}"
