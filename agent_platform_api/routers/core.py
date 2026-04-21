from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException

from agent_platform_api.helpers import (
    is_datetime_query,
    normalize_scenario,
    persona_option_entries,
    prompt_option_entries,
    resolve_default_persona_key,
    resolve_default_prompt_key,
    runtime_datetime_system_hint,
)
from agent_platform_api.models.agents import ApiChatResponse, ApiOptionsResponse, ChatRequest
from agent_platform_api.runtime import (
    DEFAULT_EMBEDDING,
    agent_platform,
    commenting_runtime_defaults,
    ensure_agent_not_archived,
    ensure_platform_api_enabled,
    runtime_options,
)

router = APIRouter()


@router.get("/api/v1/options", response_model=ApiOptionsResponse)
async def api_get_options(refresh: bool = False, scenario: str = "chat"):
    ensure_platform_api_enabled()
    resolved_scenario = normalize_scenario(scenario)

    model_options, embedding_options = runtime_options(force_refresh=refresh)
    prompt_options = prompt_option_entries(resolved_scenario)
    persona_options = persona_option_entries(resolved_scenario)
    default_model = ""
    default_prompt_key = resolve_default_prompt_key(prompt_options, resolved_scenario)
    default_persona_key = resolve_default_persona_key(persona_options, resolved_scenario)

    default_embedding = (
        os.getenv("LETTA_DEFAULT_EMBEDDING_HANDLE")
        or os.getenv("LETTA_EMBEDDING_HANDLE")
        or DEFAULT_EMBEDDING
    )
    if default_embedding and not any(option["key"] == default_embedding for option in embedding_options):
        default_embedding = ""

    for option in embedding_options:
        option["is_default"] = bool(default_embedding and option["key"] == default_embedding)

    return {
        "scenario": resolved_scenario,
        "models": model_options,
        "embeddings": embedding_options,
        "prompts": prompt_options,
        "personas": persona_options,
        "defaults": {
            "scenario": resolved_scenario,
            "model": default_model,
            "prompt_key": default_prompt_key,
            "persona_key": default_persona_key,
            "embedding": default_embedding,
        },
        "commenting": commenting_runtime_defaults(),
    }


@router.post("/api/v1/chat", response_model=ApiChatResponse)
async def api_chat(request: ChatRequest):
    ensure_platform_api_enabled()
    ensure_agent_not_archived(request.agent_id)

    try:
        return agent_platform.send_chat_message(
            agent_id=request.agent_id,
            message=request.message,
            datetime_system_hint=runtime_datetime_system_hint() if is_datetime_query(request.message) else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

