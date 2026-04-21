from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException

from agent_platform_api.helpers import normalize_scenario, persona_content_map, prompt_content_map
from agent_platform_api.models.commenting import ApiCommentingGenerateResponse, CommentingGenerateRequest
from agent_platform_api.runtime import (
    commenting_runtime_defaults,
    commenting_service,
    ensure_platform_api_enabled,
    runtime_options,
)

router = APIRouter()


@router.post(
    "/api/v1/commenting/generate",
    response_model=ApiCommentingGenerateResponse,
    tags=["commenting"],
    summary="Generate a stateless comment for news/comment threads",
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

    model_options, _ = runtime_options()
    allowed_models = {
        str(option.get("key", "") or "")
        for option in model_options
        if str(option.get("key", "") or "").strip()
    }
    model_handle = (request.model or "").strip() or os.getenv("AGENT_PLATFORM_COMMENTING_DEFAULT_MODEL", "").strip()
    if not model_handle and model_options:
        model_handle = str(model_options[0].get("key", "") or "")
    if not model_handle:
        raise HTTPException(status_code=400, detail="No model available for commenting generation")

    if allowed_models and model_handle not in allowed_models:
        normalized_requested_model = commenting_service._resolve_provider_model(model_handle)
        matched_model_handle = next(
            (
                candidate
                for candidate in allowed_models
                if commenting_service._resolve_provider_model(candidate) == normalized_requested_model
            ),
            "",
        )
        if matched_model_handle:
            model_handle = matched_model_handle
        else:
            raise HTTPException(status_code=400, detail=f"Invalid model: {model_handle}")

    persona_text = str(persona_map[request.persona_key] or "")
    try:
        generation_result = commenting_service.generate_comment(
            model=model_handle,
            system_prompt=prompt_map[request.prompt_key],
            persona_prompt=persona_text,
            news_input=text,
            max_tokens=request.max_tokens,
            timeout_seconds=request.timeout_seconds,
            task_shape=request.task_shape,
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
        "prompt_key": request.prompt_key,
        "persona_key": request.persona_key,
        "model": model_handle,
        "content": content,
        "provider": commenting_service.provider_name,
        "max_tokens": int(generation_result.get("max_tokens", runtime_defaults.max_tokens)),
        "timeout_seconds": float(generation_result.get("timeout_seconds", runtime_defaults.timeout_seconds)),
        "task_shape": str(generation_result.get("task_shape", runtime_defaults.task_shape)),
        "content_source": str(generation_result.get("content_source", "") or "") or None,
        "selected_attempt": selected_attempt,
        "finish_reason": str(generation_result.get("finish_reason", "") or "") or None,
        "usage": usage,
        "received_at": str(generation_result.get("received_at", "") or "") or None,
        "raw_request": raw_request,
        "raw_reply": raw_reply,
    }

