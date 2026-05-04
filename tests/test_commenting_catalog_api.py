from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from agent_platform_api.models.commenting import CommentingGenerateRequest
from agent_platform_api.routers import commenting


def test_commenting_generate_uses_model_key_and_selected_source_connection(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(commenting, "ensure_platform_api_enabled", lambda: None)
    monkeypatch.setattr(
        commenting,
        "resolve_comment_model_selection",
        lambda model_key=None, model_selector=None, force_refresh=False: {
            "model_key": "local_unsloth::qwen3.5-27b",
            "source_id": "local_unsloth",
            "source_label": "Local Unsloth",
            "provider_model_id": "qwen3.5-27b",
            "base_url": "http://127.0.0.1:2234/v1",
            "source_adapter": "llama_cpp_server",
            "api_key": "local-token",
        },
    )

    def fake_generate_comment(**kwargs):
        captured.update(kwargs)
        return {
            "content": "Generated comment.",
            "content_source": "assistant_content",
            "selected_attempt": "classic",
            "finish_reason": "stop",
            "usage": {},
            "received_at": "2026-04-23T00:00:00+00:00",
            "raw_request": {"model": kwargs["model"]},
            "raw_reply": {"choices": []},
            "max_tokens": 128,
            "timeout_seconds": 45.0,
            "task_shape": "classic",
            "cache_prompt": kwargs["cache_prompt"],
            "enable_thinking": kwargs["enable_thinking"],
            "temperature": kwargs["temperature"],
            "top_p": kwargs["top_p"],
            "top_k": kwargs["top_k"],
        }

    monkeypatch.setattr(commenting.commenting_service, "generate_comment", fake_generate_comment)

    payload = asyncio.run(
        commenting.api_commenting_generate(
            CommentingGenerateRequest(
                input="Need one comment",
                prompt_key="comment_v20260418",
                persona_key="comment_linxiaotang",
                model_key="local_unsloth::qwen3.5-27b",
                max_tokens=128,
                timeout_seconds=45,
                retry_count=0,
                task_shape="classic",
                cache_prompt=False,
                enable_thinking=True,
                temperature=0.8,
                top_p=0.9,
                top_k=64,
            )
        )
    )

    assert captured["base_url"] == "http://127.0.0.1:2234/v1"
    assert captured["api_key"] == "local-token"
    assert captured["model"] == "qwen3.5-27b"
    assert captured["source_adapter"] == "llama_cpp_server"
    assert captured["cache_prompt"] is False
    assert captured["enable_thinking"] is True
    assert captured["temperature"] == 0.8
    assert captured["top_p"] == 0.9
    assert captured["top_k"] == 64
    assert payload["model_key"] == "local_unsloth::qwen3.5-27b"
    assert payload["source_label"] == "Local Unsloth"
    assert payload["provider_model_id"] == "qwen3.5-27b"
    assert payload["enable_thinking"] is True


def test_commenting_generate_request_rejects_removed_compact_task_shape() -> None:
    with pytest.raises(ValidationError, match="classic"):
        CommentingGenerateRequest(
            input="Need one comment",
            prompt_key="comment_v20260418",
            persona_key="comment_linxiaotang",
            model_key="local_unsloth::qwen3.5-27b",
            task_shape="compact",
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("temperature", -0.1),
        ("temperature", 2.1),
        ("top_p", 0),
        ("top_p", 1.1),
        ("top_k", 0),
    ],
)
def test_commenting_generate_request_rejects_invalid_sampling_ranges(field: str, value: float | int) -> None:
    kwargs = {
        "input": "Need one comment",
        "prompt_key": "comment_v20260418",
        "persona_key": "comment_linxiaotang",
        "model_key": "local_unsloth::qwen3.5-27b",
        field: value,
    }
    with pytest.raises(ValidationError):
        CommentingGenerateRequest(**kwargs)
