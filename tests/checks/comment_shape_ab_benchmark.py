from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import httpx


DEFAULT_INPUTS = [
    "苹果发布了新产品，价格引发争议。",
    "某品牌奶茶宣布涨价，网友讨论很激烈。",
    "景区节假日人流管理新规上线，支持和吐槽都有。",
    "平台调整创作者分成比例，大家意见分化明显。",
    "一线城市地铁延长运营时间，通勤族反应两极。",
]


@dataclass
class RunRecord:
    shape: str
    max_tokens: int
    run_index: int
    topic_index: int
    status_code: int
    latency_seconds: float
    strict_success: bool
    selected_attempt: str
    finish_reason: str
    content_source: str
    content_length: int
    usage_prompt_tokens: int | None
    usage_completion_tokens: int | None
    usage_total_tokens: int | None
    usage_reasoning_tokens: int | None
    received_at: str
    quality_pass: bool
    error_detail: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark Comment Lab task shapes with strict success criteria")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8284/api/v1/commenting/generate")
    parser.add_argument("--model", default="qwen3.5-27b")
    parser.add_argument("--prompt-key", default="comment_v20260418")
    parser.add_argument("--persona-key", default="comment_linxiaotang")
    parser.add_argument("--runs-per-shape", type=int, default=20)
    parser.add_argument("--max-tokens", default="0,256,512,1024")
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--client-timeout-seconds", type=float, default=240.0)
    parser.add_argument("--shapes", default="compact,agent_studio")
    parser.add_argument("--output-dir", default="tests/outputs")
    return parser.parse_args()


def parse_int_list(value: str) -> list[int]:
    out: list[int] = []
    for token in str(value).split(","):
        token = token.strip()
        if not token:
            continue
        out.append(int(token))
    if not out:
        raise ValueError("at least one integer is required")
    return out


def parse_str_list(value: str) -> list[str]:
    out = [token.strip() for token in str(value).split(",") if token.strip()]
    if not out:
        raise ValueError("at least one value is required")
    return out


def distribute(total: int, buckets: list[int]) -> dict[int, int]:
    base = total // len(buckets)
    remainder = total % len(buckets)
    out: dict[int, int] = {}
    for idx, bucket in enumerate(buckets):
        out[bucket] = base + (1 if idx < remainder else 0)
    return out


def as_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def mean_optional(values: list[float | int | None]) -> float | None:
    filtered = [float(value) for value in values if value is not None]
    if not filtered:
        return None
    return round(statistics.mean(filtered), 2)


def reasoning_ratio_pct(reasoning_tokens: int | None, completion_tokens: int | None) -> float | None:
    if reasoning_tokens is None or completion_tokens is None:
        return None
    if completion_tokens <= 0:
        return None
    return round((reasoning_tokens / completion_tokens) * 100.0, 2)


def quality_pass(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    if len(value) < 8 or len(value) > 220:
        return False
    lowered = value.lower()
    blocked_markers = (
        "persona:",
        "assistant:",
        "system:",
        "reasoning",
        "思考过程",
        "最终决定",
        "option 1",
        "option 2",
    )
    if any(marker in lowered for marker in blocked_markers):
        return False
    if value.startswith(("-", "*", "1.", "2.", "3.")):
        return False
    if not value.endswith(("。", "！", "？", "!", "?", "～", "~", "」", "』", "”", '"')):
        return False
    return True


def pct(value: float) -> float:
    return round(value * 100.0, 2)


def benchmark(args: argparse.Namespace) -> tuple[list[RunRecord], list[dict[str, Any]], list[dict[str, Any]]]:
    shapes = parse_str_list(args.shapes)
    max_tokens_list = parse_int_list(args.max_tokens)
    distribution = distribute(args.runs_per_shape, max_tokens_list)

    records: list[RunRecord] = []
    total_runs = len(shapes) * args.runs_per_shape
    run_counter = 0

    client = httpx.Client(timeout=args.client_timeout_seconds)
    try:
        for shape in shapes:
            topic_cursor = 0
            shape_run_idx = 0
            for max_tokens, count in distribution.items():
                for _ in range(count):
                    run_counter += 1
                    shape_run_idx += 1
                    topic_idx = topic_cursor % len(DEFAULT_INPUTS)
                    topic_cursor += 1
                    payload = {
                        "scenario": "comment",
                        "input": DEFAULT_INPUTS[topic_idx],
                        "prompt_key": args.prompt_key,
                        "persona_key": args.persona_key,
                        "model": args.model,
                        "timeout_seconds": args.timeout_seconds,
                        "task_shape": shape,
                    }
                    if int(max_tokens) > 0:
                        payload["max_tokens"] = int(max_tokens)

                    started_at = time.time()
                    status_code = 0
                    selected_attempt = ""
                    finish_reason = ""
                    content_source = ""
                    content = ""
                    usage_prompt_tokens: int | None = None
                    usage_completion_tokens: int | None = None
                    usage_total_tokens: int | None = None
                    usage_reasoning_tokens: int | None = None
                    received_at = ""
                    error_detail = ""

                    try:
                        response = client.post(args.endpoint, json=payload)
                        latency = time.time() - started_at
                        status_code = int(response.status_code)
                        if status_code == 200:
                            data = as_obj(response.json())
                            selected_attempt = str(data.get("selected_attempt", "") or "")
                            finish_reason = str(data.get("finish_reason", "") or "")
                            content_source = str(data.get("content_source", "") or "")
                            content = str(data.get("content", "") or "")
                            usage = as_obj(data.get("usage"))
                            if not usage:
                                raw_reply = as_obj(data.get("raw_reply"))
                                usage = as_obj(raw_reply.get("usage"))
                            usage_prompt_tokens = as_int(usage.get("prompt_tokens"))
                            usage_completion_tokens = as_int(usage.get("completion_tokens"))
                            usage_total_tokens = as_int(usage.get("total_tokens"))
                            completion_tokens_details = as_obj(usage.get("completion_tokens_details"))
                            usage_reasoning_tokens = as_int(completion_tokens_details.get("reasoning_tokens"))
                            received_at = str(data.get("received_at", "") or "")
                        else:
                            error_detail = response.text.strip()[:600]
                    except Exception as exc:
                        latency = time.time() - started_at
                        error_detail = str(exc)

                    is_quality_pass = quality_pass(content)
                    strict_success = (
                        status_code == 200
                        and content_source == "assistant_content"
                        and bool(content.strip())
                    )

                    records.append(
                        RunRecord(
                            shape=shape,
                            max_tokens=int(max_tokens),
                            run_index=shape_run_idx,
                            topic_index=topic_idx,
                            status_code=status_code,
                            latency_seconds=round(latency, 2),
                            strict_success=strict_success,
                            selected_attempt=selected_attempt,
                            finish_reason=finish_reason,
                            content_source=content_source,
                            content_length=len(content.strip()),
                            usage_prompt_tokens=usage_prompt_tokens,
                            usage_completion_tokens=usage_completion_tokens,
                            usage_total_tokens=usage_total_tokens,
                            usage_reasoning_tokens=usage_reasoning_tokens,
                            received_at=received_at,
                            quality_pass=is_quality_pass,
                            error_detail=error_detail,
                        )
                    )

                    max_tokens_label = "unlimited" if int(max_tokens) == 0 else str(max_tokens)
                    print(
                        f"[{run_counter}/{total_runs}] shape={shape} max_tokens={max_tokens_label} "
                        f"status={status_code} strict_success={strict_success} "
                        f"source={content_source or '-'} selected={selected_attempt or '-'} "
                        f"finish={finish_reason or '-'} secs={round(latency, 2)} "
                        f"usage_total={usage_total_tokens if usage_total_tokens is not None else '-'} "
                        f"usage_reasoning={usage_reasoning_tokens if usage_reasoning_tokens is not None else '-'}"
                    )
    finally:
        client.close()

    by_cell: list[dict[str, Any]] = []
    by_shape: list[dict[str, Any]] = []

    for shape in shapes:
        shape_rows = [row for row in records if row.shape == shape]
        shape_http_200_rows = [row for row in shape_rows if row.status_code == 200]
        strict_shape_rows = [row for row in shape_rows if row.strict_success]
        selected_mismatch = [row for row in shape_rows if row.status_code == 200 and row.selected_attempt and row.selected_attempt != shape]
        extraction_rows = [row for row in shape_rows if row.content_source == "reasoning_tail_extraction"]
        finish_stop_rows = [row for row in shape_http_200_rows if row.finish_reason == "stop"]
        shape_reasoning_ratios = [
            reasoning_ratio_pct(row.usage_reasoning_tokens, row.usage_completion_tokens)
            for row in shape_http_200_rows
        ]

        by_shape.append(
            {
                "shape": shape,
                "runs": len(shape_rows),
                "strict_success_rate_pct": pct(len(strict_shape_rows) / len(shape_rows)) if shape_rows else 0.0,
                "http_200_rate_pct": pct(len(shape_http_200_rows) / len(shape_rows)) if shape_rows else 0.0,
                "avg_latency_seconds_strict_success": round(statistics.mean(row.latency_seconds for row in strict_shape_rows), 2)
                if strict_shape_rows
                else None,
                "avg_latency_seconds_http_200": mean_optional([row.latency_seconds for row in shape_http_200_rows]),
                "fallback_rate_pct": pct(len(selected_mismatch) / max(1, sum(1 for row in shape_rows if row.status_code == 200))),
                "quality_pass_rate_on_strict_success_pct": pct(
                    sum(1 for row in strict_shape_rows if row.quality_pass) / max(1, len(strict_shape_rows))
                ),
                "reasoning_tail_extraction_rate_pct": pct(len(extraction_rows) / len(shape_rows)) if shape_rows else 0.0,
                "finish_reason_stop_rate_pct": pct(len(finish_stop_rows) / len(shape_http_200_rows)) if shape_http_200_rows else 0.0,
                "avg_usage_total_tokens_http_200": mean_optional([row.usage_total_tokens for row in shape_http_200_rows]),
                "avg_usage_reasoning_tokens_http_200": mean_optional([row.usage_reasoning_tokens for row in shape_http_200_rows]),
                "avg_reasoning_ratio_pct_http_200": mean_optional(shape_reasoning_ratios),
            }
        )

        for max_tokens in max_tokens_list:
            rows = [row for row in shape_rows if row.max_tokens == max_tokens]
            http_200_rows = [row for row in rows if row.status_code == 200]
            strict_rows = [row for row in rows if row.strict_success]
            selected_mismatch_cell = [row for row in rows if row.status_code == 200 and row.selected_attempt and row.selected_attempt != shape]
            extraction_cell = [row for row in rows if row.content_source == "reasoning_tail_extraction"]
            finish_stop_cell = [row for row in http_200_rows if row.finish_reason == "stop"]
            reasoning_ratios_cell = [
                reasoning_ratio_pct(row.usage_reasoning_tokens, row.usage_completion_tokens)
                for row in http_200_rows
            ]

            by_cell.append(
                {
                    "shape": shape,
                    "max_tokens": max_tokens,
                    "runs": len(rows),
                    "strict_success_rate_pct": pct(len(strict_rows) / len(rows)) if rows else 0.0,
                    "http_200_rate_pct": pct(len(http_200_rows) / len(rows)) if rows else 0.0,
                    "avg_latency_seconds_strict_success": round(statistics.mean(row.latency_seconds for row in strict_rows), 2)
                    if strict_rows
                    else None,
                    "avg_latency_seconds_http_200": mean_optional([row.latency_seconds for row in http_200_rows]),
                    "fallback_rate_pct": pct(len(selected_mismatch_cell) / max(1, sum(1 for row in rows if row.status_code == 200))),
                    "quality_pass_rate_on_strict_success_pct": pct(
                        sum(1 for row in strict_rows if row.quality_pass) / max(1, len(strict_rows))
                    ),
                    "reasoning_tail_extraction_rate_pct": pct(len(extraction_cell) / len(rows)) if rows else 0.0,
                    "finish_reason_stop_rate_pct": pct(len(finish_stop_cell) / len(http_200_rows)) if http_200_rows else 0.0,
                    "avg_usage_total_tokens_http_200": mean_optional([row.usage_total_tokens for row in http_200_rows]),
                    "avg_usage_reasoning_tokens_http_200": mean_optional([row.usage_reasoning_tokens for row in http_200_rows]),
                    "avg_reasoning_ratio_pct_http_200": mean_optional(reasoning_ratios_cell),
                }
            )

    return records, by_cell, by_shape


def render_markdown_table(rows: list[dict[str, Any]], headers: list[str]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(header, "")) for header in headers) + " |")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    records, by_cell, by_shape = benchmark(args)

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"comment-shape-benchmark-{timestamp}.json"

    payload = {
        "config": {
            "endpoint": args.endpoint,
            "model": args.model,
            "prompt_key": args.prompt_key,
            "persona_key": args.persona_key,
            "runs_per_shape": args.runs_per_shape,
            "max_tokens": args.max_tokens,
            "timeout_seconds": args.timeout_seconds,
            "client_timeout_seconds": args.client_timeout_seconds,
            "shapes": args.shapes,
            "strict_success_definition": "status=200 and content_source=assistant_content and content_non_empty",
        },
        "summary_by_cell": by_cell,
        "summary_by_shape": by_shape,
        "records": [asdict(record) for record in records],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    cell_headers = [
        "shape",
        "max_tokens",
        "runs",
        "strict_success_rate_pct",
        "http_200_rate_pct",
        "avg_latency_seconds_strict_success",
        "avg_latency_seconds_http_200",
        "fallback_rate_pct",
        "quality_pass_rate_on_strict_success_pct",
        "reasoning_tail_extraction_rate_pct",
        "finish_reason_stop_rate_pct",
        "avg_usage_total_tokens_http_200",
        "avg_usage_reasoning_tokens_http_200",
        "avg_reasoning_ratio_pct_http_200",
    ]
    shape_headers = [
        "shape",
        "runs",
        "strict_success_rate_pct",
        "http_200_rate_pct",
        "avg_latency_seconds_strict_success",
        "avg_latency_seconds_http_200",
        "fallback_rate_pct",
        "quality_pass_rate_on_strict_success_pct",
        "reasoning_tail_extraction_rate_pct",
        "finish_reason_stop_rate_pct",
        "avg_usage_total_tokens_http_200",
        "avg_usage_reasoning_tokens_http_200",
        "avg_reasoning_ratio_pct_http_200",
    ]

    print("\nBenchmark JSON:", json_path)
    print("\nSummary by shape+max_tokens")
    print(render_markdown_table(by_cell, cell_headers))
    print("\nSummary by shape")
    print(render_markdown_table(by_shape, shape_headers))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
