from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from agent_platform_api.models.labeling import LabelingGenerateRequest
from agent_platform_api.routers import labeling
from utils.labeling_service import LabelingValidationError


def test_labeling_generate_uses_model_key_and_selected_source_connection(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(labeling, "ensure_platform_api_enabled", lambda: None)
    monkeypatch.setattr(
        labeling,
        "resolve_label_model_selection",
        lambda model_key, force_refresh=False: {
            "model_key": "ark::doubao-seed-1-8-251228",
            "source_id": "ark",
            "source_label": "Volcengine Ark",
            "provider_model_id": "doubao-seed-1-8-251228",
            "base_url": "https://ark.example/v3",
            "api_key": "ark-token",
            "structured_output_mode": "strict_json_schema",
        },
    )
    monkeypatch.setattr(
        labeling,
        "prompt_record_map",
        lambda scenario=None: {
            "label_generic_spans_v1": {
                "key": "label_generic_spans_v1",
                "content": "Return spans.",
                "output_schema": '{"type":"object","properties":{"spans":{"type":"array"}},"required":["spans"],"additionalProperties":false}',
            }
        },
    )
    monkeypatch.setattr(
        labeling,
        "label_schema_record_map",
        lambda: {
            "label_span_annotations_v1": {
                "key": "label_span_annotations_v1",
                "schema": {
                    "type": "object",
                    "properties": {"spans": {"type": "array"}},
                    "required": ["spans"],
                    "additionalProperties": False,
                },
            }
        },
    )

    def fake_generate_labels(**kwargs):
        captured.update(kwargs)
        return {
            "result": {
                "spans": [
                    {"label": "PLAYER", "text": "Messi", "start": 0, "end": 5},
                ]
            },
            "output_mode": "strict_json_schema",
            "selected_attempt": "primary",
            "finish_reason": "stop",
            "usage": {},
            "received_at": "2026-04-23T00:00:00+00:00",
            "raw_request": {"model": kwargs["model"]},
            "raw_reply": {"choices": []},
            "validation_errors": [],
        }

    monkeypatch.setattr(labeling.labeling_service, "generate_labels", fake_generate_labels)

    payload = asyncio.run(
        labeling.api_labeling_generate(
            LabelingGenerateRequest(
                input="Messi scored.",
                prompt_key="label_generic_spans_v1",
                model_key="ark::doubao-seed-1-8-251228",
                max_tokens=256,
                timeout_seconds=45,
                repair_retry_count=1,
            )
        )
    )

    assert captured["base_url"] == "https://ark.example/v3"
    assert captured["api_key"] == "ark-token"
    assert captured["model"] == "doubao-seed-1-8-251228"
    assert captured["output_mode"] == "strict_json_schema"
    assert captured["output_schema_name"] == "label_span_annotations_v1"
    assert payload["source_label"] == "Volcengine Ark"
    assert payload["provider_model_id"] == "doubao-seed-1-8-251228"
    assert payload["schema_key"] == "label_span_annotations_v1"
    assert payload["result"]["spans"][0]["text"] == "Messi"


def test_labeling_generate_returns_validation_errors_on_failure(monkeypatch) -> None:
    monkeypatch.setattr(labeling, "ensure_platform_api_enabled", lambda: None)
    monkeypatch.setattr(
        labeling,
        "resolve_label_model_selection",
        lambda model_key, force_refresh=False: {
            "model_key": "local_unsloth::gemma-4-31b-it",
            "source_id": "local_unsloth",
            "source_label": "Local Unsloth",
            "provider_model_id": "gemma-4-31b-it",
            "base_url": "http://127.0.0.1:2234/v1",
            "api_key": "local-token",
            "structured_output_mode": "best_effort_prompt_json",
        },
    )
    monkeypatch.setattr(
        labeling,
        "prompt_record_map",
        lambda scenario=None: {
            "label_generic_spans_v1": {
                "key": "label_generic_spans_v1",
                "content": "Return spans.",
                "output_schema": None,
            }
        },
    )
    monkeypatch.setattr(
        labeling,
        "label_schema_record_map",
        lambda: {
            "label_span_annotations_v1": {
                "key": "label_span_annotations_v1",
                "schema": {
                    "type": "object",
                    "properties": {"spans": {"type": "array"}},
                    "required": ["spans"],
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
                validation_errors=["spans[0].text must exactly match input[start:end]."],
            )
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            labeling.api_labeling_generate(
                LabelingGenerateRequest(
                    input="Messi scored.",
                    prompt_key="label_generic_spans_v1",
                    model_key="local_unsloth::gemma-4-31b-it",
                )
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["validation_errors"] == ["spans[0].text must exactly match input[start:end]."]
