from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from agent_platform_api.models.labeling import LabelingGenerateRequest
from agent_platform_api.routers import labeling
from agent_platform_api.services.labeling import LabelingValidationError


def test_labeling_generate_uses_model_key_and_selected_source_connection(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(labeling, "ensure_platform_api_enabled", lambda: None)
    monkeypatch.setattr(
        labeling,
        "resolve_label_model_selection",
        lambda model_key, force_refresh=False: {
            "model_key": "local_llama_server::gemma4",
            "source_id": "local_llama_server",
            "source_label": "Local llama-server",
            "provider_model_id": "gemma4",
            "base_url": "http://127.0.0.1:8081/v1",
            "api_key": "local-token",
            "structured_output_mode": "json_schema",
        },
    )
    monkeypatch.setattr(
        labeling,
        "prompt_record_map",
        lambda scenario=None: {
            "label_generic_entities_v1": {
                "key": "label_generic_entities_v1",
                "content": "Return grouped entities.",
                "output_schema": '{"type":"object","properties":{"people":{"type":"array"}},"required":["people"],"additionalProperties":false}',
            }
        },
    )
    monkeypatch.setattr(
        labeling,
        "label_schema_record_map",
        lambda: {
            "label_entity_groups_v1": {
                "key": "label_entity_groups_v1",
                "schema": {
                    "type": "object",
                    "properties": {
                        "people": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["people"],
                    "additionalProperties": False,
                },
            }
        },
    )

    def fake_generate_labels(**kwargs):
        captured.update(kwargs)
        return {
            "result": {
                "people": ["Messi"],
            },
            "output_mode": "json_schema",
            "selected_attempt": "primary",
            "finish_reason": "stop",
            "usage": {},
            "received_at": "2026-04-23T00:00:00+00:00",
            "raw_request": {"model": kwargs["model"]},
            "raw_reply": {"choices": []},
            "validation_errors": [],
            "temperature": kwargs["temperature"],
            "top_p": kwargs["top_p"],
        }

    monkeypatch.setattr(labeling.labeling_service, "generate_labels", fake_generate_labels)

    payload = asyncio.run(
        labeling.api_labeling_generate(
            LabelingGenerateRequest(
                input="Messi scored.",
                prompt_key="label_generic_entities_v1",
                model_key="local_llama_server::gemma4",
                max_tokens=256,
                timeout_seconds=45,
                repair_retry_count=1,
                temperature=0.2,
                top_p=0.9,
            )
        )
    )

    assert captured["base_url"] == "http://127.0.0.1:8081/v1"
    assert captured["api_key"] == "local-token"
    assert captured["model"] == "gemma4"
    assert captured["temperature"] == 0.2
    assert captured["top_p"] == 0.9
    assert captured["output_mode"] == "json_schema"
    assert captured["output_schema_name"] == "label_entity_groups_v1"
    assert payload["source_label"] == "Local llama-server"
    assert payload["provider_model_id"] == "gemma4"
    assert payload["schema_key"] == "label_entity_groups_v1"
    assert payload["temperature"] == 0.2
    assert payload["top_p"] == 0.9
    assert payload["result"]["people"] == ["Messi"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("temperature", -0.1),
        ("temperature", 2.1),
        ("top_p", 0),
        ("top_p", 1.1),
    ],
)
def test_labeling_generate_request_rejects_invalid_sampling_ranges(field: str, value: float) -> None:
    kwargs = {
        "input": "Messi scored.",
        "prompt_key": "label_generic_entities_v1",
        "model_key": "local_llama_server::gemma4",
        field: value,
    }
    with pytest.raises(ValidationError):
        LabelingGenerateRequest(**kwargs)


def test_labeling_generate_returns_validation_errors_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(labeling, "ensure_platform_api_enabled", lambda: None)
    monkeypatch.setattr(
        labeling,
        "resolve_label_model_selection",
        lambda model_key, force_refresh=False: {
            "model_key": "local_llama_server::gemma4",
            "source_id": "local_llama_server",
            "source_label": "Local llama-server",
            "provider_model_id": "gemma4",
            "base_url": "http://127.0.0.1:8081/v1",
            "api_key": "local-token",
            "structured_output_mode": "json_schema",
        },
    )
    monkeypatch.setattr(
        labeling,
        "prompt_record_map",
        lambda scenario=None: {
            "label_generic_entities_v1": {
                "key": "label_generic_entities_v1",
                "content": "Return grouped entities.",
                "output_schema": None,
            }
        },
    )
    monkeypatch.setattr(
        labeling,
        "label_schema_record_map",
        lambda: {
            "label_entity_groups_v1": {
                "key": "label_entity_groups_v1",
                "schema": {
                    "type": "object",
                    "properties": {
                        "people": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["people"],
                    "additionalProperties": False,
                },
            }
        },
    )
    monkeypatch.setattr(
        labeling.labeling_service,
        "generate_labels",
        lambda **kwargs: (_ for _ in ()).throw(
            LabelingValidationError(
                "Label provider returned invalid structured output.",
                validation_errors=["people[0] must exactly match a substring in the input article."],
            )
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            labeling.api_labeling_generate(
                LabelingGenerateRequest(
                    input="Messi scored.",
                    prompt_key="label_generic_entities_v1",
                    model_key="local_llama_server::gemma4",
                )
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["validation_errors"] == [
        "people[0] must exactly match a substring in the input article."
    ]
