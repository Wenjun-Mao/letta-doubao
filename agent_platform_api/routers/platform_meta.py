from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException

from agent_platform_api.helpers import (
    active_persona_records,
    active_prompt_records,
    normalize_scenario,
    persona_option_entries,
    prompt_option_entries,
    read_prompt_persona_revisions,
    resolve_default_persona_key,
    resolve_default_prompt_key,
)
from agent_platform_api.models.platform import (
    ApiPlatformCapabilitiesResponse,
    ApiPlatformModelCatalogResponse,
    ApiPlatformToolListResponse,
    ApiPlatformToolTestInvokeResponse,
    PlatformToolTestInvokeRequest,
)
from agent_platform_api.models.templates import (
    ApiPromptPersonaMetadataResponse,
    ApiPromptPersonaRevisionsResponse,
)
from agent_platform_api.runtime import (
    agent_platform,
    client,
    custom_tool_registry,
    ensure_agent_not_archived,
    ensure_platform_api_enabled,
    is_truthy,
    model_catalog,
    missing_platform_capabilities,
    platform_api_enabled,
)

router = APIRouter()


@router.get(
    "/api/v1/platform/capabilities",
    response_model=ApiPlatformCapabilitiesResponse,
    tags=["platform-meta"],
    summary="Get platform capability matrix",
)
async def api_platform_capabilities():
    capabilities = agent_platform.capabilities()
    return {
        "enabled": platform_api_enabled(),
        "strict_mode": is_truthy(os.getenv("AGENT_PLATFORM_STRICT_CAPABILITIES")),
        "missing_required": missing_platform_capabilities(capabilities),
        **capabilities,
    }


@router.get(
    "/api/v1/platform/model-catalog",
    response_model=ApiPlatformModelCatalogResponse,
    tags=["platform-meta"],
    summary="Get unified model-catalog diagnostics",
)
async def api_platform_model_catalog(refresh: bool = False):
    ensure_platform_api_enabled()
    return model_catalog(force_refresh=refresh)


@router.get(
    "/api/v1/platform/tools",
    response_model=ApiPlatformToolListResponse,
    tags=["platform-tools"],
    summary="List tools for Toolbench discovery",
)
async def api_platform_list_tools(search: str = "", limit: int = 100, agent_id: str | None = None):
    ensure_platform_api_enabled()

    resolved_limit = max(1, min(limit, 500))
    try:
        tools = agent_platform.list_available_tools(search=(search or "").strip() or None, limit=resolved_limit)
        managed_entries = {
            str(entry.get("tool_id", "") or ""): entry
            for entry in custom_tool_registry.list_tools(include_archived=False, include_source=False)
            if str(entry.get("tool_id", "") or "").strip()
        }

        attached_ids: set[str] = set()
        if agent_id:
            attached_ids = {
                str(getattr(tool, "id", "") or "")
                for tool in list(client.agents.tools.list(agent_id=agent_id))
                if str(getattr(tool, "id", "") or "").strip()
            }

        for tool in tools:
            tool_id = str(tool.get("id", "") or "")
            managed_entry = managed_entries.get(tool_id)
            tool["attached_to_agent"] = bool(agent_id and tool_id in attached_ids)
            tool["managed"] = bool(managed_entry)
            tool["read_only"] = not bool(managed_entry)
            tool["archived"] = False
            tool["slug"] = str(managed_entry.get("slug", "") or "") if managed_entry else None

        return {
            "total": len(tools),
            "search": (search or "").strip(),
            "limit": resolved_limit,
            "agent_id": agent_id,
            "items": tools,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/api/v1/platform/tools/test-invoke",
    response_model=ApiPlatformToolTestInvokeResponse,
    tags=["platform-tools"],
    summary="Invoke a runtime message to validate tool-call behavior",
)
async def api_platform_tool_test_invoke(request: PlatformToolTestInvokeRequest):
    ensure_platform_api_enabled()

    agent_id = request.agent_id.strip()
    text = request.input.strip()
    expected_tool_name = (request.expected_tool_name or "").strip()

    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id is required")
    if not text:
        raise HTTPException(status_code=400, detail="input is required")

    ensure_agent_not_archived(agent_id)

    try:
        payload = agent_platform.send_runtime_message(
            agent_id=agent_id,
            message=text,
            override_model=(request.override_model or "").strip() or None,
            override_system=(request.override_system or "").strip() or None,
            timeout_seconds=request.timeout_seconds,
            retry_count=request.retry_count,
        )
        result = payload.get("result", {}) if isinstance(payload, dict) else {}
        sequence = result.get("sequence", []) if isinstance(result, dict) else []
        tool_calls = [
            step
            for step in sequence
            if str(step.get("type", "") or "").strip().lower() == "tool_call"
        ]
        tool_returns = [
            step
            for step in sequence
            if str(step.get("type", "") or "").strip().lower() == "tool_return"
        ]

        expected_matched: bool | None = None
        if expected_tool_name:
            expected_lower = expected_tool_name.lower()
            expected_matched = any(
                str(step.get("name", "") or "").strip().lower() == expected_lower
                for step in tool_calls
            )

        return {
            "agent_id": agent_id,
            "input": text,
            "expected_tool_name": expected_tool_name or None,
            "expected_tool_matched": expected_matched,
            "tool_call_count": len(tool_calls),
            "tool_return_count": len(tool_returns),
            "result": result,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/api/v1/platform/metadata/prompts-personas",
    response_model=ApiPromptPersonaMetadataResponse,
    tags=["platform-meta"],
    summary="Get prompt and persona metadata",
)
async def api_platform_prompt_persona_metadata(scenario: str = "chat"):
    ensure_platform_api_enabled()
    resolved_scenario = normalize_scenario(scenario)

    prompts: list[dict[str, Any]] = []
    for record in active_prompt_records(resolved_scenario):
        prompts.append(
            {
                "scenario": str(record.get("scenario", "") or resolved_scenario),
                "key": str(record.get("key", "") or ""),
                "label": str(record.get("label", "") or ""),
                "description": str(record.get("description", "") or ""),
                "preview": str(record.get("preview", "") or ""),
                "length": int(record.get("length", 0) or 0),
            }
        )

    personas: list[dict[str, Any]] = []
    for record in active_persona_records(resolved_scenario):
        personas.append(
            {
                "scenario": str(record.get("scenario", "") or resolved_scenario),
                "key": str(record.get("key", "") or ""),
                "preview": str(record.get("preview", "") or ""),
                "length": int(record.get("length", 0) or 0),
            }
        )

    default_prompt_key = resolve_default_prompt_key(prompt_option_entries(resolved_scenario), resolved_scenario)
    default_persona_key = resolve_default_persona_key(
        persona_option_entries(resolved_scenario),
        resolved_scenario,
    )
    return {
        "defaults": {
            "scenario": resolved_scenario,
            "prompt_key": default_prompt_key,
            "persona_key": default_persona_key,
        },
        "prompts": prompts,
        "personas": personas,
    }


@router.get(
    "/api/v1/platform/metadata/prompts-personas/revisions",
    response_model=ApiPromptPersonaRevisionsResponse,
    tags=["platform-meta"],
    summary="Get prompt/persona revision history timeline",
)
async def api_platform_prompt_persona_revisions(
    agent_id: str | None = None,
    field: str | None = None,
    limit: int = 80,
):
    ensure_platform_api_enabled()

    resolved_field = (field or "").strip().lower() or None
    if resolved_field and resolved_field not in {"system", "persona", "human"}:
        raise HTTPException(status_code=400, detail="field must be one of: system, persona, human")

    resolved_limit = max(1, min(limit, 500))
    resolved_agent_id = (agent_id or "").strip() or None
    items = read_prompt_persona_revisions(
        agent_id=resolved_agent_id,
        field=resolved_field,
        limit=resolved_limit,
    )
    return {
        "total": len(items),
        "limit": resolved_limit,
        "agent_id": resolved_agent_id,
        "field": resolved_field,
        "items": items,
    }

