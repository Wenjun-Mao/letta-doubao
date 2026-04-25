from __future__ import annotations

import os
from typing import Any, cast

from agent_platform_api.dependencies import (
    client,
    commenting_service,
    label_schema_registry,
    labeling_service,
    model_router_client,
)
from agent_platform_api.models.commenting import ApiCommentingRuntimeDefaultsResponse
from agent_platform_api.models.common import CommentingTaskShape, ScenarioType
from agent_platform_api.models.labeling import ApiLabelingRuntimeDefaultsResponse
from agent_platform_api.registries.label_schema import DEFAULT_LABEL_SCHEMA_KEY

MODEL_OPTION_OVERRIDES: dict[str, dict[str, str]] = {
    "lmstudio_openai/gemma-4-31b-it": {
        "label": "Gemma 4 31B IT",
        "description": "Local model discovered from Unsloth Studio.",
    },
    "lmstudio_openai/qwen3.5-27b": {
        "label": "Qwen 3.5 27B",
        "description": "Recommended default for local development.",
    },
    "lmstudio_openai/qwen/qwen3.5-35b-a3b": {
        "label": "Qwen 3.5 35B A3B",
        "description": "Higher quality but heavier VRAM usage.",
    },
    "openai-proxy/doubao-seed-1-8-251228": {
        "label": "Doubao Seed 1.8 (ARK)",
        "description": "Requires OpenAI-compatible ARK provider configured in Letta server.",
    },
}

PROVIDER_MODEL_OPTION_OVERRIDES: dict[str, dict[str, str]] = {
    "gemma-4-31b-it": {
        "label": "Gemma 4 31B IT",
        "description": "Local model discovered from Unsloth Studio.",
    },
    "gemma4": {
        "label": "Gemma 4 (llama-server)",
        "description": "Local GGUF model served by llama-server with JSON schema support.",
    },
    "qwen3.5-27b": {
        "label": "Qwen 3.5 27B",
        "description": "Recommended default for local development.",
    },
    "qwen/qwen3.5-35b-a3b": {
        "label": "Qwen 3.5 35B A3B",
        "description": "Higher quality but heavier VRAM usage.",
    },
    "doubao-seed-1-8-251228": {
        "label": "Doubao Seed 1.8 (ARK)",
        "description": "OpenAI-compatible ARK provider model.",
    },
}
MODEL_OPTION_PRIORITY = {key: index for index, key in enumerate(MODEL_OPTION_OVERRIDES)}
PROVIDER_MODEL_OPTION_PRIORITY = {
    key: index for index, key in enumerate(PROVIDER_MODEL_OPTION_OVERRIDES)
}

PREFERRED_EMBEDDING_OPTIONS = [
    {
        "key": "lmstudio_openai/text-embedding-qwen3-embedding-0.6b",
        "label": "Qwen Embedding 0.6B (Local)",
        "description": "Local embedding model served by LM Studio.",
    },
    {
        "key": "lmstudio_openai/text-embedding-nomic-embed-text-v1.5",
        "label": "Nomic Embed v1.5 (Local)",
        "description": "Alternative local embedding model via LM Studio.",
    },
    {
        "key": "letta/letta-free",
        "label": "Letta Free Embedding (Cloud)",
        "description": "Cloud embedding endpoint; requires network access and endpoint support.",
    },
]

DEFAULT_MODEL = ""
DEFAULT_CHAT_PROMPT_KEY = "chat_v20260418"
DEFAULT_CHAT_PERSONA_KEY = "chat_linxiaotang"
DEFAULT_COMMENT_PROMPT_KEY = "comment_v20260418"
DEFAULT_COMMENT_PERSONA_KEY = "comment_linxiaotang"
DEFAULT_LABEL_PROMPT_KEY = "label_generic_entities_v1"
DEFAULT_EMBEDDING = ""
SCENARIO_DEFAULTS: dict[ScenarioType, dict[str, str]] = {
    "chat": {
        "prompt_key": DEFAULT_CHAT_PROMPT_KEY,
        "persona_key": DEFAULT_CHAT_PERSONA_KEY,
    },
    "comment": {
        "prompt_key": DEFAULT_COMMENT_PROMPT_KEY,
        "persona_key": DEFAULT_COMMENT_PERSONA_KEY,
    },
    "label": {
        "prompt_key": DEFAULT_LABEL_PROMPT_KEY,
        "persona_key": "",
    },
}


def invalidate_options_cache() -> None:
    model_router_client.invalidate()


def dedupe_options(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for option in options:
        key = str(option.get("key", "") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(option)
    return out


def _looks_like_embedding_handle(handle: str) -> bool:
    lowered = str(handle or "").strip().lower()
    return "embedding" in lowered or "embed" in lowered


def _resolve_model_handle(model_obj: Any) -> str:
    for attr in ("handle", "id", "model", "name"):
        value = str(getattr(model_obj, attr, "") or "").strip()
        if value:
            return value
    return ""


def _resolve_letta_catalog_handles() -> tuple[set[str], set[str]]:
    discovered_model_handles: set[str] = set()
    discovered_embedding_handles: set[str] = set()

    try:
        for embedding in list(client.models.embeddings.list()):
            handle = _resolve_model_handle(embedding)
            if handle:
                discovered_embedding_handles.add(handle)
    except Exception:
        pass

    try:
        for model in list(client.models.list()):
            handle = _resolve_model_handle(model)
            model_type = str(
                getattr(model, "api_model_type", "") or getattr(model, "model_type", "") or ""
            ).strip().lower()
            if not handle:
                continue
            if _looks_like_embedding_handle(handle) or model_type in {"embedding", "embeddings"}:
                discovered_embedding_handles.add(handle)
                continue
            discovered_model_handles.add(handle)
    except Exception:
        pass

    return discovered_model_handles, discovered_embedding_handles


def _enriched_catalog_items(force_refresh: bool = False) -> list[dict[str, Any]]:
    payload = model_router_client.catalog(force_refresh=force_refresh)
    letta_model_handles, _ = _resolve_letta_catalog_handles()
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
        "items": _enriched_catalog_items(force_refresh=force_refresh),
        "router": {
            "enabled": True,
            "base_url": model_router_client.v1_base_url(),
        },
    }


def _model_option_metadata(item: dict[str, Any], *, chat_key: str | None = None) -> tuple[str, str]:
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


def _embedding_options() -> list[dict[str, Any]]:
    _, discovered_embedding_handles = _resolve_letta_catalog_handles()
    embedding_options = [dict(option) for option in PREFERRED_EMBEDDING_OPTIONS]
    known_embedding_keys = {option["key"] for option in embedding_options}

    for handle in sorted(discovered_embedding_handles):
        if handle in known_embedding_keys:
            continue
        known_embedding_keys.add(handle)
        embedding_options.append(
            {
                "key": handle,
                "label": handle.split("/", 1)[-1],
                "description": "Discovered embedding handle from Letta model catalog.",
            }
        )

    embedding_options = dedupe_options(embedding_options)
    embedding_catalog_known = bool(discovered_embedding_handles)
    for option in embedding_options:
        option["available"] = (not embedding_catalog_known) or option["key"] in discovered_embedding_handles
    return embedding_options


def _model_option_sort_key(option: dict[str, Any]) -> tuple[int, int, str, str]:
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
    items = _enriched_catalog_items(force_refresh=force_refresh)
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
        label, description = _model_option_metadata(item, chat_key=key if scenario == "chat" else None)
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
            }
        )

    if scenario == "chat":
        model_options.sort(key=_model_option_sort_key)
    return model_options, _embedding_options()


def resolve_comment_model_selection(
    *,
    model_key: str | None = None,
    model_selector: str | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    items = [item for item in _enriched_catalog_items(force_refresh=force_refresh) if item["comment_lab_available"]]
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


def active_label_schema_records() -> list[dict[str, Any]]:
    return [
        record
        for record in label_schema_registry.list_schemas(include_archived=False)
        if not bool(record.get("archived", False))
    ]


def label_schema_option_entries() -> list[dict[str, Any]]:
    return [
        {
            "key": str(record.get("key", "") or ""),
            "label": str(record.get("label", "") or ""),
            "description": str(record.get("description", "") or ""),
            "scenario": "label",
            "available": True,
        }
        for record in active_label_schema_records()
        if str(record.get("key", "") or "").strip()
    ]


def label_schema_record_map() -> dict[str, dict[str, Any]]:
    return {
        str(record.get("key", "") or ""): record
        for record in active_label_schema_records()
        if str(record.get("key", "") or "").strip()
    }


def resolve_default_label_schema_key(schema_options: list[dict[str, Any]]) -> str:
    if any(str(option.get("key", "")) == DEFAULT_LABEL_SCHEMA_KEY for option in schema_options):
        return DEFAULT_LABEL_SCHEMA_KEY
    return str(schema_options[0].get("key", "") if schema_options else "")


def resolve_label_model_selection(
    *,
    model_key: str,
    force_refresh: bool = False,
) -> dict[str, Any]:
    items = [item for item in _enriched_catalog_items(force_refresh=force_refresh) if item["label_lab_available"]]
    requested_key = str(model_key or "").strip()
    if not requested_key:
        raise ValueError("model_key is required")

    matched = next((item for item in items if item["model_key"] == requested_key), None)
    if matched is None:
        raise ValueError(f"Invalid model_key: {requested_key}")
    return {**matched, "api_key": model_router_client.api_key()}


def commenting_runtime_defaults() -> ApiCommentingRuntimeDefaultsResponse:
    defaults = commenting_service.runtime_defaults()
    task_shape = str(defaults.get("task_shape", "classic") or "classic").strip().lower()
    if task_shape not in {"classic", "all_in_system", "structured_output"}:
        task_shape = "classic"
    resolved_task_shape = cast(CommentingTaskShape, task_shape)
    return ApiCommentingRuntimeDefaultsResponse(
        max_tokens=int(defaults.get("max_tokens", 0)),
        timeout_seconds=float(defaults.get("timeout_seconds", 60.0)),
        task_shape=resolved_task_shape,
    )


def labeling_runtime_defaults() -> ApiLabelingRuntimeDefaultsResponse:
    defaults = labeling_service.runtime_defaults()
    return ApiLabelingRuntimeDefaultsResponse(
        max_tokens=int(defaults.get("max_tokens", 0)),
        timeout_seconds=float(defaults.get("timeout_seconds", 60.0)),
        repair_retry_count=int(defaults.get("repair_retry_count", 1)),
    )

