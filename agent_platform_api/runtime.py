from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

from fastapi import HTTPException
from letta_client import Letta

from agent_platform_api.models.commenting import ApiCommentingRuntimeDefaultsResponse
from agent_platform_api.models.common import CommentingTaskShape, LabelingOutputMode, ScenarioType
from agent_platform_api.models.labeling import ApiLabelingRuntimeDefaultsResponse
from agent_platform_api.settings import get_settings
from utils.agent_lifecycle_registry import AgentLifecycleRegistry
from utils.agent_platform_service import AgentPlatformService
from utils.commenting_service import CommentingService
from utils.custom_tool_registry import CustomToolRegistry
from utils.labeling_service import LabelingService
from utils.label_schema_registry import DEFAULT_LABEL_SCHEMA_KEY, LabelSchemaRegistry
from utils.model_allowlist import load_configured_source_allowlist
from utils.model_catalog import ModelCatalogService
from utils.platform_test_orchestrator import PlatformTestOrchestrator
from utils.prompt_persona_registry import PromptPersonaRegistry

APP_VERSION = os.getenv("AGENT_PLATFORM_API_VERSION", "0.2.0")

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
DEFAULT_LABEL_PROMPT_KEY = "label_generic_spans_v1"
DEFAULT_EMBEDDING = ""
LABEL_STRICT_SOURCE_IDS = {"ark"}
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
MANAGED_TOOL_TAG = "ade:managed"

client = Letta(base_url=os.getenv("LETTA_BASE_URL", "http://localhost:8283"))
agent_platform = AgentPlatformService(client)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
test_orchestrator = PlatformTestOrchestrator(project_root=PROJECT_ROOT)
prompt_persona_registry = PromptPersonaRegistry(PROJECT_ROOT)
label_schema_registry = LabelSchemaRegistry(PROJECT_ROOT)
custom_tool_registry = CustomToolRegistry(PROJECT_ROOT)
agent_lifecycle_registry = AgentLifecycleRegistry(PROJECT_ROOT)
model_catalog_service = ModelCatalogService()
commenting_service = CommentingService()
labeling_service = LabelingService()
REVISION_LOG_DIR = PROJECT_ROOT / "diagnostics"
REVISION_LOG_FILE = REVISION_LOG_DIR / "prompt_persona_revisions.jsonl"


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


def invalidate_options_cache() -> None:
    model_catalog_service.invalidate()


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


def _structured_output_mode_for_source(source_id: str, source_adapter: str = "") -> LabelingOutputMode:
    adapter = str(source_adapter or "").strip().lower()
    if adapter == "llama_cpp_server":
        return "json_schema"
    if adapter == "ark_openai" or str(source_id or "").strip() in LABEL_STRICT_SOURCE_IDS:
        return "strict_json_schema"
    return "best_effort_prompt_json"


def _label_allowlist_for_source(source_id: str):
    return load_configured_source_allowlist(str(source_id or "").strip(), probe_mode="label-structured")


def _enriched_catalog_items(force_refresh: bool = False) -> list[dict[str, Any]]:
    snapshot = model_catalog_service.snapshot(force_refresh=force_refresh)
    letta_model_handles, _ = _resolve_letta_catalog_handles()
    label_allowlists: dict[str, Any] = {}
    items: list[dict[str, Any]] = []
    for entry in model_catalog_service.flatten(snapshot):
        is_embedding = entry.model_type == "embedding"
        letta_handle = entry.letta_handle
        agent_studio_available = (
            (not is_embedding)
            and ("chat" in entry.enabled_for)
            and bool(letta_handle)
            and letta_handle in letta_model_handles
        )
        comment_lab_available = (not is_embedding) and ("comment" in entry.enabled_for)
        structured_output_mode: LabelingOutputMode | None = None
        label_lab_available = False
        if (not is_embedding) and ("label" in entry.enabled_for):
            structured_output_mode = _structured_output_mode_for_source(entry.source_id, entry.source_adapter)
            if structured_output_mode == "strict_json_schema":
                if entry.source_id not in label_allowlists:
                    label_allowlists[entry.source_id] = _label_allowlist_for_source(entry.source_id)
                allowlist = label_allowlists.get(entry.source_id)
                label_lab_available = bool(
                    allowlist
                    and allowlist.applied
                    and entry.provider_model_id in allowlist.usable_models
                )
            else:
                label_lab_available = True
        items.append(
            {
                "model_key": entry.model_key,
                "source_id": entry.source_id,
                "source_label": entry.source_label,
                "source_kind": entry.source_kind,
                "source_adapter": entry.source_adapter,
                "base_url": entry.base_url,
                "enabled_for": list(entry.enabled_for),
                "provider_model_id": entry.provider_model_id,
                "model_type": entry.model_type,
                "letta_handle": letta_handle,
                "agent_studio_available": agent_studio_available,
                "comment_lab_available": comment_lab_available,
                "label_lab_available": label_lab_available,
                "structured_output_mode": structured_output_mode,
            }
        )
    return items


def model_catalog(force_refresh: bool = False) -> dict[str, Any]:
    snapshot = model_catalog_service.snapshot(force_refresh=force_refresh)
    return {
        "generated_at": snapshot.generated_at,
        "sources": [
            {
                "id": source.id,
                "label": source.label,
                "kind": source.kind,
                "adapter": source.adapter,
                "base_url": source.base_url,
                "enabled_for": list(source.enabled_for),
                "letta_handle_prefix": source.letta_handle_prefix,
                "status": source.status,
                "detail": source.detail,
                "allowlist_applied": source.allowlist_applied,
                "allowlist_checked_at": source.allowlist_checked_at,
                "raw_model_count": source.raw_model_count,
                "filtered_model_count": source.filtered_model_count,
                "models": [
                    {
                        "provider_model_id": model.provider_model_id,
                        "model_type": model.model_type,
                    }
                    for model in source.models
                ],
            }
            for source in snapshot.sources
        ],
        "items": _enriched_catalog_items(force_refresh=force_refresh),
    }


def _model_option_metadata(item: dict[str, Any], *, chat_key: str | None = None) -> tuple[str, str]:
    resolved_key = str(chat_key or item.get("letta_handle", "") or "").strip()
    provider_model_id = str(item.get("provider_model_id", "") or "").strip()
    override = MODEL_OPTION_OVERRIDES.get(resolved_key) or PROVIDER_MODEL_OPTION_OVERRIDES.get(provider_model_id)
    if override:
        return override["label"], override["description"]
    source_label = str(item.get("source_label", "") or "").strip()
    return provider_model_id or resolved_key, f"Discovered from {source_label}."


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
    preferred_rank = MODEL_OPTION_PRIORITY.get(key)
    if preferred_rank is None:
        preferred_rank = PROVIDER_MODEL_OPTION_PRIORITY.get(provider_model_id)
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

    if scenario == "chat":
        for item in items:
            if not item["agent_studio_available"]:
                continue
            key = str(item.get("letta_handle", "") or "").strip()
            if not key or key in seen_model_keys:
                continue
            seen_model_keys.add(key)
            label, description = _model_option_metadata(item, chat_key=key)
            model_options.append(
                {
                    "key": key,
                    "label": label,
                    "description": description,
                    "available": True,
                    "source_id": item["source_id"],
                    "source_label": item["source_label"],
                    "provider_model_id": item["provider_model_id"],
                    "label_lab_available": item["label_lab_available"],
                    "structured_output_mode": item["structured_output_mode"],
                }
            )
    elif scenario == "comment":
        for item in items:
            if not item["comment_lab_available"]:
                continue
            key = str(item.get("model_key", "") or "").strip()
            if not key or key in seen_model_keys:
                continue
            seen_model_keys.add(key)
            label, description = _model_option_metadata(item)
            model_options.append(
                {
                    "key": key,
                    "label": label,
                    "description": description,
                    "available": True,
                    "source_id": item["source_id"],
                    "source_label": item["source_label"],
                    "provider_model_id": item["provider_model_id"],
                    "label_lab_available": item["label_lab_available"],
                    "structured_output_mode": item["structured_output_mode"],
                }
            )
    else:
        for item in items:
            if not item["label_lab_available"]:
                continue
            key = str(item.get("model_key", "") or "").strip()
            if not key or key in seen_model_keys:
                continue
            seen_model_keys.add(key)
            label, description = _model_option_metadata(item)
            model_options.append(
                {
                    "key": key,
                    "label": label,
                    "description": description,
                    "available": True,
                    "source_id": item["source_id"],
                    "source_label": item["source_label"],
                    "provider_model_id": item["provider_model_id"],
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
    legacy_model: str | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    items = [item for item in _enriched_catalog_items(force_refresh=force_refresh) if item["comment_lab_available"]]
    source_api_keys = _source_api_keys()
    requested_key = str(model_key or "").strip()
    if requested_key:
        matched = next((item for item in items if item["model_key"] == requested_key), None)
        if matched:
            return {**matched, "api_key": source_api_keys.get(str(matched["source_id"]), "")}
        raise ValueError(f"Invalid model_key: {requested_key}")

    requested_model = str(legacy_model or "").strip()
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
        matched = matches[0]
        return {**matched, "api_key": source_api_keys.get(str(matched["source_id"]), "")}
    if len(matches) > 1:
        raise ValueError(f"Ambiguous model selector '{requested_model}'. Use model_key instead.")
    raise ValueError(f"Invalid model: {requested_model}")


def _source_api_keys() -> dict[str, str]:
    settings = get_settings()
    return {
        source.id: source.resolve_api_key()
        for source in settings.model_sources
    }


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
    return {**matched, "api_key": _source_api_keys().get(str(matched["source_id"]), "")}


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
