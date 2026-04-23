from __future__ import annotations

from fastapi import APIRouter, HTTPException

from agent_platform_api.helpers import normalize_scenario, prompt_record_map
from agent_platform_api.models.labeling import ApiLabelingGenerateResponse, LabelingGenerateRequest
from agent_platform_api.runtime import (
    ensure_platform_api_enabled,
    labeling_service,
    label_schema_record_map,
    resolve_label_model_selection,
)
from utils.labeling_service import LabelingValidationError

router = APIRouter()


@router.post(
    "/api/v1/labeling/generate",
    response_model=ApiLabelingGenerateResponse,
    tags=["labeling"],
    summary="Generate stateless span annotations for an input article",
)
async def api_labeling_generate(request: LabelingGenerateRequest):
    ensure_platform_api_enabled()

    resolved_scenario = normalize_scenario(request.scenario, default="label")
    if resolved_scenario != "label":
        raise HTTPException(status_code=400, detail="scenario must be 'label' for this endpoint")

    text = request.input.strip()
    if not text:
        raise HTTPException(status_code=400, detail="input is required")
    if not request.prompt_key.startswith("label_"):
        raise HTTPException(
            status_code=400,
            detail=f"Prompt key '{request.prompt_key}' is not valid for scenario 'label'",
        )

    prompt_map = prompt_record_map("label")
    prompt_record = prompt_map.get(request.prompt_key)
    if prompt_record is None:
        raise HTTPException(status_code=400, detail=f"Invalid prompt key: {request.prompt_key}")
    schema_map = label_schema_record_map()
    schema_record = schema_map.get(request.schema_key)
    if schema_record is None:
        raise HTTPException(status_code=400, detail=f"Invalid schema key: {request.schema_key}")

    try:
        model_selection = resolve_label_model_selection(model_key=request.model_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    output_mode = str(model_selection.get("structured_output_mode", "") or "").strip()
    try:
        generation_result = labeling_service.generate_labels(
            base_url=str(model_selection.get("base_url", "") or ""),
            model=str(model_selection.get("provider_model_id", "") or ""),
            api_key=str(model_selection.get("api_key", "") or ""),
            system_prompt=str(prompt_record.get("content", "") or ""),
            article_input=text,
            output_schema_raw=json_dumps_schema(schema_record.get("schema")),
            output_schema_name=request.schema_key,
            output_mode=output_mode,
            max_tokens=request.max_tokens,
            timeout_seconds=request.timeout_seconds,
            repair_retry_count=request.repair_retry_count,
        )
    except LabelingValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": str(exc),
                "validation_errors": exc.validation_errors,
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    raw_request = generation_result.get("raw_request", {})
    if not isinstance(raw_request, dict):
        raw_request = {}
    raw_reply = generation_result.get("raw_reply", {})
    if not isinstance(raw_reply, dict):
        raw_reply = {}
    usage = generation_result.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}

    return {
        "scenario": "label",
        "model_key": str(model_selection.get("model_key", "") or ""),
        "source_id": str(model_selection.get("source_id", "") or ""),
        "source_label": str(model_selection.get("source_label", "") or ""),
        "provider_model_id": str(model_selection.get("provider_model_id", "") or ""),
        "prompt_key": request.prompt_key,
        "schema_key": request.schema_key,
        "output_mode": output_mode,
        "selected_attempt": str(generation_result.get("selected_attempt", "") or "primary"),
        "result": generation_result.get("result", {"spans": []}),
        "finish_reason": str(generation_result.get("finish_reason", "") or "") or None,
        "usage": usage,
        "received_at": str(generation_result.get("received_at", "") or "") or None,
        "raw_request": raw_request,
        "raw_reply": raw_reply,
        "validation_errors": generation_result.get("validation_errors", []) or [],
    }


def json_dumps_schema(value: object) -> str | None:
    import json

    if not isinstance(value, dict):
        return None
    return json.dumps(value, ensure_ascii=False)
