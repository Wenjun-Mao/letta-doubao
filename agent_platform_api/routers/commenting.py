from __future__ import annotations

from fastapi import APIRouter, HTTPException

from agent_platform_api.helpers import normalize_scenario, persona_content_map, prompt_content_map
from agent_platform_api.models.commenting import ApiCommentingGenerateResponse, CommentingGenerateRequest
from agent_platform_api.openapi_metadata import TAG_COMMENT_LAB
from agent_platform_api.runtime import (
    commenting_runtime_defaults,
    commenting_service,
    ensure_platform_api_enabled,
    resolve_comment_model_selection,
)

router = APIRouter()


@router.post(
    "/api/v1/commenting/generate",
    response_model=ApiCommentingGenerateResponse,
    tags=[TAG_COMMENT_LAB],
    summary="Generate a stateless comment for news/comment threads",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "llama_server_comment": {
                            "summary": "Generate with local llama-server",
                            "value": {
                                "scenario": "comment",
                                "input": "Summarize the reader reaction and write one concise editor-style reply.",
                                "prompt_key": "comment_v20260418",
                                "persona_key": "comment_linxiaotang",
                                "model_key": "local_llama_server::gemma4",
                                "max_tokens": 512,
                                "timeout_seconds": 120,
                                "retry_count": 1,
                                "task_shape": "classic",
                                "cache_prompt": False,
                                "temperature": 0.6,
                                "top_p": 1.0,
                                "top_k": 64,
                            },
                        }
                    }
                }
            }
        }
    },
)
async def api_commenting_generate(request: CommentingGenerateRequest):
    ensure_platform_api_enabled()

    resolved_scenario = normalize_scenario(request.scenario, default="comment")
    if resolved_scenario != "comment":
        raise HTTPException(status_code=400, detail="scenario must be 'comment' for this endpoint")

    text = request.input.strip()
    if not text:
        raise HTTPException(status_code=400, detail="input is required")

    if not request.prompt_key.startswith("comment_"):
        raise HTTPException(
            status_code=400,
            detail=f"Prompt key '{request.prompt_key}' is not valid for scenario 'comment'",
        )
    if not request.persona_key.startswith("comment_"):
        raise HTTPException(
            status_code=400,
            detail=f"Persona key '{request.persona_key}' is not valid for scenario 'comment'",
        )

    prompt_map = prompt_content_map("comment")
    persona_map = persona_content_map("comment")
    if request.prompt_key not in prompt_map:
        raise HTTPException(status_code=400, detail=f"Invalid prompt key: {request.prompt_key}")
    if request.persona_key not in persona_map:
        raise HTTPException(status_code=400, detail=f"Invalid persona key: {request.persona_key}")

    try:
        legacy_model_selector = str(request.__dict__.get("model") or "").strip()
        model_selection = resolve_comment_model_selection(
            model_key=(request.model_key or "").strip() or None,
            model_selector=legacy_model_selector or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    persona_text = str(persona_map[request.persona_key] or "")
    try:
        generation_result = commenting_service.generate_comment(
            base_url=str(model_selection.get("base_url", "") or ""),
            model=str(model_selection.get("provider_model_id", "") or ""),
            system_prompt=prompt_map[request.prompt_key],
            persona_prompt=persona_text,
            news_input=text,
            api_key=str(model_selection.get("api_key", "") or ""),
            max_tokens=request.max_tokens,
            timeout_seconds=request.timeout_seconds,
            retry_count=request.retry_count,
            task_shape=request.task_shape,
            source_adapter=str(model_selection.get("source_adapter", "") or ""),
            cache_prompt=request.cache_prompt,
            temperature=(
                request.temperature
                if request.temperature is not None
                else _scenario_sampling_default(model_selection, "comment_lab", "temperature")
            ),
            top_p=(
                request.top_p
                if request.top_p is not None
                else _scenario_sampling_default(model_selection, "comment_lab", "top_p")
            ),
            top_k=(
                request.top_k
                if request.top_k is not None
                else _scenario_sampling_default(model_selection, "comment_lab", "top_k")
            ),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    content = str(generation_result.get("content", "") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Comment provider returned empty content")

    runtime_defaults = commenting_runtime_defaults()
    raw_reply = generation_result.get("raw_reply", {})
    if not isinstance(raw_reply, dict):
        raw_reply = {}
    usage = generation_result.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}
    raw_request = generation_result.get("raw_request", {})
    if not isinstance(raw_request, dict):
        raw_request = {}
    selected_attempt = str(generation_result.get("selected_attempt", "") or "").strip() or "unknown"

    return {
        "scenario": "comment",
        "model_key": str(model_selection.get("model_key", "") or ""),
        "source_id": str(model_selection.get("source_id", "") or ""),
        "source_label": str(model_selection.get("source_label", "") or ""),
        "provider_model_id": str(model_selection.get("provider_model_id", "") or ""),
        "prompt_key": request.prompt_key,
        "persona_key": request.persona_key,
        "model": str(model_selection.get("provider_model_id", "") or ""),
        "content": content,
        "provider": str(model_selection.get("source_label", "") or ""),
        "max_tokens": int(generation_result.get("max_tokens", runtime_defaults.max_tokens)),
        "timeout_seconds": float(generation_result.get("timeout_seconds", runtime_defaults.timeout_seconds)),
        "task_shape": str(generation_result.get("task_shape", runtime_defaults.task_shape)),
        "cache_prompt": bool(generation_result.get("cache_prompt", runtime_defaults.cache_prompt)),
        "temperature": float(generation_result.get("temperature", runtime_defaults.temperature)),
        "top_p": float(generation_result.get("top_p", runtime_defaults.top_p)),
        "top_k": generation_result.get("top_k", runtime_defaults.top_k),
        "content_source": str(generation_result.get("content_source", "") or "") or None,
        "selected_attempt": selected_attempt,
        "finish_reason": str(generation_result.get("finish_reason", "") or "") or None,
        "usage": usage,
        "received_at": str(generation_result.get("received_at", "") or "") or None,
        "raw_request": raw_request,
        "raw_reply": raw_reply,
    }


def _scenario_sampling_default(
    model_selection: dict[str, object],
    scenario: str,
    field: str,
) -> object | None:
    scenario_defaults = model_selection.get("scenario_sampling_defaults", {})
    if isinstance(scenario_defaults, dict):
        defaults = scenario_defaults.get(scenario)
        if isinstance(defaults, dict) and defaults.get(field) is not None:
            return defaults[field]
    sampling_defaults = model_selection.get("sampling_defaults", {})
    if isinstance(sampling_defaults, dict):
        return sampling_defaults.get(field)
    return None

