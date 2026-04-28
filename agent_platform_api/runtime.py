from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException

from agent_platform_api.dependencies import (
    APP_VERSION,
    PROJECT_ROOT,
    REVISION_LOG_DIR,
    REVISION_LOG_FILE,
    agent_lifecycle_registry,
    agent_platform,
    client,
    commenting_service,
    custom_tool_registry,
    label_schema_registry,
    labeling_service,
    model_router_client,
    prompt_persona_registry,
    test_orchestrator,
)
from agent_platform_api.options import (
    DEFAULT_EMBEDDING,
    DEFAULT_MODEL,
    SCENARIO_DEFAULTS,
    active_label_schema_records,
    commenting_runtime_defaults,
    dedupe_options,
    invalidate_options_cache,
    label_schema_option_entries,
    label_schema_record_map,
    labeling_runtime_defaults,
    model_catalog,
    resolve_comment_model_selection,
    resolve_default_label_schema_key,
    resolve_label_model_selection,
    runtime_options,
)

MANAGED_TOOL_TAG = "ade:managed"


def is_truthy(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def platform_api_enabled() -> bool:
    return is_truthy(os.getenv("AGENT_PLATFORM_API_ENABLED", "1"))


def ensure_platform_api_enabled() -> None:
    if platform_api_enabled():
        return
    raise HTTPException(
        status_code=503,
        detail="Agent Platform API is disabled by AGENT_PLATFORM_API_ENABLED.",
    )


def is_not_found_error(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return "not found" in text or "404" in text


def fetch_agent_or_404(agent_id: str) -> Any:
    try:
        return client.agents.retrieve(agent_id=agent_id)
    except Exception as exc:
        if is_not_found_error(exc):
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found") from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def ensure_agent_not_archived(agent_id: str) -> None:
    record = agent_lifecycle_registry.get_record(agent_id)
    if record and bool(record.get("archived", False)):
        raise HTTPException(
            status_code=410,
            detail=f"Agent '{agent_id}' is archived. Restore it before using this endpoint.",
        )


def missing_platform_capabilities(capabilities: dict[str, Any]) -> list[str]:
    missing: list[str] = []

    runtime = capabilities.get("runtime", {})
    if not runtime.get("per_request_model_override") and not runtime.get("per_request_model_override_via_extra_body"):
        missing.append("runtime.per_request_model_override")
    if not runtime.get("per_request_system_override") and not runtime.get("per_request_system_override_via_extra_body"):
        missing.append("runtime.per_request_system_override")

    control = capabilities.get("control", {})
    if not control.get("update_system_prompt"):
        missing.append("control.update_system_prompt")
    if not control.get("update_agent_model"):
        missing.append("control.update_agent_model")
    if not control.get("update_core_memory_block"):
        missing.append("control.update_core_memory_block")
    if not control.get("attach_tool"):
        missing.append("control.attach_tool")
    if not control.get("detach_tool"):
        missing.append("control.detach_tool")

    return missing


def validate_platform_capabilities_startup() -> None:
    if not platform_api_enabled():
        return

    strict_mode = is_truthy(os.getenv("AGENT_PLATFORM_STRICT_CAPABILITIES"))
    capabilities = agent_platform.capabilities()
    missing = missing_platform_capabilities(capabilities)
    if strict_mode and missing:
        raise RuntimeError(f"Missing required Agent Platform capabilities: {', '.join(missing)}")
