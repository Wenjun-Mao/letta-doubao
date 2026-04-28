from __future__ import annotations

from typing import Any

import agent_platform_api.options.letta_catalog as letta_catalog
from agent_platform_api.dependencies import model_router_client


def invalidate_options_cache() -> None:
    model_router_client.invalidate()


def enriched_catalog_items(force_refresh: bool = False) -> list[dict[str, Any]]:
    payload = model_router_client.catalog(force_refresh=force_refresh)
    letta_model_handles, _ = letta_catalog.resolve_letta_catalog_handles()
    router_base_url = model_router_client.v1_base_url()
    items: list[dict[str, Any]] = []
    for raw_item in payload.get("items", []):
        if not isinstance(raw_item, dict):
            continue
        model_key = str(raw_item.get("model_key") or raw_item.get("router_model_id") or "").strip()
        upstream_provider_model_id = str(raw_item.get("provider_model_id", "") or "").strip()
        if not model_key:
            continue
        is_embedding = str(raw_item.get("model_type", "") or "").strip() == "embedding"
        letta_handle = str(raw_item.get("letta_handle", "") or "").strip() or None
        router_agent_available = bool(raw_item.get("agent_studio_available", False))
        agent_studio_available = (
            (not is_embedding)
            and router_agent_available
            and bool(letta_handle)
            and letta_handle in letta_model_handles
        )
        module_visibility = [
            str(item or "").strip()
            for item in raw_item.get("module_visibility", [])
            if str(item or "").strip()
        ]
        items.append(
            {
                "model_key": model_key,
                "source_id": str(raw_item.get("source_id", "") or ""),
                "source_label": str(raw_item.get("source_label", "") or ""),
                "source_kind": str(raw_item.get("source_kind", "") or "openai-compatible"),
                "source_adapter": str(raw_item.get("source_adapter", "") or "generic_openai"),
                "base_url": router_base_url,
                "source_base_url": str(raw_item.get("source_base_url", "") or ""),
                "enabled_for": module_visibility,
                "module_visibility": module_visibility,
                "provider_model_id": model_key,
                "upstream_provider_model_id": upstream_provider_model_id,
                "model_type": str(raw_item.get("model_type", "") or "unknown"),
                "letta_handle": letta_handle,
                "agent_studio_available": agent_studio_available,
                "router_agent_studio_available": router_agent_available,
                "comment_lab_available": (not is_embedding) and bool(raw_item.get("comment_lab_available", False)),
                "label_lab_available": (not is_embedding) and bool(raw_item.get("label_lab_available", False)),
                "structured_output_mode": raw_item.get("structured_output_mode"),
            }
        )
    return items


def model_catalog(force_refresh: bool = False) -> dict[str, Any]:
    payload = model_router_client.catalog(force_refresh=force_refresh)
    sources: list[dict[str, Any]] = []
    for raw_source in payload.get("sources", []):
        if not isinstance(raw_source, dict):
            continue
        normalized_source = dict(raw_source)
        module_visibility = normalized_source.get("module_visibility", [])
        normalized_source["enabled_for"] = list(module_visibility) if isinstance(module_visibility, list) else []
        normalized_source.setdefault("letta_handle_prefix", "openai-proxy")
        sources.append(normalized_source)
    return {
        "generated_at": payload.get("generated_at"),
        "sources": sources,
        "items": enriched_catalog_items(force_refresh=force_refresh),
        "router": {
            "enabled": True,
            "base_url": model_router_client.v1_base_url(),
        },
    }
