from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import os
import sys
import time
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

# Add project root to sys.path to resolve imports properly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from letta_client import Letta
from utils.agent_platform_service import AgentPlatformService
from utils.platform_test_orchestrator import PlatformTestOrchestrator
from prompts.persona import PERSONAS, HUMAN_TEMPLATE
from prompts.system_prompts import (
    CUSTOM_V1_PROMPT,
    CUSTOM_V2_PROMPT,
)

APP_VERSION = os.getenv("AGENT_PLATFORM_API_VERSION", "0.2.0")

app = FastAPI(
    title="Agent Platform Dev API",
    version=APP_VERSION,
    summary="Runtime and control APIs for local Agent Platform development",
    description=(
        "Provides legacy Dev UI routes and Agent Platform runtime/control/test orchestration routes. "
        "Designed for dual-run migration from legacy UI to ADE frontend."
    ),
)

# Allow CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    agent_id: str
    message: str

class AgentCreateRequest(BaseModel):
    name: str = "dev-agent"
    model: str = ""
    prompt_key: str = "custom_v2"
    embedding: str | None = None


class PlatformRuntimeMessageRequest(BaseModel):
    input: str
    override_model: str | None = None
    override_system: str | None = None


class PlatformSystemUpdateRequest(BaseModel):
    system: str


class PlatformModelUpdateRequest(BaseModel):
    model: str


class PlatformMemoryBlockUpdateRequest(BaseModel):
    value: str


class PlatformToolTestInvokeRequest(BaseModel):
    agent_id: str
    input: str
    expected_tool_name: str | None = None
    override_model: str | None = None
    override_system: str | None = None


class PlatformTestRunRequest(BaseModel):
    run_type: Literal[
        "agent_bootstrap_check",
        "provider_embedding_matrix_check",
        "prompt_strategy_check",
        "platform_api_e2e_check",
        "ade_mvp_smoke_e2e_check",
        "migration_flag_rollout_check",
        "platform_dual_run_gate",
        "persona_guardrail_runner",
        "memory_update_runner",
    ]
    model: str | None = None
    embedding: str | None = None
    rounds: int | None = None
    config_path: str | None = None


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

PROMPT_OPTIONS = [
    {
        "key": "custom_v2",
        "label": "Custom V2 Chat (Default)",
        "description": "Recommended baseline for robust persona adherence and tool-flow behavior.",
    },
    {
        "key": "custom_v1",
        "label": "Custom V1 (Legacy)",
        "description": "Legacy baseline kept for A/B testing and regression comparison.",
    },
]

PROMPT_MAP = {
    "custom_v1": CUSTOM_V1_PROMPT,
    "custom_v2": CUSTOM_V2_PROMPT,
}

DEFAULT_MODEL = ""
DEFAULT_PROMPT_KEY = "custom_v2"
DEFAULT_EMBEDDING = ""
_OPTIONS_CACHE_TTL_SECONDS = max(1, int(os.getenv("AGENT_PLATFORM_OPTIONS_CACHE_TTL_SECONDS", "30")))
_OPTIONS_CACHE: dict[str, Any] = {
    "expires_at": 0.0,
    "models": [],
    "embeddings": [],
}

# Letta Client Initialization
client = Letta(base_url=os.getenv("LETTA_BASE_URL", "http://localhost:8283"))
agent_platform = AgentPlatformService(client)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
test_orchestrator = PlatformTestOrchestrator(project_root=PROJECT_ROOT)
REVISION_LOG_DIR = PROJECT_ROOT / "diagnostics"
REVISION_LOG_FILE = REVISION_LOG_DIR / "prompt_persona_revisions.jsonl"


def _is_truthy(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _platform_api_enabled() -> bool:
    return _is_truthy(os.getenv("AGENT_PLATFORM_API_ENABLED", "1"))


def _legacy_api_enabled() -> bool:
    return _is_truthy(os.getenv("AGENT_PLATFORM_LEGACY_API_ENABLED", "1"))


def _migration_mode() -> str:
    mode = os.getenv("AGENT_PLATFORM_MIGRATION_MODE", "dual").strip().lower()
    if mode in {"legacy", "dual", "ade"}:
        return mode
    return "dual"


def _ensure_platform_api_enabled() -> None:
    if _platform_api_enabled():
        return
    raise HTTPException(
        status_code=503,
        detail="Agent Platform API is disabled by AGENT_PLATFORM_API_ENABLED.",
    )


def _ensure_legacy_api_enabled() -> None:
    if _legacy_api_enabled():
        return
    raise HTTPException(
        status_code=503,
        detail="Legacy Dev UI API is disabled by AGENT_PLATFORM_LEGACY_API_ENABLED.",
    )


def _missing_platform_capabilities(capabilities: dict[str, Any]) -> list[str]:
    runtime = capabilities.get("runtime", {})
    control = capabilities.get("control", {})

    missing: list[str] = []
    if not (runtime.get("per_request_model_override") or runtime.get("per_request_model_override_via_extra_body")):
        missing.append("runtime.per_request_model_override")
    if not control.get("update_system_prompt"):
        missing.append("control.update_system_prompt")
    if not control.get("update_core_memory_block"):
        missing.append("control.update_core_memory_block")
    if not control.get("attach_tool"):
        missing.append("control.attach_tool")
    if not control.get("detach_tool"):
        missing.append("control.detach_tool")

    return missing


@app.on_event("startup")
async def _startup_validate_platform_capabilities() -> None:
    if not _platform_api_enabled():
        return

    strict_mode = _is_truthy(os.getenv("AGENT_PLATFORM_STRICT_CAPABILITIES"))
    capabilities = agent_platform.capabilities()
    missing = _missing_platform_capabilities(capabilities)
    if strict_mode and missing:
        raise RuntimeError(f"Missing required Agent Platform capabilities: {', '.join(missing)}")

try:
    _SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
except Exception:
    # Windows environments may not have IANA tzdata available.
    _SHANGHAI_TZ = timezone(timedelta(hours=8), name="CST")
_DATETIME_QUERY_TOKENS = (
    "today",
    "date",
    "time",
    "current date",
    "current time",
    "what day",
    "what time",
    "\u4eca\u5929",       # today
    "\u65e5\u671f",       # date
    "\u51e0\u6708",       # month
    "\u51e0\u53f7",       # day number
    "\u51e0\u65e5",       # day number (variant)
    "\u661f\u671f",       # weekday
    "\u5468\u51e0",       # what weekday
    "\u793c\u62dc\u51e0", # what weekday (variant)
    "\u73b0\u5728\u51e0\u70b9", # what time now
    "\u5f53\u524d\u65f6\u95f4", # current time
)


def _dedupe_options(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for option in options:
        key = option.get("key", "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(option)
    return out


def _runtime_options(force_refresh: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cache_expires_at = float(_OPTIONS_CACHE.get("expires_at", 0.0) or 0.0)
    cached_models = _OPTIONS_CACHE.get("models")
    cached_embeddings = _OPTIONS_CACHE.get("embeddings")
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

    def _looks_like_embedding_handle(handle: str) -> bool:
        lowered = handle.lower()
        return "embedding" in lowered or "embed" in lowered

    try:
        for embedding in list(client.models.embeddings.list()):
            handle = str(getattr(embedding, "handle", "") or "")
            if handle:
                discovered_embedding_handles.add(handle)
    except Exception:
        pass

    try:
        for model in list(client.models.list()):
            handle = str(getattr(model, "handle", "") or "")
            model_type = str(getattr(model, "api_model_type", "") or getattr(model, "model_type", "") or "")
            if not handle:
                continue
            if _looks_like_embedding_handle(handle):
                discovered_embedding_handles.add(handle)
                continue
            # Never surface embedding handles in LLM selector.
            if handle in discovered_embedding_handles or handle in known_embedding_keys:
                continue
            if model_type and model_type != "llm":
                continue
            discovered_model_handles.add(handle)
    except Exception:
        # UI must stay usable even if model discovery fails.
        pass

    # Include any extra handles discovered from the running Letta server.
    existing_model_keys = {option["key"] for option in model_options}
    for handle in sorted(discovered_model_handles):
        if handle not in existing_model_keys:
            model_options.append(
                {
                    "key": handle,
                    "label": handle,
                    "description": "Discovered from current Letta server.",
                }
            )

    existing_embedding_keys = {option["key"] for option in embedding_options}
    for handle in sorted(discovered_embedding_handles):
        if handle not in existing_embedding_keys:
            embedding_options.append(
                {
                    "key": handle,
                    "label": handle,
                    "description": "Discovered from current Letta server.",
                }
            )

    model_options = _dedupe_options(model_options)
    embedding_options = _dedupe_options(embedding_options)

    # Mark whether each option is currently resolvable by this Letta server.
    for option in model_options:
        option["available"] = option["key"] in discovered_model_handles if discovered_model_handles else True

    for option in embedding_options:
        option["available"] = option["key"] in discovered_embedding_handles if discovered_embedding_handles else True

    _OPTIONS_CACHE["models"] = [dict(option) for option in model_options]
    _OPTIONS_CACHE["embeddings"] = [dict(option) for option in embedding_options]
    _OPTIONS_CACHE["expires_at"] = time.monotonic() + _OPTIONS_CACHE_TTL_SECONDS

    return [dict(option) for option in model_options], [dict(option) for option in embedding_options]


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except Exception:
        return str(value)


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return _safe_json(json.loads(stripped))
            except Exception:
                return value
        return value
    if isinstance(value, list):
        text_parts = [getattr(item, "text", None) for item in value]
        valid_parts = [part for part in text_parts if isinstance(part, str) and part]
        if valid_parts:
            return " ".join(valid_parts)
        return _safe_json(value)
    if isinstance(value, (dict, tuple)):
        return _safe_json(value)
    return str(value)


def _to_jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return _to_jsonable(model_dump(mode="json"))
        except TypeError:
            return _to_jsonable(model_dump())
        except Exception:
            pass

    to_dict = getattr(value, "dict", None)
    if callable(to_dict):
        try:
            return _to_jsonable(to_dict())
        except Exception:
            pass

    return _normalize_text(value)


def _serialize_message(msg: Any) -> dict[str, Any]:
    message_type = getattr(msg, "message_type", "unknown")
    role = getattr(msg, "role", message_type)

    content: Any = getattr(msg, "content", None)
    if message_type == "reasoning_message":
        content = getattr(msg, "reasoning", content)
    if message_type == "tool_return_message":
        content = getattr(msg, "tool_return", content)

    tool_name = None
    tool_arguments = None
    tool_call = getattr(msg, "tool_call", None)
    if tool_call is not None:
        tool_name = getattr(tool_call, "name", None)
        tool_arguments = _normalize_text(getattr(tool_call, "arguments", None))

    timestamp = getattr(msg, "created_at", None) or getattr(msg, "date", None)

    return {
        "id": str(getattr(msg, "id", "")),
        "created_at": str(timestamp or ""),
        "message_type": message_type,
        "role": role,
        "status": str(getattr(msg, "status", "")),
        "name": tool_name,
        "tool_arguments": tool_arguments,
        "content": _normalize_text(content),
    }


def _derive_last_interaction_at(agent_id: str, last_updated_at: str = "") -> str:
    if last_updated_at:
        return last_updated_at
    try:
        messages = list(client.agents.messages.list(agent_id=agent_id))
    except Exception:
        return ""

    latest = ""
    for msg in messages:
        message_type = str(getattr(msg, "message_type", ""))
        if message_type == "system_message":
            continue
        created_at = str(getattr(msg, "created_at", None) or getattr(msg, "date", None) or "")
        if created_at and created_at > latest:
            latest = created_at
    return latest


def _is_datetime_query(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(token in lowered for token in _DATETIME_QUERY_TOKENS)


def _runtime_datetime_system_hint() -> str:
    now = datetime.now(_SHANGHAI_TZ)
    iso_time = now.strftime("%Y-%m-%d %H:%M:%S %Z%z")
    return (
        "Runtime datetime context for this turn. "
        "Timezone: Asia/Shanghai. "
        f"Current datetime: {iso_time}. "
        "If the user asks about current date or time, answer directly using this value. "
        "Do not say you cannot access a calendar."
    )


def _first_non_empty_line(text: str) -> str:
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned
    return ""


def _trim_preview(value: str, max_len: int = 180) -> str:
    line = _first_non_empty_line(value)
    if len(line) <= max_len:
        return line
    return f"{line[:max_len]}..."


def _append_prompt_persona_revision(
    *,
    agent_id: str,
    field: str,
    before: str,
    after: str,
    source: str,
) -> None:
    if before == after:
        return

    record = {
        "revision_id": str(uuid4()),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "agent_id": agent_id,
        "field": field,
        "source": source,
        "before": before,
        "after": after,
        "before_preview": _trim_preview(before),
        "after_preview": _trim_preview(after),
        "before_length": len(before),
        "after_length": len(after),
        "delta_length": len(after) - len(before),
    }

    try:
        REVISION_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with REVISION_LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # Revision history should not break primary mutation APIs.
        return


def _read_prompt_persona_revisions(
    *,
    agent_id: str | None,
    field: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    if not REVISION_LOG_FILE.exists():
        return []

    items: list[dict[str, Any]] = []
    try:
        for raw_line in REVISION_LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue

            if agent_id and str(payload.get("agent_id", "") or "") != agent_id:
                continue
            if field and str(payload.get("field", "") or "") != field:
                continue

            items.append(payload)
    except Exception:
        return []

    if len(items) > limit:
        items = items[-limit:]
    items.reverse()
    return items

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open(os.path.join(os.path.dirname(__file__), "static", "index.html"), "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/options")
async def api_get_options(refresh: bool = False):
    _ensure_legacy_api_enabled()

    model_options, embedding_options = _runtime_options(force_refresh=refresh)

    # Force explicit model choice in the UI for every new-agent creation.
    default_model = ""

    default_embedding = os.getenv("LETTA_DEFAULT_EMBEDDING_HANDLE") or os.getenv("LETTA_EMBEDDING_HANDLE") or DEFAULT_EMBEDDING
    if default_embedding and not any(option["key"] == default_embedding for option in embedding_options):
        default_embedding = ""

    for option in embedding_options:
        option["is_default"] = bool(default_embedding and option["key"] == default_embedding)

    return {
        "models": model_options,
        "embeddings": embedding_options,
        "prompts": PROMPT_OPTIONS,
        "defaults": {
            "model": default_model,
            "prompt_key": DEFAULT_PROMPT_KEY,
            "embedding": default_embedding,
        },
    }


@app.get("/api/agents")
async def api_list_agents(limit: int = 100, include_last_interaction: bool = False):
    """List existing agents so the UI can pull and inspect prior state."""
    _ensure_legacy_api_enabled()

    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >= 1")
    if limit > 500:
        limit = 500

    agents = list(client.agents.list())
    items = []
    for agent in agents:
        agent_id = str(getattr(agent, "id", ""))
        last_updated_at = str(getattr(agent, "last_updated_at", ""))
        if include_last_interaction:
            last_interaction_at = _derive_last_interaction_at(agent_id, last_updated_at)
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
            }
        )

    # Prefer recently updated agents first.
    items.sort(key=lambda x: (x["last_updated_at"] or x["created_at"]), reverse=True)

    return {
        "total": len(items),
        "items": items[:limit],
    }

@app.post("/api/agents")
async def api_create_agent(request: AgentCreateRequest):
    _ensure_legacy_api_enabled()

    model_options, embedding_options = _runtime_options()
    allowed_models = {option["key"] for option in model_options}
    allowed_embeddings = {option["key"] for option in embedding_options}

    if not request.model.strip():
        raise HTTPException(status_code=400, detail="Model is required. Please choose one.")

    if request.model not in allowed_models:
        raise HTTPException(status_code=400, detail=f"Invalid model: {request.model}")
    if request.prompt_key not in PROMPT_MAP:
        raise HTTPException(status_code=400, detail=f"Invalid prompt key: {request.prompt_key}")
    if request.embedding and request.embedding not in allowed_embeddings:
        raise HTTPException(status_code=400, detail=f"Invalid embedding handle: {request.embedding}")

    create_args: dict[str, Any] = {
        "name": request.name,
        "system": PROMPT_MAP[request.prompt_key],
        "model": request.model,
        "timezone": "Asia/Shanghai",
        "context_window_limit": 16384,
        "memory_blocks": [
            {
                "label": "persona",
                "value": PERSONAS["linxiaotang"],
            },
            {
                "label": "human",
                "value": HUMAN_TEMPLATE,
            },
        ],
    }
    if request.embedding:
        create_args["embedding"] = request.embedding

    try:
        agent = client.agents.create(**create_args)
    except Exception as exc:
        error_text = str(exc)
        if "Handle" in error_text and "not found" in error_text:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{error_text}. This handle is not registered on the current Letta server. "
                    "If you want LM Studio and Doubao in one server, use a combined env profile (for example .env3)."
                ),
            ) from exc
        raise HTTPException(status_code=400, detail=error_text) from exc

    return {
        "id": agent.id,
        "name": agent.name,
        "model": request.model,
        "embedding": request.embedding,
        "prompt_key": request.prompt_key,
    }

@app.get("/api/agents/{agent_id}/details")
async def api_get_agent_details(agent_id: str):
    _ensure_legacy_api_enabled()

    agent = client.agents.retrieve(agent_id=agent_id)
    tools_raw = list(client.agents.tools.list(agent_id=agent.id))
    tools = {t.name: t.description for t in tools_raw}
    
    blocks = client.agents.blocks.list(agent_id=agent_id)
    memory = {b.label: b.value for b in blocks}
    
    last_updated_at = str(getattr(agent, "last_updated_at", ""))
    last_interaction_at = _derive_last_interaction_at(agent_id, last_updated_at)

    return {
        "id": getattr(agent, "id", agent_id),
        "name": getattr(agent, "name", "Unknown"),
        "agent_type": str(getattr(agent, "agent_type", "Unknown")),
        "model": getattr(agent, "model", "Unknown"),
        "embedding": getattr(agent, "embedding", None),
        "llm_config": _to_jsonable(getattr(agent, "llm_config", None)),
        "embedding_config": _to_jsonable(getattr(agent, "embedding_config", None)),
        "tool_rules": _to_jsonable(getattr(agent, "tool_rules", None)),
        "description": getattr(agent, "description", None),
        "created_at": str(getattr(agent, "created_at", "")),
        "last_updated_at": last_updated_at,
        "last_interaction_at": last_interaction_at,
        "context_window_limit": getattr(agent, "context_window_limit", None),
        "tools": tools,
        "system": getattr(agent, "system", "Unknown"),
        "memory": memory,
    }


@app.get("/api/agents/{agent_id}/persistent_state")
async def api_get_agent_persistent_state(agent_id: str, limit: int = 120, include_system: bool = False):
    """
    Returns persisted state from Letta backend storage (Postgres/pgvector via Letta API):
    - agent metadata
    - memory blocks
    - attached tools
    - persisted conversation history
    """
    _ensure_legacy_api_enabled()

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

        payload = _serialize_message(msg)
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
            "tool_rules": _normalize_text(getattr(agent, "tool_rules", None)),
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

@app.get("/api/agents/{agent_id}/raw_prompt")
async def api_get_raw_prompt(agent_id: str):
    _ensure_legacy_api_enabled()

    messages = list(client.agents.messages.list(agent_id=agent_id))
    recent_messages = messages[-10:] if len(messages) >= 10 else messages
    
    formatted_msgs = []
    for msg in recent_messages:
        content = getattr(msg, "content", "")
        if not content:
            content = getattr(msg, "reasoning", str(msg))
        role = getattr(msg, "role", getattr(msg, "message_type", "unknown"))
        formatted_msgs.append({"role": role, "content": _normalize_text(content)})
        
    return {"messages": formatted_msgs}


@app.get(
    "/api/platform/migration-status",
    tags=["platform-meta"],
    summary="Get migration feature-flag status",
)
async def api_platform_migration_status():
    return {
        "migration_mode": _migration_mode(),
        "platform_api_enabled": _platform_api_enabled(),
        "legacy_api_enabled": _legacy_api_enabled(),
        "strict_capabilities": _is_truthy(os.getenv("AGENT_PLATFORM_STRICT_CAPABILITIES")),
    }


@app.get(
    "/api/platform/capabilities",
    tags=["platform-meta"],
    summary="Get platform capability matrix",
)
async def api_platform_capabilities():
    capabilities = agent_platform.capabilities()
    return {
        "enabled": _platform_api_enabled(),
        "migration_mode": _migration_mode(),
        "legacy_api_enabled": _legacy_api_enabled(),
        "strict_mode": _is_truthy(os.getenv("AGENT_PLATFORM_STRICT_CAPABILITIES")),
        "missing_required": _missing_platform_capabilities(capabilities),
        **capabilities,
    }


@app.get(
    "/api/platform/tools",
    tags=["platform-tools"],
    summary="List tools for Toolbench discovery",
)
async def api_platform_list_tools(search: str = "", limit: int = 100, agent_id: str | None = None):
    _ensure_platform_api_enabled()

    resolved_limit = max(1, min(limit, 500))
    try:
        tools = agent_platform.list_available_tools(search=(search or "").strip() or None, limit=resolved_limit)

        attached_ids: set[str] = set()
        if agent_id:
            attached_ids = {
                str(getattr(tool, "id", "") or "")
                for tool in list(client.agents.tools.list(agent_id=agent_id))
                if str(getattr(tool, "id", "") or "").strip()
            }

        for tool in tools:
            tool_id = str(tool.get("id", "") or "")
            tool["attached_to_agent"] = bool(agent_id and tool_id in attached_ids)

        return {
            "total": len(tools),
            "search": (search or "").strip(),
            "limit": resolved_limit,
            "agent_id": agent_id,
            "items": tools,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/api/platform/tools/test-invoke",
    tags=["platform-tools"],
    summary="Invoke a runtime message to validate tool-call behavior",
)
async def api_platform_tool_test_invoke(request: PlatformToolTestInvokeRequest):
    _ensure_platform_api_enabled()

    agent_id = request.agent_id.strip()
    text = request.input.strip()
    expected_tool_name = (request.expected_tool_name or "").strip()

    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id is required")
    if not text:
        raise HTTPException(status_code=400, detail="input is required")

    try:
        payload = agent_platform.send_runtime_message(
            agent_id=agent_id,
            message=text,
            override_model=(request.override_model or "").strip() or None,
            override_system=(request.override_system or "").strip() or None,
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


@app.get(
    "/api/platform/metadata/prompts-personas",
    tags=["platform-meta"],
    summary="Get prompt and persona metadata",
)
async def api_platform_prompt_persona_metadata():
    _ensure_platform_api_enabled()

    prompts: list[dict[str, Any]] = []
    for option in PROMPT_OPTIONS:
        key = str(option.get("key", "") or "")
        prompt_text = str(PROMPT_MAP.get(key, "") or "")
        prompts.append(
            {
                "key": key,
                "label": str(option.get("label", "") or ""),
                "description": str(option.get("description", "") or ""),
                "preview": _first_non_empty_line(prompt_text)[:180],
                "length": len(prompt_text),
            }
        )

    personas: list[dict[str, Any]] = []
    for key, value in sorted(PERSONAS.items()):
        persona_text = str(value or "")
        personas.append(
            {
                "key": key,
                "preview": _first_non_empty_line(persona_text)[:180],
                "length": len(persona_text),
            }
        )

    return {
        "defaults": {
            "prompt_key": DEFAULT_PROMPT_KEY,
            "persona_key": "linxiaotang",
        },
        "prompts": prompts,
        "personas": personas,
    }


@app.get(
    "/api/platform/metadata/prompts-personas/revisions",
    tags=["platform-meta"],
    summary="Get prompt/persona revision history timeline",
)
async def api_platform_prompt_persona_revisions(
    agent_id: str | None = None,
    field: str | None = None,
    limit: int = 80,
):
    _ensure_platform_api_enabled()

    resolved_field = (field or "").strip().lower() or None
    if resolved_field and resolved_field not in {"system", "persona", "human"}:
        raise HTTPException(status_code=400, detail="field must be one of: system, persona, human")

    resolved_limit = max(1, min(limit, 500))
    resolved_agent_id = (agent_id or "").strip() or None
    items = _read_prompt_persona_revisions(
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


@app.post(
    "/api/platform/agents/{agent_id}/messages",
    tags=["platform-runtime"],
    summary="Send runtime message with optional overrides",
)
async def api_platform_send_message(agent_id: str, request: PlatformRuntimeMessageRequest):
    _ensure_platform_api_enabled()

    text = request.input.strip()
    if not text:
        raise HTTPException(status_code=400, detail="input is required")

    try:
        return agent_platform.send_runtime_message(
            agent_id=agent_id,
            message=text,
            override_model=(request.override_model or "").strip() or None,
            override_system=(request.override_system or "").strip() or None,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch(
    "/api/platform/agents/{agent_id}/system",
    tags=["platform-control"],
    summary="Update persisted system prompt",
)
async def api_platform_update_system(agent_id: str, request: PlatformSystemUpdateRequest):
    _ensure_platform_api_enabled()

    system_text = request.system.strip()
    if not system_text:
        raise HTTPException(status_code=400, detail="system is required")

    try:
        payload = agent_platform.update_system_prompt(agent_id=agent_id, system_prompt=system_text)
        _append_prompt_persona_revision(
            agent_id=agent_id,
            field="system",
            before=str(payload.get("system_before", "") or ""),
            after=str(payload.get("system_after", "") or ""),
            source="api/platform/agents/{agent_id}/system",
        )
        return payload
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch(
    "/api/platform/agents/{agent_id}/model",
    tags=["platform-control"],
    summary="Update persisted agent model",
)
async def api_platform_update_model(agent_id: str, request: PlatformModelUpdateRequest):
    _ensure_platform_api_enabled()

    model_handle = request.model.strip()
    if not model_handle:
        raise HTTPException(status_code=400, detail="model is required")

    try:
        return agent_platform.update_agent_model(agent_id=agent_id, model_handle=model_handle)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch(
    "/api/platform/agents/{agent_id}/core-memory/blocks/{block_label}",
    tags=["platform-control"],
    summary="Update core-memory block value",
)
async def api_platform_update_memory_block(
    agent_id: str,
    block_label: str,
    request: PlatformMemoryBlockUpdateRequest,
):
    _ensure_platform_api_enabled()

    label = block_label.strip()
    if not label:
        raise HTTPException(status_code=400, detail="block_label is required")

    try:
        payload = agent_platform.update_core_memory_block(
            agent_id=agent_id,
            block_label=label,
            value=request.value,
        )
        if label in {"persona", "human"}:
            _append_prompt_persona_revision(
                agent_id=agent_id,
                field=label,
                before=str(payload.get("value_before", "") or ""),
                after=str(payload.get("value_after", "") or ""),
                source=f"api/platform/agents/{{agent_id}}/core-memory/blocks/{label}",
            )
        return payload
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch(
    "/api/platform/agents/{agent_id}/tools/attach/{tool_id}",
    tags=["platform-tools"],
    summary="Attach tool to agent",
)
async def api_platform_attach_tool(agent_id: str, tool_id: str):
    _ensure_platform_api_enabled()

    resolved_tool_id = tool_id.strip()
    if not resolved_tool_id:
        raise HTTPException(status_code=400, detail="tool_id is required")

    try:
        return agent_platform.attach_tool(agent_id=agent_id, tool_id=resolved_tool_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch(
    "/api/platform/agents/{agent_id}/tools/detach/{tool_id}",
    tags=["platform-tools"],
    summary="Detach tool from agent",
)
async def api_platform_detach_tool(agent_id: str, tool_id: str):
    _ensure_platform_api_enabled()

    resolved_tool_id = tool_id.strip()
    if not resolved_tool_id:
        raise HTTPException(status_code=400, detail="tool_id is required")

    try:
        return agent_platform.detach_tool(agent_id=agent_id, tool_id=resolved_tool_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get(
    "/api/platform/test-runs",
    tags=["platform-tests"],
    summary="List orchestrated test runs",
)
async def api_platform_list_test_runs():
    _ensure_platform_api_enabled()

    return {
        "items": test_orchestrator.list_runs(),
    }


@app.post(
    "/api/platform/test-runs",
    tags=["platform-tests"],
    summary="Create orchestrated test run",
)
async def api_platform_create_test_run(request: PlatformTestRunRequest):
    _ensure_platform_api_enabled()

    try:
        return test_orchestrator.create_run(
            run_type=request.run_type,
            model=request.model,
            embedding=request.embedding,
            rounds=request.rounds,
            config_path=request.config_path,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get(
    "/api/platform/test-runs/{run_id}",
    tags=["platform-tests"],
    summary="Get orchestrated test run",
)
async def api_platform_get_test_run(run_id: str):
    _ensure_platform_api_enabled()

    run = test_orchestrator.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run_id not found")
    return run


@app.post(
    "/api/platform/test-runs/{run_id}/cancel",
    tags=["platform-tests"],
    summary="Cancel orchestrated test run",
)
async def api_platform_cancel_test_run(run_id: str):
    _ensure_platform_api_enabled()

    run = test_orchestrator.cancel_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run_id not found")
    return run


@app.get(
    "/api/platform/test-runs/{run_id}/artifacts",
    tags=["platform-tests"],
    summary="List test run artifacts",
)
async def api_platform_list_test_run_artifacts(run_id: str):
    _ensure_platform_api_enabled()

    artifacts = test_orchestrator.list_artifacts(run_id)
    if artifacts is None:
        raise HTTPException(status_code=404, detail="run_id not found")
    return {
        "run_id": run_id,
        "items": artifacts,
    }


@app.get(
    "/api/platform/test-runs/{run_id}/artifacts/{artifact_id}",
    tags=["platform-tests"],
    summary="Read test run artifact content",
)
async def api_platform_read_test_run_artifact(run_id: str, artifact_id: str, max_lines: int = 400):
    _ensure_platform_api_enabled()

    payload = test_orchestrator.read_artifact(run_id, artifact_id, max_lines=max_lines)
    if payload is None:
        raise HTTPException(status_code=404, detail="run_id or artifact_id not found")
    return payload

@app.post("/api/chat")
async def api_chat(request: ChatRequest):
    _ensure_legacy_api_enabled()

    is_datetime_turn = _is_datetime_query(request.message)

    try:
        return agent_platform.send_legacy_chat_message(
            agent_id=request.agent_id,
            message=request.message,
            datetime_system_hint=_runtime_datetime_system_hint() if is_datetime_turn else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8284)
