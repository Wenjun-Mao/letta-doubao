from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_none

from agent_platform_api.services.commenting import (
    _RETRYABLE_COMMENTING_EXCEPTIONS,
    CommentingService,
)


def _build_service() -> CommentingService:
    return CommentingService(
        settings_factory=lambda: SimpleNamespace(
            commenting_timeout_seconds=180,
            commenting_max_tokens=0,
            commenting_task_shape="classic",
        )
    )


def test_chat_completions_url_supports_v1_and_v3_bases() -> None:
    assert CommentingService._chat_completions_url("http://127.0.0.1:1234/v1") == (
        "http://127.0.0.1:1234/v1/chat/completions"
    )
    assert CommentingService._chat_completions_url("https://ark.cn-beijing.volces.com/api/v3") == (
        "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
    )


def test_parse_sse_chat_completion_response_aggregates_chunks() -> None:
    payload = "\n".join(
        [
            'data: {"id":"chatcmpl-1","object":"chat.completion.chunk","created":1,"model":"gemma-4-31b-it","choices":[{"index":0,"delta":{"role":"assistant"}}]}',
            'data: {"id":"chatcmpl-1","object":"chat.completion.chunk","created":1,"model":"gemma-4-31b-it","choices":[{"index":0,"delta":{"content":"Hello"}}]}',
            'data: {"id":"chatcmpl-1","object":"chat.completion.chunk","created":1,"model":"gemma-4-31b-it","choices":[{"index":0,"delta":{"content":" world"}}]}',
            'data: {"id":"chatcmpl-1","object":"chat.completion.chunk","created":1,"model":"gemma-4-31b-it","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":2,"total_tokens":3}}',
            "data: [DONE]",
        ]
    )

    parsed = CommentingService._parse_sse_chat_completion_response(payload)

    assert parsed is not None
    assert parsed["model"] == "gemma-4-31b-it"
    assert parsed["usage"]["total_tokens"] == 3
    assert parsed["choices"][0]["message"]["content"] == "Hello world"
    assert parsed["choices"][0]["finish_reason"] == "stop"


def test_retry_count_zero_makes_single_provider_attempt(monkeypatch) -> None:
    service = _build_service()
    attempts = {"count": 0}

    def fake_once(payload, *, base_url, api_key, timeout_seconds):
        attempts["count"] += 1
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(service, "_post_chat_completions_once", fake_once)
    monkeypatch.setattr(
        service,
        "_build_retrying",
        lambda retry_count: Retrying(
            stop=stop_after_attempt(1 + service._clamp_retry_count(retry_count)),
            wait=wait_none(),
            retry=retry_if_exception_type(_RETRYABLE_COMMENTING_EXCEPTIONS),
            reraise=True,
        ),
    )

    with pytest.raises(httpx.TimeoutException):
        service._post_chat_completions(
            {"model": "lmstudio_openai/qwen3.5-27b"},
            base_url="http://127.0.0.1:1234/v1",
            api_key="test-key",
            timeout_seconds=30,
            retry_count=0,
        )

    assert attempts["count"] == 1


@pytest.mark.parametrize(
    ("retry_count", "expected_attempts"),
    [
        (1, 2),
        (2, 3),
    ],
)
def test_retry_count_controls_total_attempts(monkeypatch, retry_count: int, expected_attempts: int) -> None:
    service = _build_service()
    attempts = {"count": 0}

    def fake_once(payload, *, base_url, api_key, timeout_seconds):
        attempts["count"] += 1
        if attempts["count"] < expected_attempts:
            raise httpx.ReadError("temporary read failure")
        return {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}

    monkeypatch.setattr(service, "_post_chat_completions_once", fake_once)
    monkeypatch.setattr(
        service,
        "_build_retrying",
        lambda retry_count: Retrying(
            stop=stop_after_attempt(1 + service._clamp_retry_count(retry_count)),
            wait=wait_none(),
            retry=retry_if_exception_type(_RETRYABLE_COMMENTING_EXCEPTIONS),
            reraise=True,
        ),
    )

    payload = service._post_chat_completions(
        {"model": "lmstudio_openai/qwen3.5-27b"},
        base_url="http://127.0.0.1:1234/v1",
        api_key="test-key",
        timeout_seconds=30,
        retry_count=retry_count,
    )

    assert attempts["count"] == expected_attempts
    assert payload["choices"][0]["message"]["content"] == "ok"


def test_non_transient_provider_errors_do_not_retry(monkeypatch) -> None:
    service = _build_service()
    attempts = {"count": 0}

    def fake_once(payload, *, base_url, api_key, timeout_seconds):
        attempts["count"] += 1
        raise ValueError("bad request")

    monkeypatch.setattr(service, "_post_chat_completions_once", fake_once)
    monkeypatch.setattr(
        service,
        "_build_retrying",
        lambda retry_count: Retrying(
            stop=stop_after_attempt(1 + service._clamp_retry_count(retry_count)),
            wait=wait_none(),
            retry=retry_if_exception_type(_RETRYABLE_COMMENTING_EXCEPTIONS),
            reraise=True,
        ),
    )

    with pytest.raises(ValueError):
        service._post_chat_completions(
            {"model": "lmstudio_openai/qwen3.5-27b"},
            base_url="http://127.0.0.1:1234/v1",
            api_key="test-key",
            timeout_seconds=30,
            retry_count=5,
        )

    assert attempts["count"] == 1


def test_structured_output_fallback_stays_separate_from_retry_policy(monkeypatch) -> None:
    service = _build_service()
    calls: list[dict[str, object]] = []

    def fake_post(payload, *, base_url, api_key, timeout_seconds, retry_count):
        calls.append(
            {
                "payload": dict(payload),
                "base_url": base_url,
                "api_key": api_key,
                "timeout_seconds": timeout_seconds,
                "retry_count": retry_count,
            }
        )
        if "response_format" in payload:
            raise ValueError("response_format json_schema is not supported")
        return {
            "choices": [
                {
                    "message": {"content": json.dumps({"comment": "Fallback succeeded."})},
                    "finish_reason": "stop",
                }
            ],
            "usage": {},
        }

    monkeypatch.setattr(service, "_post_chat_completions", fake_post)

    result = service.generate_comment(
        base_url="http://127.0.0.1:1234/v1",
        api_key="test-key",
        model="lmstudio_openai/qwen3.5-27b",
        system_prompt="System",
        persona_prompt="Persona",
        news_input="News input",
        timeout_seconds=45,
        retry_count=0,
        task_shape="structured_output",
    )

    assert "Fallback succeeded." in result["content"]
    assert len(calls) == 2
    assert "response_format" in calls[0]["payload"]
    assert "response_format" not in calls[1]["payload"]
    assert all(call["base_url"] == "http://127.0.0.1:1234/v1" for call in calls)
    assert all(call["api_key"] == "test-key" for call in calls)
    assert all(call["retry_count"] == 0 for call in calls)


def test_generate_comment_strips_think_tags_from_assistant_content(monkeypatch) -> None:
    service = _build_service()

    monkeypatch.setattr(
        service,
        "_post_chat_completions",
        lambda payload, *, base_url, api_key, timeout_seconds, retry_count: {
            "choices": [
                {
                    "message": {"content": "<think>private reasoning</think>Public reply"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {},
        },
    )

    result = service.generate_comment(
        base_url="http://127.0.0.1:1234/v1",
        api_key="test-key",
        model="lmstudio_openai/gemma-4-31b-it",
        system_prompt="System",
        persona_prompt="Persona",
        news_input="News input",
        timeout_seconds=45,
        retry_count=0,
        task_shape="classic",
    )

    assert result["content"] == "Public reply。"


def test_generate_comment_rejects_removed_compact_task_shape(monkeypatch) -> None:
    service = _build_service()

    monkeypatch.setattr(
        service,
        "_post_chat_completions",
        lambda payload, *, base_url, api_key, timeout_seconds, retry_count: {
            "choices": [
                {
                    "message": {"content": "Should not be used."},
                    "finish_reason": "stop",
                }
            ],
            "usage": {},
        },
    )

    with pytest.raises(ValueError, match="Unsupported task_shape: compact"):
        service.generate_comment(
            base_url="http://127.0.0.1:1234/v1",
            api_key="test-key",
            model="lmstudio_openai/gemma-4-31b-it",
            system_prompt="System",
            persona_prompt="Persona",
            news_input="News input",
            timeout_seconds=45,
            retry_count=0,
            task_shape="compact",
        )
