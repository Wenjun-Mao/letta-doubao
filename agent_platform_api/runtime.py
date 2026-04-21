from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, cast

import httpx
from fastapi import HTTPException
from letta_client import Letta
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from agent_platform_api.models.commenting import ApiCommentingRuntimeDefaultsResponse
from agent_platform_api.models.common import CommentingTaskShape, ScenarioType
from utils.agent_lifecycle_registry import AgentLifecycleRegistry
from utils.agent_platform_service import AgentPlatformService
from utils.commenting_service import CommentingService
from utils.custom_tool_registry import CustomToolRegistry
from utils.platform_test_orchestrator import PlatformTestOrchestrator
from utils.prompt_persona_registry import PromptPersonaRegistry

APP_VERSION = os.getenv("AGENT_PLATFORM_API_VERSION", "0.2.0")

PREFERRED_MODEL_OPTIONS = [
    {
        "key": "lmstudio_openai/qwen3.5-27b",
        "label": "Qwen 3.5 27B",
        "description": "Recommended default for local development.",
    },
    {
        "key": "lmstudio_openai/qwen/qwen3.5-35b-a3b",
        "label": "Qwen 3.5 35B A3B",
        "description": "Higher quality but heavier VRAM usage.",
    },
    {
        "key": "openai-proxy/doubao-seed-1-8-251228",
        "label": "Doubao Seed 1.8 (ARK)",
        "description": "Requires OpenAI-compatible ARK provider configured in Letta server.",
    },
]

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
}
MANAGED_TOOL_TAG = "ade:managed"
OPTIONS_CACHE_TTL_SECONDS = max(1, int(os.getenv("AGENT_PLATFORM_OPTIONS_CACHE_TTL_SECONDS", "30")))
MODEL_DISCOVERY_TIMEOUT_SECONDS = max(1.0, float(os.getenv("AGENT_PLATFORM_MODEL_DISCOVERY_TIMEOUT_SECONDS", "5")))
OPTIONS_CACHE: dict[str, Any] = {
    "expires_at": 0.0,
    "models": [],
    "embeddings": [],
}


class RetryableModelDiscoveryError(RuntimeError):
    """Raised for transient failures while querying upstream model catalogs."""


client = Letta(base_url=os.getenv("LETTA_BASE_URL", "http://localhost:8283"))
agent_platform = AgentPlatformService(client)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
test_orchestrator = PlatformTestOrchestrator(project_root=PROJECT_ROOT)
prompt_persona_registry = PromptPersonaRegistry(PROJECT_ROOT)
custom_tool_registry = CustomToolRegistry(PROJECT_ROOT)
agent_lifecycle_registry = AgentLifecycleRegistry(PROJECT_ROOT)
commenting_service = CommentingService()
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
        key = option.get("key", "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(option)
    return out


def resolve_models_endpoint(base_url: str | None) -> str:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return ""
    if base.endswith("/models"):
        return base
    if base.endswith("/chat/completions"):
        return f"{base[:-len('/chat/completions')]}/models"
    if base.endswith("/v1"):
        return f"{base}/models"
    return f"{base}/v1/models"


def ensure_lmstudio_handle(model_id: str) -> str:
    resolved = str(model_id or "").strip().strip("/")
    if not resolved:
        return ""

    lowered = resolved.lower()
    if lowered.startswith(("lmstudio_openai/", "openai-proxy/", "openai/", "anthropic/")):
        return resolved
    return f"lmstudio_openai/{resolved}"


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type(
        (
            RetryableModelDiscoveryError,
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.ReadError,
            httpx.RemoteProtocolError,
            httpx.WriteError,
        )
    ),
    reraise=True,
)
def discover_lmstudio_model_ids(models_endpoint: str) -> set[str]:
    if not models_endpoint:
        return set()

    with httpx.Client(timeout=MODEL_DISCOVERY_TIMEOUT_SECONDS) as http_client:
        response = http_client.get(models_endpoint)
        if response.status_code in {429, 500, 502, 503, 504}:
            raise RetryableModelDiscoveryError(
                f"Model discovery temporary failure ({response.status_code})"
            )
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, dict):
        return set()

    items = payload.get("data")
    if not isinstance(items, list):
        return set()

    discovered: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or item.get("model") or item.get("name") or "").strip()
        if model_id:
            discovered.add(model_id)
    return discovered


def runtime_options(force_refresh: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cache_expires_at = float(OPTIONS_CACHE.get("expires_at", 0.0) or 0.0)
    cached_models = OPTIONS_CACHE.get("models")
    cached_embeddings = OPTIONS_CACHE.get("embeddings")
    if (
        not force_refresh
        and time.monotonic() < cache_expires_at
        and isinstance(cached_models, list)
        and isinstance(cached_embeddings, list)
        and cached_models
    ):
        return [dict(option) for option in cached_models], [dict(option) for option in cached_embeddings]

    model_options = [dict(option) for option in PREFERRED_MODEL_OPTIONS]
    embedding_options = [dict(option) for option in PREFERRED_EMBEDDING_OPTIONS]
    known_embedding_keys = {option["key"] for option in embedding_options}

    discovered_model_handles: set[str] = set()
    discovered_embedding_handles: set[str] = set()

    def looks_like_embedding_handle(handle: str) -> bool:
        lowered = handle.lower()
        return "embedding" in lowered or "embed" in lowered

    def resolve_model_handle(model_obj: Any) -> str:
        for attr in ("handle", "id", "model", "name"):
            value = str(getattr(model_obj, attr, "") or "").strip()
            if value:
                return value
        return ""

    try:
        for embedding in list(client.models.embeddings.list()):
            handle = resolve_model_handle(embedding)
            if handle:
                discovered_embedding_handles.add(handle)
    except Exception:
        pass

    try:
        for model in list(client.models.list()):
            handle = resolve_model_handle(model)
            model_type = str(
                getattr(model, "api_model_type", "") or getattr(model, "model_type", "") or ""
            ).strip().lower()
            if not handle:
                continue
            if looks_like_embedding_handle(handle):
                discovered_embedding_handles.add(handle)
                continue
            if model_type in {"embedding", "embeddings"}:
                discovered_embedding_handles.add(handle)
                continue
            discovered_model_handles.add(handle)
    except Exception:
        pass

    lmstudio_base_url = (
        os.getenv("AGENT_PLATFORM_COMMENTING_BASE_URL")
        or os.getenv("LMSTUDIO_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("OPENAI_API_BASE")
    )
    try:
        models_endpoint = resolve_models_endpoint(lmstudio_base_url)
        for model_id in discover_lmstudio_model_ids(models_endpoint):
            handle = ensure_lmstudio_handle(model_id)
            if not handle:
                continue
            if looks_like_embedding_handle(handle):
                discovered_embedding_handles.add(handle)
                continue
            discovered_model_handles.add(handle)
    except Exception:
        pass

    for handle in sorted(discovered_model_handles):
        if any(option["key"] == handle for option in model_options):
            continue
        model_options.append(
            {
                "key": handle,
                "label": handle.split("/", 1)[-1],
                "description": "Discovered from Letta or OpenAI-compatible model catalog.",
            }
        )

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

    model_options = dedupe_options(model_options)
    embedding_options = dedupe_options(embedding_options)
    model_catalog_known = bool(discovered_model_handles)
    embedding_catalog_known = bool(discovered_embedding_handles)
    for option in model_options:
        option["available"] = (not model_catalog_known) or option["key"] in discovered_model_handles
    for option in embedding_options:
        option["available"] = (not embedding_catalog_known) or option["key"] in discovered_embedding_handles

    OPTIONS_CACHE["expires_at"] = time.monotonic() + OPTIONS_CACHE_TTL_SECONDS
    OPTIONS_CACHE["models"] = [dict(option) for option in model_options]
    OPTIONS_CACHE["embeddings"] = [dict(option) for option in embedding_options]
    return model_options, embedding_options


def invalidate_options_cache() -> None:
    OPTIONS_CACHE["expires_at"] = 0.0


def commenting_runtime_defaults() -> ApiCommentingRuntimeDefaultsResponse:
    defaults = commenting_service.runtime_defaults()
    task_shape = str(defaults.get("task_shape", "compact") or "compact").strip().lower()
    if task_shape not in {"compact", "all_in_system", "structured_output"}:
        task_shape = "compact"
    resolved_task_shape = cast(CommentingTaskShape, task_shape)
    return ApiCommentingRuntimeDefaultsResponse(
        max_tokens=int(defaults.get("max_tokens", 1536)),
        timeout_seconds=float(defaults.get("timeout_seconds", 60.0)),
        task_shape=resolved_task_shape,
    )

