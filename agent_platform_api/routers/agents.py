from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from prompts.persona import HUMAN_TEMPLATE
from agent_platform_api.registries.agent_lifecycle import AgentLifecycleRegistryError

from agent_platform_api.settings import get_settings
from agent_platform_api.helpers import (
    derive_last_interaction_at,
    normalize_scenario,
    normalize_text,
    persona_content_map,
    prompt_content_map,
    serialize_message,
    to_jsonable,
)
from agent_platform_api.mappers import agent_lifecycle_payload
from agent_platform_api.models.agents import (
    AgentCreateRequest,
    ApiAgentCreateResponse,
    ApiAgentDetailsResponse,
    ApiAgentLifecycleResponse,
    ApiAgentListResponse,
    ApiAgentPurgeResponse,
    ApiPersistentStateResponse,
    ApiRawPromptResponse,
)
from agent_platform_api.openapi_metadata import TAG_AGENT_STUDIO, TAG_PLATFORM_CONTROL
from agent_platform_api.runtime import (
    agent_lifecycle_registry,
    agent_platform,
    client,
    ensure_platform_api_enabled,
    fetch_agent_or_404,
    is_not_found_error,
    runtime_options,
)

router = APIRouter()


def _router_llm_config_for_model(
    model_handle: str,
    *,
    temperature: float | None = None,
    top_p: float | None = None,
) -> dict[str, Any] | None:
    handle = str(model_handle or "").strip()
    if not handle.startswith("openai-proxy/") or "::" not in handle:
        return None
    router_base_url = get_settings().model_router_v1_base_url()
    if not router_base_url:
        return None
    provider_model_id = handle.split("/", 1)[1].strip()
    if not provider_model_id:
        return None
    config: dict[str, Any] = {
        "context_window": 16384,
        "model": provider_model_id,
        "model_endpoint_type": "openai",
        "model_endpoint": router_base_url,
        "handle": handle,
        "max_tokens": 16384,
        "parallel_tool_calls": False,
    }
    if temperature is not None:
        config["temperature"] = float(temperature)
    if top_p is not None:
        config["top_p"] = float(top_p)
    return config


@router.get(
    "/api/v1/agents",
    response_model=ApiAgentListResponse,
    tags=[TAG_AGENT_STUDIO],
    summary="List Agent Studio agents",
)
async def api_list_agents(
    limit: int = 100,
    include_last_interaction: bool = False,
    include_archived: bool = False,
):
    """List existing agents so the UI can pull and inspect prior state."""
    ensure_platform_api_enabled()

    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >= 1")
    if limit > 500:
        limit = 500

    archived_agent_ids = agent_lifecycle_registry.archived_agent_ids()
    agents = list(client.agents.list())
    items = []
    for agent in agents:
        agent_id = str(getattr(agent, "id", ""))
        is_archived = agent_id in archived_agent_ids
        if is_archived and not include_archived:
            continue
        last_updated_at = str(getattr(agent, "last_updated_at", ""))
        if include_last_interaction:
            last_interaction_at = derive_last_interaction_at(agent_id, last_updated_at)
        else:
            last_interaction_at = last_updated_at or str(getattr(agent, "created_at", ""))
        items.append(
            {
                "id": agent_id,
                "name": str(getattr(agent, "name", "")),
                "model": str(getattr(agent, "model", "")),
                "created_at": str(getattr(agent, "created_at", "")),
                "last_updated_at": last_updated_at,
                "last_interaction_at": last_interaction_at,
                "archived": is_archived,
            }
        )

    items.sort(key=lambda item: (item["last_updated_at"] or item["created_at"]), reverse=True)
    return {
        "total": len(items),
        "items": items[:limit],
    }


@router.post(
    "/api/v1/agents",
    response_model=ApiAgentCreateResponse,
    tags=[TAG_AGENT_STUDIO],
    summary="Create an Agent Studio agent",
)
async def api_create_agent(request: AgentCreateRequest):
    ensure_platform_api_enabled()
    resolved_scenario = normalize_scenario(request.scenario)
    if resolved_scenario != "chat":
        raise HTTPException(
            status_code=400,
            detail=(
                "/api/v1/agents supports only scenario='chat'. "
                "Use /api/v1/commenting/generate for stateless comments "
                "or /api/v1/labeling/generate for stateless labeling."
            ),
        )

    model_options, embedding_options = runtime_options("chat")
    prompt_map = prompt_content_map("chat")
    persona_map = persona_content_map("chat")
    allowed_models = {option["key"] for option in model_options}
    allowed_embeddings = {option["key"] for option in embedding_options}

    if not request.model.strip():
        raise HTTPException(status_code=400, detail="Model is required. Please choose one.")
    if request.model not in allowed_models:
        raise HTTPException(status_code=400, detail=f"Invalid model: {request.model}")
    if not request.prompt_key.startswith("chat_"):
        raise HTTPException(
            status_code=400,
            detail=f"Prompt key '{request.prompt_key}' is not valid for scenario 'chat'",
        )
    if not request.persona_key.startswith("chat_"):
        raise HTTPException(
            status_code=400,
            detail=f"Persona key '{request.persona_key}' is not valid for scenario 'chat'",
        )
    if request.prompt_key not in prompt_map:
        raise HTTPException(status_code=400, detail=f"Invalid prompt key: {request.prompt_key}")
    if request.persona_key not in persona_map:
        raise HTTPException(status_code=400, detail=f"Invalid persona key: {request.persona_key}")
    if request.embedding and request.embedding not in allowed_embeddings:
        raise HTTPException(status_code=400, detail=f"Invalid embedding handle: {request.embedding}")

    create_args: dict[str, Any] = {
        "name": request.name,
        "system": prompt_map[request.prompt_key],
        "model": request.model,
        "timezone": "Asia/Shanghai",
        "context_window_limit": 16384,
        "memory_blocks": [
            {
                "label": "persona",
                "value": persona_map[request.persona_key],
            },
            {
                "label": "human",
                "value": HUMAN_TEMPLATE,
            },
        ],
    }
    if request.embedding:
        create_args["embedding"] = request.embedding
    router_llm_config = _router_llm_config_for_model(
        request.model,
        temperature=request.temperature,
        top_p=request.top_p,
    )
    if router_llm_config is not None:
        create_args["llm_config"] = router_llm_config

    try:
        agent = client.agents.create(**create_args)
    except Exception as exc:
        error_text = str(exc)
        if "Handle" in error_text and "not found" in error_text:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{error_text}. This handle is not registered on the current Letta server. "
                    "If you want LM Studio and Doubao in one server, use a combined env profile (for example .env)."
                ),
            ) from exc
        raise HTTPException(status_code=400, detail=error_text) from exc

    return {
        "id": agent.id,
        "name": agent.name,
        "scenario": "chat",
        "model": request.model,
        "embedding": request.embedding,
        "prompt_key": request.prompt_key,
        "persona_key": request.persona_key,
    }


@router.post(
    "/api/v1/platform/agents/{agent_id}/archive",
    response_model=ApiAgentLifecycleResponse,
    tags=[TAG_PLATFORM_CONTROL],
    summary="Archive agent (soft delete)",
)
async def api_platform_archive_agent(agent_id: str):
    ensure_platform_api_enabled()
    resolved_agent_id = agent_id.strip()
    if not resolved_agent_id:
        raise HTTPException(status_code=400, detail="agent_id is required")

    agent = fetch_agent_or_404(resolved_agent_id)
    try:
        archived = agent_lifecycle_registry.archive_agent(
            agent_id=resolved_agent_id,
            name=str(getattr(agent, "name", "")),
            model=str(getattr(agent, "model", "")),
        )
    except AgentLifecycleRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return agent_lifecycle_payload(
        archived,
        fallback_name=str(getattr(agent, "name", "")),
        fallback_model=str(getattr(agent, "model", "")),
    )


@router.post(
    "/api/v1/platform/agents/{agent_id}/restore",
    response_model=ApiAgentLifecycleResponse,
    tags=[TAG_PLATFORM_CONTROL],
    summary="Restore archived agent",
)
async def api_platform_restore_agent(agent_id: str):
    ensure_platform_api_enabled()
    resolved_agent_id = agent_id.strip()
    if not resolved_agent_id:
        raise HTTPException(status_code=400, detail="agent_id is required")

    archived_record = agent_lifecycle_registry.get_record(resolved_agent_id)
    if not archived_record or not bool(archived_record.get("archived", False)):
        raise HTTPException(status_code=400, detail=f"Agent '{resolved_agent_id}' is not archived")

    agent = fetch_agent_or_404(resolved_agent_id)
    try:
        restored = agent_lifecycle_registry.restore_agent(resolved_agent_id)
    except AgentLifecycleRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return agent_lifecycle_payload(
        restored,
        fallback_name=str(getattr(agent, "name", "")),
        fallback_model=str(getattr(agent, "model", "")),
    )


def purge_archived_agent(agent_id: str) -> dict[str, Any]:
    resolved_agent_id = agent_id.strip()
    if not resolved_agent_id:
        raise HTTPException(status_code=400, detail="agent_id is required")

    archived_record = agent_lifecycle_registry.get_record(resolved_agent_id)
    if not archived_record or not bool(archived_record.get("archived", False)):
        raise HTTPException(
            status_code=400,
            detail=f"Agent '{resolved_agent_id}' must be archived before purge",
        )

    try:
        agent_platform.delete_agent(agent_id=resolved_agent_id)
    except Exception as exc:
        if not is_not_found_error(exc):
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        agent_lifecycle_registry.purge_agent(resolved_agent_id)
    except AgentLifecycleRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "ok": True,
        "id": resolved_agent_id,
        "kind": "agent",
    }


@router.delete(
    "/api/v1/platform/agents/{agent_id}/purge",
    response_model=ApiAgentPurgeResponse,
    tags=[TAG_PLATFORM_CONTROL],
    summary="Purge archived agent (hard delete)",
)
async def api_platform_purge_agent(agent_id: str):
    ensure_platform_api_enabled()
    return purge_archived_agent(agent_id)


@router.delete(
    "/api/v1/agents/{agent_id}",
    response_model=ApiAgentPurgeResponse,
    tags=[TAG_PLATFORM_CONTROL],
    summary="Delete archived agent (hard delete)",
)
async def api_delete_agent(agent_id: str):
    ensure_platform_api_enabled()
    return purge_archived_agent(agent_id)


@router.get(
    "/api/v1/agents/{agent_id}/details",
    response_model=ApiAgentDetailsResponse,
    tags=[TAG_AGENT_STUDIO],
    summary="Get Agent Studio agent details",
)
async def api_get_agent_details(agent_id: str):
    ensure_platform_api_enabled()

    agent = client.agents.retrieve(agent_id=agent_id)
    tools_raw = list(client.agents.tools.list(agent_id=agent.id))
    tools = {tool.name: tool.description for tool in tools_raw}
    blocks = client.agents.blocks.list(agent_id=agent_id)
    memory = {block.label: block.value for block in blocks}

    last_updated_at = str(getattr(agent, "last_updated_at", ""))
    last_interaction_at = derive_last_interaction_at(agent_id, last_updated_at)
    return {
        "id": getattr(agent, "id", agent_id),
        "name": getattr(agent, "name", "Unknown"),
        "agent_type": str(getattr(agent, "agent_type", "Unknown")),
        "model": getattr(agent, "model", "Unknown"),
        "embedding": getattr(agent, "embedding", None),
        "llm_config": to_jsonable(getattr(agent, "llm_config", None)),
        "embedding_config": to_jsonable(getattr(agent, "embedding_config", None)),
        "tool_rules": to_jsonable(getattr(agent, "tool_rules", None)),
        "description": getattr(agent, "description", None),
        "created_at": str(getattr(agent, "created_at", "")),
        "last_updated_at": last_updated_at,
        "last_interaction_at": last_interaction_at,
        "context_window_limit": getattr(agent, "context_window_limit", None),
        "tools": tools,
        "system": getattr(agent, "system", "Unknown"),
        "memory": memory,
    }


@router.get(
    "/api/v1/agents/{agent_id}/persistent_state",
    response_model=ApiPersistentStateResponse,
    tags=[TAG_AGENT_STUDIO],
    summary="Get persisted Agent Studio state",
)
async def api_get_agent_persistent_state(agent_id: str, limit: int = 120, include_system: bool = False):
    """
    Returns persisted state from Letta backend storage (Postgres/pgvector via Letta API):
    - agent metadata
    - memory blocks
    - attached tools
    - persisted conversation history
    """
    ensure_platform_api_enabled()

    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >= 1")
    if limit > 500:
        limit = 500

    agent = client.agents.retrieve(agent_id=agent_id)
    blocks = list(client.agents.blocks.list(agent_id=agent_id))
    tools_raw = list(client.agents.tools.list(agent_id=agent_id))
    messages = list(client.agents.messages.list(agent_id=agent_id))

    serialized_messages = []
    type_counts: dict[str, int] = {}
    for msg in messages:
        message_type = str(getattr(msg, "message_type", "unknown"))
        if not include_system and message_type == "system_message":
            continue

        payload = serialize_message(msg)
        serialized_messages.append(payload)
        type_counts[message_type] = type_counts.get(message_type, 0) + 1

    total_persisted = len(serialized_messages)
    if len(serialized_messages) > limit:
        serialized_messages = serialized_messages[-limit:]

    memory_blocks = [
        {
            "label": getattr(block, "label", ""),
            "description": getattr(block, "description", ""),
            "limit": getattr(block, "limit", None),
            "value": getattr(block, "value", ""),
        }
        for block in blocks
    ]
    tool_entries = [
        {
            "id": getattr(tool, "id", ""),
            "name": getattr(tool, "name", ""),
            "description": getattr(tool, "description", ""),
        }
        for tool in tools_raw
    ]

    return {
        "source": "letta_backend_persistent_storage",
        "agent": {
            "id": getattr(agent, "id", agent_id),
            "name": getattr(agent, "name", ""),
            "agent_type": str(getattr(agent, "agent_type", "")),
            "model": getattr(agent, "model", ""),
            "embedding": getattr(agent, "embedding", None),
            "created_at": str(getattr(agent, "created_at", "")),
            "last_updated_at": str(getattr(agent, "last_updated_at", "")),
            "context_window_limit": getattr(agent, "context_window_limit", None),
            "tool_rules": normalize_text(getattr(agent, "tool_rules", None)),
        },
        "memory_blocks": memory_blocks,
        "tools": tool_entries,
        "conversation_history": {
            "total_persisted": total_persisted,
            "displayed": len(serialized_messages),
            "limit": limit,
            "counts_by_type": type_counts,
            "items": serialized_messages,
        },
    }


@router.get(
    "/api/v1/agents/{agent_id}/raw_prompt",
    response_model=ApiRawPromptResponse,
    tags=[TAG_AGENT_STUDIO],
    summary="Get raw prompt messages for an Agent Studio agent",
)
async def api_get_raw_prompt(agent_id: str):
    ensure_platform_api_enabled()

    messages = list(client.agents.messages.list(agent_id=agent_id))
    recent_messages = messages[-10:] if len(messages) >= 10 else messages
    formatted_messages = []
    for msg in recent_messages:
        content = getattr(msg, "content", "")
        if not content:
            content = getattr(msg, "reasoning", str(msg))
        role = getattr(msg, "role", getattr(msg, "message_type", "unknown"))
        formatted_messages.append({"role": role, "content": normalize_text(content)})
    return {"messages": formatted_messages}

