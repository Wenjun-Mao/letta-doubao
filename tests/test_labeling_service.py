from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agent_platform_api.services.labeling import LabelingService, LabelingValidationError


def _build_service() -> LabelingService:
    return LabelingService(
        settings_factory=lambda: SimpleNamespace(
            labeling_timeout_seconds=60,
            labeling_max_tokens=1024,
            labeling_repair_retry_count=1,
            labeling_temperature=0.0,
            labeling_top_p=1.0,
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
                                "players": ["Messi"],
                                "teams": ["Inter Miami"],
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
        system_prompt="Return grouped entities.",
        article_input="Messi scored for Inter Miami.",
        output_mode="strict_json_schema",
        output_schema_raw=json.dumps(
            {
                "type": "object",
                "properties": {
                    "players": {"type": "array", "items": {"type": "string"}},
                    "teams": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["players", "teams"],
                "additionalProperties": False,
            }
        ),
    )

    assert result["output_mode"] == "strict_json_schema"
    assert result["selected_attempt"] == "primary"
    assert result["result"]["players"] == ["Messi"]
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
                                "players": ["Messi"],
                                "teams": ["Inter Miami"],
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
        system_prompt="Return grouped entities.",
        article_input="Messi scored for Inter Miami.",
        output_mode="json_schema",
        output_schema_raw=json.dumps(
            {
                "type": "object",
                "properties": {
                    "players": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "teams": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["players", "teams"],
                "additionalProperties": False,
            }
        ),
        output_schema_name="label_football_entity_groups_v1",
    )

    assert result["output_mode"] == "json_schema"
    assert captured["model"] == "gemma4"
    assert captured["temperature"] == 0.0
    assert captured["top_p"] == 1.0
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["response_format"]["json_schema"]["name"] == "label_football_entity_groups_v1"
    assert captured["response_format"]["json_schema"]["strict"] is True
    assert captured["response_format"]["json_schema"]["schema"]["required"] == ["players", "teams"]


def test_generate_labels_accepts_sampling_overrides(monkeypatch) -> None:
    service = _build_service()
    captured: dict[str, object] = {}

    def fake_post(payload, *, base_url, api_key, timeout_seconds):
        captured.update(payload)
        return {
            "choices": [
                {
                    "message": {"content": '{"players":["Messi"],"teams":["Inter Miami"]}'},
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
        system_prompt="Return grouped entities.",
        article_input="Messi scored for Inter Miami.",
        output_mode="json_schema",
        output_schema_raw=json.dumps(
            {
                "type": "object",
                "properties": {
                    "players": {"type": "array", "items": {"type": "string"}},
                    "teams": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["players", "teams"],
                "additionalProperties": False,
            }
        ),
        temperature=0.2,
        top_p=0.9,
    )

    assert captured["temperature"] == 0.2
    assert captured["top_p"] == 0.9
    assert result["temperature"] == 0.2
    assert result["top_p"] == 0.9


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
                            '{"players":["Messi"],"teams":["Inter Miami"]}'
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
        system_prompt="Return grouped entities.",
        article_input="Messi scored for Inter Miami.",
        output_mode="best_effort_prompt_json",
        output_schema_raw=json.dumps(
            {
                "type": "object",
                "properties": {
                    "players": {"type": "array", "items": {"type": "string"}},
                    "teams": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["players", "teams"],
                "additionalProperties": False,
            }
        ),
    )

    assert result["result"] == {
        "players": ["Messi"],
        "teams": ["Inter Miami"],
    }


def test_generate_labels_trims_whitespace_and_removes_duplicates(monkeypatch) -> None:
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
                                "players": ["  Messi  ", "Messi"],
                                "teams": ["Inter Miami", " Inter Miami ", "Orlando City"],
                            }
                        )
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
        system_prompt="Return grouped entities.",
        article_input="Messi scored for Inter Miami against Orlando City.",
        output_mode="json_schema",
        output_schema_raw=json.dumps(
            {
                "type": "object",
                "properties": {
                    "players": {"type": "array", "items": {"type": "string"}},
                    "teams": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["players", "teams"],
                "additionalProperties": False,
            }
        ),
    )

    assert result["result"] == {
        "players": ["Messi"],
        "teams": ["Inter Miami", "Orlando City"],
    }


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
                            "content": '{"players":["Ronaldo"],"teams":["Inter Miami"]}'
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
                        "content": '{"players":["Messi"],"teams":["Inter Miami"]}'
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
        system_prompt="Return grouped entities.",
        article_input="Messi scored for Inter Miami.",
        output_mode="best_effort_prompt_json",
        output_schema_raw=json.dumps(
            {
                "type": "object",
                "properties": {
                    "players": {"type": "array", "items": {"type": "string"}},
                    "teams": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["players", "teams"],
                "additionalProperties": False,
            }
        ),
        repair_retry_count=1,
    )

    assert len(calls) == 2
    assert result["selected_attempt"] == "repair"
    assert result["result"]["players"] == ["Messi"]


def test_generate_labels_raises_validation_error_after_repair_failure(monkeypatch) -> None:
    service = _build_service()

    monkeypatch.setattr(
        service,
        "_post_chat_completions",
        lambda payload, *, base_url, api_key, timeout_seconds: {
            "choices": [
                {
                    "message": {
                        "content": '{"players":["Ronaldo"],"teams":["Inter Miami"]}'
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
            system_prompt="Return grouped entities.",
            article_input="Messi scored for Inter Miami.",
            output_mode="best_effort_prompt_json",
            output_schema_raw=json.dumps(
                {
                    "type": "object",
                    "properties": {
                        "players": {"type": "array", "items": {"type": "string"}},
                        "teams": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["players", "teams"],
                    "additionalProperties": False,
                }
            ),
            repair_retry_count=1,
        )

    assert any("substring" in item for item in exc_info.value.validation_errors)
