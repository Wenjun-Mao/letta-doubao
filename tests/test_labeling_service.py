from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from utils.labeling_service import LabelingService, LabelingValidationError


def _build_service() -> LabelingService:
    return LabelingService(
        settings_factory=lambda: SimpleNamespace(
            labeling_timeout_seconds=60,
            labeling_max_tokens=512,
            labeling_repair_retry_count=1,
        )
    )


def test_generate_labels_strict_json_schema_succeeds(monkeypatch) -> None:
    service = _build_service()

    monkeypatch.setattr(
        service,
        "_post_chat_completions",
        lambda payload, *, base_url, api_key, timeout_seconds: {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "spans": [
                                    {"label": "PLAYER", "text": "Messi", "start": 0, "end": 5},
                                    {"label": "TEAM", "text": "Inter Miami", "start": 17, "end": 28},
                                ]
                            }
                        )
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"total_tokens": 12},
        },
    )

    result = service.generate_labels(
        base_url="https://ark.example/v3",
        api_key="ark-token",
        model="openai-proxy/doubao-seed-1-8-251228",
        system_prompt="Return spans.",
        article_input="Messi scored for Inter Miami.",
        output_mode="strict_json_schema",
    )

    assert result["output_mode"] == "strict_json_schema"
    assert result["selected_attempt"] == "primary"
    assert result["result"]["spans"][0]["text"] == "Messi"
    assert result["validation_errors"] == []


def test_generate_labels_json_schema_sends_llama_server_response_format(monkeypatch) -> None:
    service = _build_service()
    captured: dict[str, object] = {}

    def fake_post(payload, *, base_url, api_key, timeout_seconds):
        captured.update(payload)
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "spans": [
                                    {"label": "PLAYER", "text": "Messi", "start": 0, "end": 5},
                                ]
                            }
                        )
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {},
        }

    monkeypatch.setattr(service, "_post_chat_completions", fake_post)

    result = service.generate_labels(
        base_url="http://127.0.0.1:8081/v1",
        api_key="local-token",
        model="gemma4",
        system_prompt="Return spans.",
        article_input="Messi scored.",
        output_mode="json_schema",
        output_schema_raw=json.dumps(
            {
                "type": "object",
                "properties": {
                    "spans": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "text": {"type": "string"},
                                "start": {"type": "integer"},
                                "end": {"type": "integer"},
                            },
                            "required": ["label", "text", "start", "end"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["spans"],
                "additionalProperties": False,
            }
        ),
        output_schema_name="label_span_annotations_v1",
    )

    assert result["output_mode"] == "json_schema"
    assert captured["model"] == "gemma4"
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["response_format"]["json_schema"]["name"] == "label_span_annotations_v1"
    assert captured["response_format"]["json_schema"]["strict"] is True
    assert captured["response_format"]["json_schema"]["schema"]["required"] == ["spans"]


def test_generate_labels_best_effort_strips_think_tags(monkeypatch) -> None:
    service = _build_service()

    monkeypatch.setattr(
        service,
        "_post_chat_completions",
        lambda payload, *, base_url, api_key, timeout_seconds: {
            "choices": [
                {
                    "message": {
                        "content": (
                            "<think>private reasoning</think>"
                            '{"spans":[{"label":"PLAYER","text":"Messi","start":0,"end":5}]}'
                        )
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {},
        },
    )

    result = service.generate_labels(
        base_url="http://127.0.0.1:2234/v1",
        api_key="local-token",
        model="lmstudio_openai/gemma-4-31b-it",
        system_prompt="Return spans.",
        article_input="Messi scored.",
        output_mode="best_effort_prompt_json",
    )

    assert result["result"]["spans"] == [
        {"label": "PLAYER", "text": "Messi", "start": 0, "end": 5}
    ]


def test_generate_labels_normalizes_unique_text_offsets(monkeypatch) -> None:
    service = _build_service()

    monkeypatch.setattr(
        service,
        "_post_chat_completions",
        lambda payload, *, base_url, api_key, timeout_seconds: {
            "choices": [
                {
                    "message": {
                        "content": '{"spans":[{"label":"TEAM","text":"Orlando City","start":39,"end":51}]}'
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {},
        },
    )

    result = service.generate_labels(
        base_url="http://127.0.0.1:8081/v1",
        api_key="local-token",
        model="gemma4",
        system_prompt="Return spans.",
        article_input="Messi scored for Inter Miami against Orlando City.",
        output_mode="json_schema",
    )

    assert result["result"]["spans"] == [
        {"label": "TEAM", "text": "Orlando City", "start": 37, "end": 49}
    ]


def test_generate_labels_uses_repair_attempt_after_validation_failure(monkeypatch) -> None:
    service = _build_service()
    calls: list[dict[str, object]] = []

    def fake_post(payload, *, base_url, api_key, timeout_seconds):
        calls.append(payload)
        if len(calls) == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"spans":[{"label":"PLAYER","text":"Ronaldo","start":0,"end":7}]}'
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {},
            }
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"spans":[{"label":"PLAYER","text":"Messi","start":0,"end":5}]}'
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {},
        }

    monkeypatch.setattr(service, "_post_chat_completions", fake_post)

    result = service.generate_labels(
        base_url="http://127.0.0.1:2234/v1",
        api_key="local-token",
        model="lmstudio_openai/gemma-4-31b-it",
        system_prompt="Return spans.",
        article_input="Messi scored.",
        output_mode="best_effort_prompt_json",
        repair_retry_count=1,
    )

    assert len(calls) == 2
    assert result["selected_attempt"] == "repair"
    assert result["result"]["spans"][0]["start"] == 0


def test_generate_labels_raises_validation_error_after_repair_failure(monkeypatch) -> None:
    service = _build_service()

    monkeypatch.setattr(
        service,
        "_post_chat_completions",
        lambda payload, *, base_url, api_key, timeout_seconds: {
            "choices": [
                {
                        "message": {
                            "content": '{"spans":[{"label":"PLAYER","text":"Ronaldo","start":0,"end":7}]}'
                        },
                    "finish_reason": "stop",
                }
            ],
            "usage": {},
        },
    )

    with pytest.raises(LabelingValidationError, match="invalid structured output") as exc_info:
        service.generate_labels(
            base_url="http://127.0.0.1:2234/v1",
            api_key="local-token",
            model="lmstudio_openai/gemma-4-31b-it",
            system_prompt="Return spans.",
            article_input="Messi scored.",
            output_mode="best_effort_prompt_json",
            repair_retry_count=1,
        )

    assert any("input[start:end]" in item for item in exc_info.value.validation_errors)
