from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import httpx

from evals.comment_persona_eval.artifacts import ArtifactWriter, write_artifacts
from evals.comment_persona_eval.workflow import (
    EvalConfig,
    fetch_comment_personas,
    load_config,
    run_attempt,
    validate_comment_options,
)


def _response(status_code: int, payload: dict[str, Any], request: httpx.Request) -> httpx.Response:
    return httpx.Response(status_code, json=payload, request=request)


def test_default_config_loads_comment_lab_values() -> None:
    config = load_config(Path("evals/comment_persona_eval/config.toml"))

    assert config.model_key == "dgx_vllm::gemma4-31b-nvfp4"
    assert config.prompt_key == "comment_v20260418"
    assert config.max_tokens == 0
    assert config.timeout_seconds == 180
    assert config.retry_count == 0
    assert config.task_shape == "all_in_system"
    assert config.cache_prompt is False
    assert config.enable_thinking is False
    assert config.temperature == 1.0
    assert config.top_p == 0.95
    assert config.top_k == 64
    assert config.news_path.name == "sports_news_demo2.txt"
    assert config.rounds == 1


def test_fetch_comment_personas_filters_by_key_search_and_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["scenario"] == "comment"
        assert request.url.params["search"] == "Messi"
        return _response(
            200,
            {
                "items": [
                    {"key": "comment_first", "label": "First", "archived": False},
                    {"key": "chat_wrong", "label": "Wrong", "archived": False},
                    {"key": "comment_archived", "label": "Archived", "archived": True},
                    {"key": "comment_second", "label": "Second", "archived": False},
                ]
            },
            request,
        )

    config = EvalConfig(
        news_path=Path("evals/comment_persona_eval/inputs/sports_news_demo.txt"),
        persona_search="Messi",
        persona_keys=("comment_second",),
        limit=1,
    )
    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler)) as client:
        personas = fetch_comment_personas(client, config)

    assert [item["key"] for item in personas] == ["comment_second"]


def test_validate_comment_options_rejects_unavailable_model_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _response(
            200,
            {
                "models": [{"key": "ark::doubao-seed-2-0-pro-260215"}],
                "prompts": [{"key": "comment_v20260418"}],
            },
            request,
        )

    config = EvalConfig(
        news_path=Path("evals/comment_persona_eval/inputs/sports_news_demo.txt"),
        model_key="ark::doubao-seed-2-pro-260215",
    )
    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler)) as client:
        try:
            validate_comment_options(client, config)
        except ValueError as exc:
            assert "is not available" in str(exc)
            assert "ark::doubao-seed-2-0-pro-260215" in str(exc)
        else:
            raise AssertionError("Expected unavailable model_key to fail preflight validation")


def test_run_attempt_uses_comment_lab_payload_and_flattens_success() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return _response(
            200,
            {
                "content": "这条新闻确实值得继续观察。",
                "finish_reason": "stop",
                "content_source": "assistant_content",
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
                "raw_reply": {"timings": {"cache_n": 0, "prompt_n": 123, "predicted_n": 24}},
            },
            request,
        )

    config = EvalConfig(
        news_path=Path("evals/comment_persona_eval/inputs/sports_news_demo.txt"),
        model_key="local_llama_server::gemma4",
        prompt_key="comment_v20260418",
        max_tokens=0,
        timeout_seconds=180,
        retry_count=0,
        task_shape="all_in_system",
        cache_prompt=False,
        temperature=0.7,
        top_p=0.95,
        top_k=64,
    )
    persona = {"key": "comment_demo", "label": "Demo", "description": "Demo persona"}
    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler)) as client:
        row, raw = run_attempt(
            client,
            config=config,
            run_id="run-1",
            round_number=2,
            persona=persona,
            news_text="News body",
        )

    assert captured["payload"] == {
        "scenario": "comment",
        "input": "News body",
        "prompt_key": "comment_v20260418",
        "persona_key": "comment_demo",
        "model_key": "local_llama_server::gemma4",
        "max_tokens": 0,
        "timeout_seconds": 180,
        "retry_count": 0,
        "task_shape": "all_in_system",
        "cache_prompt": False,
        "enable_thinking": False,
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 64,
    }
    assert row["status"] == "ok"
    assert row["content"] == "这条新闻确实值得继续观察。"
    assert row["content_length"] == len("这条新闻确实值得继续观察。")
    assert row["usage_total_tokens"] == 18
    assert row["cache_prompt"] is False
    assert row["enable_thinking"] is False
    assert row["temperature"] == 0.7
    assert row["top_p"] == 0.95
    assert row["top_k"] == 64
    assert row["timings_cache_n"] == 0
    assert row["timings_prompt_n"] == 123
    assert row["timings_predicted_n"] == 24
    assert raw["request"]["persona_key"] == "comment_demo"
    assert raw["response"]["finish_reason"] == "stop"


def test_write_artifacts_preserves_csv_and_raw_jsonl(tmp_path) -> None:
    rows = [
        {
            "run_id": "run-1",
            "round": 1,
            "persona_key": "comment_demo",
            "persona_label": "Demo",
            "persona_description": "",
            "status": "error",
            "elapsed_seconds": 0.123,
            "content": "",
            "content_length": 0,
            "finish_reason": "",
            "content_source": "",
            "usage_prompt_tokens": 0,
            "usage_completion_tokens": 0,
            "usage_total_tokens": 0,
            "error": "bad gateway",
            "model_key": "local_llama_server::gemma4",
            "prompt_key": "comment_v20260418",
            "task_shape": "all_in_system",
            "cache_prompt": False,
            "enable_thinking": False,
            "temperature": 0.6,
            "top_p": 1.0,
            "top_k": 64,
            "max_tokens": 0,
            "timeout_seconds": 180,
            "retry_count": 0,
            "reasoning_length": 0,
            "usage_reasoning_tokens": 0,
            "timings_cache_n": 0,
            "timings_prompt_n": 0,
            "timings_predicted_n": 0,
        }
    ]
    raw_records = [
        {
            "row_id": "run-1::1::comment_demo",
            "request": {"persona_key": "comment_demo"},
            "response": None,
            "error": "bad gateway",
        }
    ]
    csv_path = tmp_path / "eval.csv"
    jsonl_path = tmp_path / "eval.jsonl"

    write_artifacts(csv_path=csv_path, jsonl_path=jsonl_path, rows=rows, raw_records=raw_records)

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    assert csv_rows[0]["status"] == "error"
    assert csv_rows[0]["error"] == "bad gateway"

    raw_line = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert raw_line["request"]["persona_key"] == "comment_demo"
    assert raw_line["error"] == "bad gateway"


def test_artifact_writer_streams_attempts_before_context_closes(tmp_path) -> None:
    row = {
        "run_id": "run-1",
        "round": 1,
        "persona_key": "comment_demo",
        "persona_label": "Demo",
        "persona_description": "",
        "status": "ok",
        "elapsed_seconds": 0.123,
        "content": "hello",
        "content_length": 5,
        "finish_reason": "stop",
        "content_source": "assistant_content",
        "usage_prompt_tokens": 1,
        "usage_completion_tokens": 2,
        "usage_total_tokens": 3,
        "error": "",
        "model_key": "local_llama_server::gemma4",
        "prompt_key": "comment_v20260418",
        "task_shape": "all_in_system",
        "cache_prompt": False,
        "enable_thinking": False,
        "temperature": 0.6,
        "top_p": 1.0,
        "top_k": 64,
        "max_tokens": 0,
        "timeout_seconds": 180,
        "retry_count": 0,
        "reasoning_length": 0,
        "usage_reasoning_tokens": 0,
        "timings_cache_n": 0,
        "timings_prompt_n": 10,
        "timings_predicted_n": 5,
    }
    raw_record = {"row_id": "run-1::1::comment_demo", "request": {"persona_key": "comment_demo"}}
    csv_path = tmp_path / "stream.csv"
    jsonl_path = tmp_path / "stream.jsonl"

    with ArtifactWriter(csv_path=csv_path, jsonl_path=jsonl_path) as writer:
        writer.write_attempt(row, raw_record)

        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            csv_rows = list(csv.DictReader(handle))
        assert csv_rows[0]["content"] == "hello"
        assert json.loads(jsonl_path.read_text(encoding="utf-8").strip())["row_id"] == "run-1::1::comment_demo"
