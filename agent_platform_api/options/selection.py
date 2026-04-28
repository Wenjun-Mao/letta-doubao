from __future__ import annotations

from typing import Any

from agent_platform_api.dependencies import model_router_client
from agent_platform_api.options.catalog import enriched_catalog_items


def resolve_comment_model_selection(
    *,
    model_key: str | None = None,
    model_selector: str | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    items = [item for item in enriched_catalog_items(force_refresh=force_refresh) if item["comment_lab_available"]]
    router_api_key = model_router_client.api_key()
    requested_key = str(model_key or "").strip()
    if requested_key:
        matched = next((item for item in items if item["model_key"] == requested_key), None)
        if matched:
            return {**matched, "api_key": router_api_key}
        raise ValueError(f"Invalid model_key: {requested_key}")

    requested_model = str(model_selector or "").strip()
    if not requested_model:
        raise ValueError("model_key is required")

    matches = [
        item
        for item in items
        if requested_model in {
            str(item["model_key"]),
            str(item["provider_model_id"]),
            str(item.get("letta_handle", "") or ""),
        }
    ]
    if len(matches) == 1:
        return {**matches[0], "api_key": router_api_key}
    if len(matches) > 1:
        raise ValueError(f"Ambiguous model selector '{requested_model}'. Use model_key instead.")
    raise ValueError(f"Invalid model: {requested_model}")


def resolve_label_model_selection(
    *,
    model_key: str,
    force_refresh: bool = False,
) -> dict[str, Any]:
    items = [item for item in enriched_catalog_items(force_refresh=force_refresh) if item["label_lab_available"]]
    requested_key = str(model_key or "").strip()
    if not requested_key:
        raise ValueError("model_key is required")

    matched = next((item for item in items if item["model_key"] == requested_key), None)
    if matched is None:
        raise ValueError(f"Invalid model_key: {requested_key}")
    return {**matched, "api_key": model_router_client.api_key()}
