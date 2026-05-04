from __future__ import annotations

from typing import Any

import agent_platform_api.options.letta_catalog as letta_catalog
from agent_platform_api.models.common import ScenarioType
from agent_platform_api.options.catalog import enriched_catalog_items
from agent_platform_api.options.constants import (
    MODEL_OPTION_OVERRIDES,
    MODEL_OPTION_PRIORITY,
    PREFERRED_EMBEDDING_OPTIONS,
    PROVIDER_MODEL_OPTION_OVERRIDES,
    PROVIDER_MODEL_OPTION_PRIORITY,
)
from agent_platform_api.options.utils import dedupe_options


def model_option_metadata(item: dict[str, Any], *, chat_key: str | None = None) -> tuple[str, str]:
    resolved_key = str(chat_key or item.get("letta_handle", "") or "").strip()
    provider_model_id = str(item.get("provider_model_id", "") or "").strip()
    upstream_provider_model_id = str(item.get("upstream_provider_model_id", "") or "").strip()
    override = (
        MODEL_OPTION_OVERRIDES.get(resolved_key)
        or PROVIDER_MODEL_OPTION_OVERRIDES.get(provider_model_id)
        or PROVIDER_MODEL_OPTION_OVERRIDES.get(upstream_provider_model_id)
    )
    if override:
        return override["label"], override["description"]
    source_label = str(item.get("source_label", "") or "").strip()
    display_model_id = upstream_provider_model_id or provider_model_id or resolved_key
    return display_model_id, f"Discovered from {source_label}."


def embedding_options() -> list[dict[str, Any]]:
    _, discovered_embedding_handles = letta_catalog.resolve_letta_catalog_handles()
    options = [dict(option) for option in PREFERRED_EMBEDDING_OPTIONS]
    known_embedding_keys = {option["key"] for option in options}

    for handle in sorted(discovered_embedding_handles):
        if handle in known_embedding_keys:
            continue
        known_embedding_keys.add(handle)
        options.append(
            {
                "key": handle,
                "label": handle.split("/", 1)[-1],
                "description": "Discovered embedding handle from Letta model catalog.",
            }
        )

    options = dedupe_options(options)
    embedding_catalog_known = bool(discovered_embedding_handles)
    for option in options:
        option["available"] = (not embedding_catalog_known) or option["key"] in discovered_embedding_handles
    return options


def model_option_sort_key(option: dict[str, Any]) -> tuple[int, int, str, str]:
    key = str(option.get("key", "") or "").strip()
    provider_model_id = str(option.get("provider_model_id", "") or "").strip()
    upstream_provider_model_id = str(option.get("upstream_provider_model_id", "") or "").strip()
    preferred_rank = MODEL_OPTION_PRIORITY.get(key)
    if preferred_rank is None:
        preferred_rank = PROVIDER_MODEL_OPTION_PRIORITY.get(provider_model_id)
    if preferred_rank is None:
        preferred_rank = PROVIDER_MODEL_OPTION_PRIORITY.get(upstream_provider_model_id)
    if preferred_rank is not None:
        return (0, int(preferred_rank), key.lower(), provider_model_id.lower())
    return (1, 0, key.lower(), provider_model_id.lower())


def runtime_options(
    scenario: ScenarioType = "chat",
    *,
    force_refresh: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    items = enriched_catalog_items(force_refresh=force_refresh)
    model_options: list[dict[str, Any]] = []
    seen_model_keys: set[str] = set()

    availability_key = {
        "chat": "agent_studio_available",
        "comment": "comment_lab_available",
        "label": "label_lab_available",
    }[scenario]

    for item in items:
        if not item[availability_key]:
            continue
        key = str(item.get("letta_handle" if scenario == "chat" else "model_key", "") or "").strip()
        if not key or key in seen_model_keys:
            continue
        seen_model_keys.add(key)
        label, description = model_option_metadata(item, chat_key=key if scenario == "chat" else None)
        model_options.append(
            {
                "key": key,
                "label": label,
                "description": description,
                "available": True,
                "source_id": item["source_id"],
                "source_label": item["source_label"],
                "provider_model_id": item["provider_model_id"],
                "upstream_provider_model_id": item.get("upstream_provider_model_id"),
                "label_lab_available": item["label_lab_available"],
                "structured_output_mode": item["structured_output_mode"],
                "sampling_defaults": item.get("sampling_defaults", {}),
                "scenario_sampling_defaults": item.get("scenario_sampling_defaults", {}),
                "supports_top_k": item.get("supports_top_k", False),
                "profile_applied": item.get("profile_applied", False),
                "profile_source": item.get("profile_source", ""),
                "agent_studio_candidate": item.get("agent_studio_candidate", False),
                "agent_studio_compatible": item.get("agent_studio_compatible", True),
            }
        )

    if scenario == "chat":
        model_options.sort(key=model_option_sort_key)
    return model_options, embedding_options()
