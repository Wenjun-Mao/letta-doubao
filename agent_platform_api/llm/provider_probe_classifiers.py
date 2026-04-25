from __future__ import annotations

from typing import Any

from agent_platform_api.llm.provider_probe_types import ProbedModelResult
from agent_platform_api.services.labeling_helpers import (
    label_probe_success,
    normalize_label_content,
    parse_json_object,
)
from model_router.catalog import RouterModelRecord


def classify_chat_probe_payload(
    record: RouterModelRecord,
    payload: Any,
) -> ProbedModelResult:
    mapped = _classify_common_probe_payload(record, payload)
    if mapped is not None:
        return mapped

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="invalid_payload",
            usable=False,
            http_status=200,
            detail="Response payload did not include any choices.",
        )

    return ProbedModelResult(
        provider_model_id=record.provider_model_id,
        model_type=record.model_type,
        status="ok",
        usable=True,
        http_status=200,
        detail="ok",
    )


def classify_label_probe_payload(
    record: RouterModelRecord,
    payload: Any,
) -> ProbedModelResult:
    mapped = _classify_common_probe_payload(record, payload)
    if mapped is not None:
        return mapped

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="invalid_payload",
            usable=False,
            http_status=200,
            detail="Response payload did not include any choices.",
        )

    choice = choices[0] if isinstance(choices[0], dict) else {}
    message = choice.get("message", {}) if isinstance(choice, dict) else {}
    candidates = [
        normalize_label_content(message.get("content", "")),
        normalize_label_content(message.get("reasoning_content", "")),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = parse_json_object(candidate)
        except ValueError:
            continue
        if label_probe_success(parsed):
            return ProbedModelResult(
                provider_model_id=record.provider_model_id,
                model_type=record.model_type,
                status="ok",
                usable=True,
                http_status=200,
                detail="ok",
            )

    return ProbedModelResult(
        provider_model_id=record.provider_model_id,
        model_type=record.model_type,
        status="invalid_payload",
        usable=False,
        http_status=200,
        detail="Structured output probe did not return the expected grouped JSON result.",
    )


def _classify_common_probe_payload(
    record: RouterModelRecord,
    payload: Any,
) -> ProbedModelResult | None:
    if isinstance(payload, dict) and payload.get("status") == "bad_request":
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="bad_request",
            usable=False,
            http_status=400,
            detail=str(payload.get("detail", "") or ""),
        )
    if isinstance(payload, dict) and payload.get("status") == "not_found":
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="not_found",
            usable=False,
            http_status=404,
            detail=str(payload.get("detail", "") or ""),
        )
    if isinstance(payload, dict) and payload.get("invalid_json"):
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="invalid_json",
            usable=False,
            http_status=200,
            detail=str(payload.get("detail", "") or ""),
        )
    if isinstance(payload, dict) and payload.get("status") == "network_error":
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="network_error",
            usable=False,
            http_status=int(payload.get("http_status", 0) or 0) or None,
            detail=str(payload.get("detail", "") or ""),
        )

    if not isinstance(payload, dict):
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="invalid_payload",
            usable=False,
            detail="Response payload must be an object.",
        )
    return None

