from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

# Add project root to sys.path to resolve imports properly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from letta_client import Letta
from utils.agent_lifecycle_registry import AgentLifecycleRegistry, AgentLifecycleRegistryError
from utils.agent_platform_service import AgentPlatformService
from utils.commenting_service import CommentingService
from utils.custom_tool_registry import CustomToolRegistry, ToolRegistryError
from utils.platform_test_orchestrator import PlatformTestOrchestrator
from utils.prompt_persona_registry import PromptPersonaRegistry, RegistryError
from prompts.persona import HUMAN_TEMPLATE

APP_VERSION = os.getenv("AGENT_PLATFORM_API_VERSION", "0.2.0")
ScenarioType = Literal["chat", "comment"]
CommentingTaskShape = Literal["compact", "all_in_system", "structured_output"]


@asynccontextmanager
async def _app_lifespan(_: FastAPI):
    _validate_platform_capabilities_startup()
    yield

app = FastAPI(
    title="Agent Platform Dev API",
    version=APP_VERSION,
    summary="Runtime and control APIs for local Agent Platform development",
    lifespan=_app_lifespan,
    description=(
        "Provides versioned Dev API routes for Agent Platform runtime/control/test orchestration. "
        "Designed for backend-first API consumption and ADE frontend integration."
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
    scenario: ScenarioType = "chat"
    name: str = "dev-agent"
    model: str = ""
    prompt_key: str = "chat_v20260418"
    persona_key: str = "chat_linxiaotang"
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
        "platform_flag_gate_check",
        "platform_dual_run_gate",
        "persona_guardrail_runner",
        "memory_update_runner",
    ]
    model: str | None = None
    embedding: str | None = None
    rounds: int | None = None
    config_path: str | None = None


class ApiOptionEntryResponse(BaseModel):
    key: str
    label: str
    description: str
    scenario: ScenarioType | None = None
    available: bool | None = None
    is_default: bool | None = None


class ApiOptionsDefaultsResponse(BaseModel):
    scenario: ScenarioType
    model: str
    prompt_key: str
    persona_key: str
    embedding: str


class ApiCommentingRuntimeDefaultsResponse(BaseModel):
    max_tokens: int
    timeout_seconds: float
    task_shape: CommentingTaskShape


class ApiOptionsResponse(BaseModel):
    scenario: ScenarioType
    models: list[ApiOptionEntryResponse]
    embeddings: list[ApiOptionEntryResponse]
    prompts: list[ApiOptionEntryResponse]
    personas: list[ApiOptionEntryResponse]
    defaults: ApiOptionsDefaultsResponse
    commenting: ApiCommentingRuntimeDefaultsResponse | None = None


class ApiAgentListItemResponse(BaseModel):
    id: str
    name: str
    model: str
    created_at: str
    last_updated_at: str
    last_interaction_at: str
    archived: bool = False


class ApiAgentListResponse(BaseModel):
    total: int
    items: list[ApiAgentListItemResponse]


class ApiAgentCreateResponse(BaseModel):
    id: str
    name: str
    scenario: ScenarioType
    model: str
    embedding: str | None = None
    prompt_key: str
    persona_key: str


class ApiAgentLifecycleResponse(BaseModel):
    id: str
    name: str
    model: str
    archived: bool
    archived_at: str | None = None
    updated_at: str


class ApiAgentPurgeResponse(BaseModel):
    ok: bool
    id: str
    kind: str


class ApiAgentDetailsResponse(BaseModel):
    id: str
    name: str
    agent_type: str
    model: str
    embedding: str | None = None
    llm_config: Any = None
    embedding_config: Any = None
    tool_rules: Any = None
    description: str | None = None
    created_at: str
    last_updated_at: str
    last_interaction_at: str
    context_window_limit: int | None = None
    tools: dict[str, str]
    system: str
    memory: dict[str, str]


class ApiPersistentAgentSummaryResponse(BaseModel):
    id: str
    name: str
    agent_type: str
    model: str
    embedding: str | None = None
    created_at: str
    last_updated_at: str
    context_window_limit: int | None = None
    tool_rules: str


class ApiPersistentMemoryBlockResponse(BaseModel):
    label: str
    description: str
    limit: int | None = None
    value: str


class ApiPersistentToolResponse(BaseModel):
    id: str
    name: str
    description: str


class ApiConversationHistoryItemResponse(BaseModel):
    id: str
    created_at: str
    message_type: str
    role: str
    status: str
    name: str | None = None
    tool_arguments: str | None = None
    content: str


class ApiConversationHistoryResponse(BaseModel):
    total_persisted: int
    displayed: int
    limit: int
    counts_by_type: dict[str, int]
    items: list[ApiConversationHistoryItemResponse]


class ApiPersistentStateResponse(BaseModel):
    source: str
    agent: ApiPersistentAgentSummaryResponse
    memory_blocks: list[ApiPersistentMemoryBlockResponse]
    tools: list[ApiPersistentToolResponse]
    conversation_history: ApiConversationHistoryResponse


class ApiRawPromptMessageResponse(BaseModel):
    role: str
    content: str


class ApiRawPromptResponse(BaseModel):
    messages: list[ApiRawPromptMessageResponse]


class ApiPlatformRuntimeCapabilitiesResponse(BaseModel):
    per_request_model_override: bool
    per_request_model_override_via_extra_body: bool
    per_request_system_override: bool
    per_request_system_override_via_extra_body: bool


class ApiPlatformControlCapabilitiesResponse(BaseModel):
    update_system_prompt: bool
    update_agent_model: bool
    update_core_memory_block: bool
    attach_tool: bool
    detach_tool: bool


class ApiPlatformSdkCapabilitiesResponse(BaseModel):
    messages_create_params: list[str]
    agents_update_params: list[str]
    blocks_update_params: list[str]


class ApiPlatformCapabilitiesResponse(BaseModel):
    enabled: bool
    strict_mode: bool
    missing_required: list[str]
    runtime: ApiPlatformRuntimeCapabilitiesResponse
    control: ApiPlatformControlCapabilitiesResponse
    sdk: ApiPlatformSdkCapabilitiesResponse


class ApiPlatformToolResponse(BaseModel):
    id: str
    name: str
    description: str
    tool_type: str
    source_type: str
    created_at: str
    last_updated_at: str
    tags: list[str]
    attached_to_agent: bool | None = None
    managed: bool | None = None
    read_only: bool | None = None
    archived: bool | None = None
    slug: str | None = None


class ApiPlatformToolListResponse(BaseModel):
    total: int
    search: str
    limit: int
    agent_id: str | None = None
    items: list[ApiPlatformToolResponse]


class ApiPlatformToolTestInvokeResponse(BaseModel):
    agent_id: str
    input: str
    expected_tool_name: str | None = None
    expected_tool_matched: bool | None = None
    tool_call_count: int
    tool_return_count: int
    result: dict[str, Any]


class ApiPromptPersonaDefaultResponse(BaseModel):
    scenario: ScenarioType
    prompt_key: str
    persona_key: str


class ApiPromptMetadataResponse(BaseModel):
    scenario: ScenarioType
    key: str
    label: str
    description: str
    preview: str
    length: int


class ApiPersonaMetadataResponse(BaseModel):
    scenario: ScenarioType
    key: str
    preview: str
    length: int


class ApiPromptPersonaMetadataResponse(BaseModel):
    defaults: ApiPromptPersonaDefaultResponse
    prompts: list[ApiPromptMetadataResponse]
    personas: list[ApiPersonaMetadataResponse]


class PromptTemplateWriteRequest(BaseModel):
    scenario: ScenarioType = "chat"
    key: str
    label: str = ""
    description: str = ""
    content: str


class PromptTemplatePatchRequest(BaseModel):
    label: str | None = None
    description: str | None = None
    content: str | None = None


class PersonaTemplateWriteRequest(BaseModel):
    scenario: ScenarioType = "chat"
    key: str
    label: str = ""
    description: str = ""
    content: str


class PersonaTemplatePatchRequest(BaseModel):
    label: str | None = None
    description: str | None = None
    content: str | None = None


class ApiTemplateRecordResponse(BaseModel):
    kind: str
    scenario: ScenarioType
    key: str
    label: str
    description: str
    content: str
    preview: str
    length: int
    archived: bool
    source_path: str
    updated_at: str


class ApiTemplateListResponse(BaseModel):
    total: int
    scenario: ScenarioType | None = None
    include_archived: bool
    items: list[ApiTemplateRecordResponse]


class ToolCenterCreateRequest(BaseModel):
    slug: str
    source_code: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    source_type: str = "python"
    enable_parallel_execution: bool | None = None
    default_requires_approval: bool | None = None
    return_char_limit: int | None = None
    pip_requirements: list[dict[str, Any]] | None = None
    npm_requirements: list[dict[str, Any]] | None = None


class ToolCenterUpdateRequest(BaseModel):
    source_code: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    source_type: str | None = None
    enable_parallel_execution: bool | None = None
    default_requires_approval: bool | None = None
    return_char_limit: int | None = None
    pip_requirements: list[dict[str, Any]] | None = None
    npm_requirements: list[dict[str, Any]] | None = None


class ApiToolCenterItemResponse(BaseModel):
    slug: str | None = None
    tool_id: str
    name: str
    description: str
    tool_type: str
    source_type: str
    tags: list[str] = Field(default_factory=list)
    managed: bool
    read_only: bool
    archived: bool
    source_path: str | None = None
    source_code: str | None = None
    created_at: str = ""
    last_updated_at: str = ""
    updated_at: str | None = None
    archived_at: str | None = None


class ApiToolCenterListResponse(BaseModel):
    total: int
    include_archived: bool
    include_builtin: bool
    items: list[ApiToolCenterItemResponse]


class ApiPromptPersonaRevisionResponse(BaseModel):
    revision_id: str
    recorded_at: str
    agent_id: str
    field: str
    source: str
    before: str
    after: str
    before_preview: str
    after_preview: str
    before_length: int
    after_length: int
    delta_length: int


class ApiPromptPersonaRevisionsResponse(BaseModel):
    total: int
    limit: int
    agent_id: str | None = None
    field: str | None = None
    items: list[ApiPromptPersonaRevisionResponse]


class ApiRuntimeMessageResponse(BaseModel):
    agent_id: str
    override_model: str | None = None
    override_system: str | None = None
    result: dict[str, Any]


class ApiSystemUpdateResponse(BaseModel):
    agent_id: str
    model: str
    system_before: str
    system_after: str


class ApiModelUpdateResponse(BaseModel):
    agent_id: str
    model_before: str
    model_after: str
    system: str


class ApiMemoryBlockUpdateResponse(BaseModel):
    agent_id: str
    block_label: str
    value_before: str
    value_after: str
    description: str
    limit: int | None = None


class ApiToolAttachDetachResponse(BaseModel):
    agent_id: str
    tool_id: str
    tool_was_attached: bool
    tool_is_attached: bool
    tool_count_before: int
    tool_count_after: int


class ApiTestArtifactResponse(BaseModel):
    artifact_id: str
    type: str
    path: str
    exists: bool
    size_bytes: int


class ApiTestRunRecordResponse(BaseModel):
    run_id: str
    run_type: str
    status: str
    command: list[str]
    created_at: str
    started_at: str
    finished_at: str
    exit_code: int | None = None
    log_file: str
    cancel_requested: bool
    output_tail: list[str] = Field(default_factory=list)
    error: str
    artifacts: list[ApiTestArtifactResponse] = Field(default_factory=list)


class ApiTestRunListResponse(BaseModel):
    items: list[ApiTestRunRecordResponse]


class ApiTestArtifactListResponse(BaseModel):
    run_id: str
    items: list[ApiTestArtifactResponse]


class ApiTestArtifactReadResponse(BaseModel):
    run_id: str
    artifact: ApiTestArtifactResponse
    content: str
    truncated: bool
    line_count: int


class ApiChatResponse(BaseModel):
    total_steps: int = 0
    sequence: list[dict[str, Any]] = Field(default_factory=list)
    memory_diff: dict[str, Any] = Field(default_factory=dict)


class CommentingGenerateRequest(BaseModel):
    scenario: ScenarioType = "comment"
    input: str
    prompt_key: str = "comment_v20260418"
    persona_key: str = "comment_linxiaotang"
    model: str | None = None
    max_tokens: int | None = Field(default=None, ge=0)
    timeout_seconds: float | None = Field(default=None, gt=0)
    task_shape: CommentingTaskShape | None = None


class ApiCommentingGenerateResponse(BaseModel):
    scenario: ScenarioType
    prompt_key: str
    persona_key: str
    model: str
    content: str
    provider: str
    max_tokens: int
    timeout_seconds: float
    task_shape: CommentingTaskShape
    content_source: str | None = None
    selected_attempt: str
    finish_reason: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    received_at: str | None = None
    raw_request: dict[str, Any] = Field(default_factory=dict)
    raw_reply: dict[str, Any] = Field(default_factory=dict)


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
prompt_persona_registry = PromptPersonaRegistry(PROJECT_ROOT)
custom_tool_registry = CustomToolRegistry(PROJECT_ROOT)
agent_lifecycle_registry = AgentLifecycleRegistry(PROJECT_ROOT)
commenting_service = CommentingService()
REVISION_LOG_DIR = PROJECT_ROOT / "diagnostics"
REVISION_LOG_FILE = REVISION_LOG_DIR / "prompt_persona_revisions.jsonl"


def _is_truthy(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _platform_api_enabled() -> bool:
    return _is_truthy(os.getenv("AGENT_PLATFORM_API_ENABLED", "1"))


def _ensure_platform_api_enabled() -> None:
    if _platform_api_enabled():
        return
    raise HTTPException(
        status_code=503,
        detail="Agent Platform API is disabled by AGENT_PLATFORM_API_ENABLED.",
    )


def _is_not_found_error(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return "not found" in text or "404" in text


def _fetch_agent_or_404(agent_id: str) -> Any:
    try:
        return client.agents.retrieve(agent_id=agent_id)
    except Exception as exc:
        if _is_not_found_error(exc):
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found") from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _agent_lifecycle_payload(record: dict[str, Any], *, fallback_name: str = "", fallback_model: str = "") -> dict[str, Any]:
    return {
        "id": str(record.get("id", "") or ""),
        "name": str(record.get("name", "") or fallback_name),
        "model": str(record.get("model", "") or fallback_model),
        "archived": bool(record.get("archived", False)),
        "archived_at": record.get("archived_at"),
        "updated_at": str(record.get("updated_at", "") or ""),
    }


def _ensure_agent_not_archived(agent_id: str) -> None:
    if agent_lifecycle_registry.is_archived(agent_id):
        raise HTTPException(
            status_code=409,
            detail="Agent is archived. Restore it before runtime or control operations.",
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


def _validate_platform_capabilities_startup() -> None:
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


def _invalidate_options_cache() -> None:
    _OPTIONS_CACHE["expires_at"] = 0.0


def _commenting_runtime_defaults() -> ApiCommentingRuntimeDefaultsResponse:
    defaults = commenting_service.runtime_defaults()
    task_shape = str(defaults.get("task_shape", "compact") or "compact").strip().lower()
    if task_shape not in {"compact", "all_in_system", "structured_output"}:
        task_shape = "compact"

    return ApiCommentingRuntimeDefaultsResponse(
        max_tokens=int(defaults.get("max_tokens", 1536)),
        timeout_seconds=float(defaults.get("timeout_seconds", 60.0)),
        task_shape=task_shape,
    )


def _normalize_scenario(value: str | None, *, default: ScenarioType = "chat") -> ScenarioType:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return default
    if normalized not in {"chat", "comment"}:
        raise HTTPException(status_code=400, detail="scenario must be either 'chat' or 'comment'")
    return normalized


def _active_prompt_records(scenario: ScenarioType | None = None) -> list[dict[str, Any]]:
    records = [
        record
        for record in prompt_persona_registry.list_templates(
            "prompt",
            include_archived=False,
            scenario=scenario,
        )
        if not bool(record.get("archived", False))
    ]
    if scenario:
        records = [
            record
            for record in records
            if str(record.get("key", "") or "").startswith(f"{scenario}_")
        ]
    return records


def _active_persona_records(scenario: ScenarioType | None = None) -> list[dict[str, Any]]:
    records = [
        record
        for record in prompt_persona_registry.list_templates(
            "persona",
            include_archived=False,
            scenario=scenario,
        )
        if not bool(record.get("archived", False))
    ]
    if scenario:
        records = [
            record
            for record in records
            if str(record.get("key", "") or "").startswith(f"{scenario}_")
        ]
    return records


def _prompt_content_map(scenario: ScenarioType | None = None) -> dict[str, str]:
    return {
        str(record.get("key", "")): str(record.get("content", "") or "")
        for record in _active_prompt_records(scenario)
        if str(record.get("key", "")).strip()
    }


def _persona_content_map(scenario: ScenarioType | None = None) -> dict[str, str]:
    return {
        str(record.get("key", "")): str(record.get("content", "") or "")
        for record in _active_persona_records(scenario)
        if str(record.get("key", "")).strip()
    }


def _prompt_option_entries(scenario: ScenarioType | None = None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for record in _active_prompt_records(scenario):
        entries.append(
            {
                "key": str(record.get("key", "") or ""),
                "label": str(record.get("label", "") or ""),
                "description": str(record.get("description", "") or ""),
                "scenario": str(record.get("scenario", "") or "") or None,
            }
        )
    return entries


def _persona_option_entries(scenario: ScenarioType | None = None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for record in _active_persona_records(scenario):
        entries.append(
            {
                "key": str(record.get("key", "") or ""),
                "label": str(record.get("label", "") or ""),
                "description": str(record.get("description", "") or ""),
                "scenario": str(record.get("scenario", "") or "") or None,
            }
        )
    return entries


def _resolve_default_prompt_key(prompt_options: list[dict[str, Any]], scenario: ScenarioType) -> str:
    preferred = SCENARIO_DEFAULTS[scenario]["prompt_key"]
    if any(str(option.get("key", "")) == preferred for option in prompt_options):
        return preferred
    return str(prompt_options[0].get("key", "") if prompt_options else "")


def _resolve_default_persona_key(persona_options: list[dict[str, Any]], scenario: ScenarioType) -> str:
    preferred = SCENARIO_DEFAULTS[scenario]["persona_key"]
    if any(str(option.get("key", "")) == preferred for option in persona_options):
        return preferred
    return str(persona_options[0].get("key", "") if persona_options else "")


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


def _as_template_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": str(record.get("kind", "") or ""),
        "scenario": str(record.get("scenario", "") or "chat"),
        "key": str(record.get("key", "") or ""),
        "label": str(record.get("label", "") or ""),
        "description": str(record.get("description", "") or ""),
        "content": str(record.get("content", "") or ""),
        "preview": str(record.get("preview", "") or ""),
        "length": int(record.get("length", 0) or 0),
        "archived": bool(record.get("archived", False)),
        "source_path": str(record.get("source_path", "") or ""),
        "updated_at": str(record.get("updated_at", "") or ""),
    }


def _managed_tool_tags(extra_tags: list[str] | None = None) -> list[str]:
    tags = [MANAGED_TOOL_TAG]
    for raw in extra_tags or []:
        tag = str(raw or "").strip()
        if not tag or tag in tags:
            continue
        tags.append(tag)
    return tags


def _as_tool_center_item(
    *,
    managed_entry: dict[str, Any] | None,
    remote_tool: dict[str, Any] | None,
    include_source: bool,
) -> dict[str, Any]:
    if managed_entry:
        return {
            "slug": str(managed_entry.get("slug", "") or ""),
            "tool_id": str(managed_entry.get("tool_id", "") or ""),
            "name": str((remote_tool or {}).get("name", managed_entry.get("name", "")) or ""),
            "description": str((remote_tool or {}).get("description", managed_entry.get("description", "")) or ""),
            "tool_type": str((remote_tool or {}).get("tool_type", managed_entry.get("tool_type", "custom")) or "custom"),
            "source_type": str((remote_tool or {}).get("source_type", managed_entry.get("source_type", "python")) or "python"),
            "tags": [str(tag) for tag in ((remote_tool or {}).get("tags", managed_entry.get("tags", [])) or []) if str(tag).strip()],
            "managed": True,
            "read_only": False,
            "archived": bool(managed_entry.get("archived", False)),
            "source_path": str(managed_entry.get("source_path", "") or "") or None,
            "source_code": str(managed_entry.get("source_code", "") or "") if include_source else None,
            "created_at": str((remote_tool or {}).get("created_at", managed_entry.get("created_at", "")) or ""),
            "last_updated_at": str((remote_tool or {}).get("last_updated_at", managed_entry.get("updated_at", "")) or ""),
            "updated_at": str(managed_entry.get("updated_at", "") or "") or None,
            "archived_at": managed_entry.get("archived_at"),
        }

    tool = remote_tool or {}
    return {
        "slug": None,
        "tool_id": str(tool.get("id", "") or ""),
        "name": str(tool.get("name", "") or ""),
        "description": str(tool.get("description", "") or ""),
        "tool_type": str(tool.get("tool_type", "") or ""),
        "source_type": str(tool.get("source_type", "") or ""),
        "tags": [str(tag) for tag in (tool.get("tags", []) or []) if str(tag).strip()],
        "managed": False,
        "read_only": True,
        "archived": False,
        "source_path": None,
        "source_code": None,
        "created_at": str(tool.get("created_at", "") or ""),
        "last_updated_at": str(tool.get("last_updated_at", "") or ""),
        "updated_at": None,
        "archived_at": None,
    }

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open(os.path.join(os.path.dirname(__file__), "static", "index.html"), "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/v1/options", response_model=ApiOptionsResponse)
async def api_get_options(refresh: bool = False, scenario: str = "chat"):
    _ensure_platform_api_enabled()
    resolved_scenario = _normalize_scenario(scenario)

    model_options, embedding_options = _runtime_options(force_refresh=refresh)
    prompt_options = _prompt_option_entries(resolved_scenario)
    persona_options = _persona_option_entries(resolved_scenario)

    # Force explicit model choice in the UI for every new-agent creation.
    default_model = ""
    default_prompt_key = _resolve_default_prompt_key(prompt_options, resolved_scenario)
    default_persona_key = _resolve_default_persona_key(persona_options, resolved_scenario)

    default_embedding = os.getenv("LETTA_DEFAULT_EMBEDDING_HANDLE") or os.getenv("LETTA_EMBEDDING_HANDLE") or DEFAULT_EMBEDDING
    if default_embedding and not any(option["key"] == default_embedding for option in embedding_options):
        default_embedding = ""

    for option in embedding_options:
        option["is_default"] = bool(default_embedding and option["key"] == default_embedding)

    return {
        "scenario": resolved_scenario,
        "models": model_options,
        "embeddings": embedding_options,
        "prompts": prompt_options,
        "personas": persona_options,
        "defaults": {
            "scenario": resolved_scenario,
            "model": default_model,
            "prompt_key": default_prompt_key,
            "persona_key": default_persona_key,
            "embedding": default_embedding,
        },
        "commenting": _commenting_runtime_defaults(),
    }


@app.get("/api/v1/agents", response_model=ApiAgentListResponse)
async def api_list_agents(limit: int = 100, include_last_interaction: bool = False, include_archived: bool = False):
    """List existing agents so the UI can pull and inspect prior state."""
    _ensure_platform_api_enabled()

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
                "archived": is_archived,
            }
        )

    # Prefer recently updated agents first.
    items.sort(key=lambda x: (x["last_updated_at"] or x["created_at"]), reverse=True)

    return {
        "total": len(items),
        "items": items[:limit],
    }

@app.post("/api/v1/agents", response_model=ApiAgentCreateResponse)
async def api_create_agent(request: AgentCreateRequest):
    _ensure_platform_api_enabled()
    resolved_scenario = _normalize_scenario(request.scenario)
    if resolved_scenario != "chat":
        raise HTTPException(
            status_code=400,
            detail="/api/v1/agents supports only scenario='chat'. Use /api/v1/commenting/generate for stateless comments.",
        )

    model_options, embedding_options = _runtime_options()
    prompt_map = _prompt_content_map("chat")
    persona_map = _persona_content_map("chat")
    allowed_models = {option["key"] for option in model_options}
    allowed_embeddings = {option["key"] for option in embedding_options}

    if not request.model.strip():
        raise HTTPException(status_code=400, detail="Model is required. Please choose one.")

    if request.model not in allowed_models:
        raise HTTPException(status_code=400, detail=f"Invalid model: {request.model}")
    if not request.prompt_key.startswith("chat_"):
        raise HTTPException(status_code=400, detail=f"Prompt key '{request.prompt_key}' is not valid for scenario 'chat'")
    if not request.persona_key.startswith("chat_"):
        raise HTTPException(status_code=400, detail=f"Persona key '{request.persona_key}' is not valid for scenario 'chat'")
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


@app.post(
    "/api/v1/platform/agents/{agent_id}/archive",
    response_model=ApiAgentLifecycleResponse,
    tags=["platform-control"],
    summary="Archive agent (soft delete)",
)
async def api_platform_archive_agent(agent_id: str):
    _ensure_platform_api_enabled()

    resolved_agent_id = agent_id.strip()
    if not resolved_agent_id:
        raise HTTPException(status_code=400, detail="agent_id is required")

    agent = _fetch_agent_or_404(resolved_agent_id)
    try:
        archived = agent_lifecycle_registry.archive_agent(
            agent_id=resolved_agent_id,
            name=str(getattr(agent, "name", "")),
            model=str(getattr(agent, "model", "")),
        )
    except AgentLifecycleRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _agent_lifecycle_payload(
        archived,
        fallback_name=str(getattr(agent, "name", "")),
        fallback_model=str(getattr(agent, "model", "")),
    )


@app.post(
    "/api/v1/platform/agents/{agent_id}/restore",
    response_model=ApiAgentLifecycleResponse,
    tags=["platform-control"],
    summary="Restore archived agent",
)
async def api_platform_restore_agent(agent_id: str):
    _ensure_platform_api_enabled()

    resolved_agent_id = agent_id.strip()
    if not resolved_agent_id:
        raise HTTPException(status_code=400, detail="agent_id is required")

    archived_record = agent_lifecycle_registry.get_record(resolved_agent_id)
    if not archived_record or not bool(archived_record.get("archived", False)):
        raise HTTPException(status_code=400, detail=f"Agent '{resolved_agent_id}' is not archived")

    agent = _fetch_agent_or_404(resolved_agent_id)
    try:
        restored = agent_lifecycle_registry.restore_agent(resolved_agent_id)
    except AgentLifecycleRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _agent_lifecycle_payload(
        restored,
        fallback_name=str(getattr(agent, "name", "")),
        fallback_model=str(getattr(agent, "model", "")),
    )


def _purge_archived_agent(agent_id: str) -> dict[str, Any]:
    resolved_agent_id = agent_id.strip()
    if not resolved_agent_id:
        raise HTTPException(status_code=400, detail="agent_id is required")

    archived_record = agent_lifecycle_registry.get_record(resolved_agent_id)
    if not archived_record or not bool(archived_record.get("archived", False)):
        raise HTTPException(status_code=400, detail=f"Agent '{resolved_agent_id}' must be archived before purge")

    try:
        agent_platform.delete_agent(agent_id=resolved_agent_id)
    except Exception as exc:
        if not _is_not_found_error(exc):
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


@app.delete(
    "/api/v1/platform/agents/{agent_id}/purge",
    response_model=ApiAgentPurgeResponse,
    tags=["platform-control"],
    summary="Purge archived agent (hard delete)",
)
async def api_platform_purge_agent(agent_id: str):
    _ensure_platform_api_enabled()
    return _purge_archived_agent(agent_id)


@app.delete(
    "/api/v1/agents/{agent_id}",
    response_model=ApiAgentPurgeResponse,
    tags=["platform-control"],
    summary="Delete archived agent (hard delete)",
)
async def api_delete_agent(agent_id: str):
    _ensure_platform_api_enabled()
    return _purge_archived_agent(agent_id)

@app.get("/api/v1/agents/{agent_id}/details", response_model=ApiAgentDetailsResponse)
async def api_get_agent_details(agent_id: str):
    _ensure_platform_api_enabled()

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


@app.get("/api/v1/agents/{agent_id}/persistent_state", response_model=ApiPersistentStateResponse)
async def api_get_agent_persistent_state(agent_id: str, limit: int = 120, include_system: bool = False):
    """
    Returns persisted state from Letta backend storage (Postgres/pgvector via Letta API):
    - agent metadata
    - memory blocks
    - attached tools
    - persisted conversation history
    """
    _ensure_platform_api_enabled()

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

@app.get("/api/v1/agents/{agent_id}/raw_prompt", response_model=ApiRawPromptResponse)
async def api_get_raw_prompt(agent_id: str):
    _ensure_platform_api_enabled()

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
    "/api/v1/platform/capabilities",
    response_model=ApiPlatformCapabilitiesResponse,
    tags=["platform-meta"],
    summary="Get platform capability matrix",
)
async def api_platform_capabilities():
    capabilities = agent_platform.capabilities()
    return {
        "enabled": _platform_api_enabled(),
        "strict_mode": _is_truthy(os.getenv("AGENT_PLATFORM_STRICT_CAPABILITIES")),
        "missing_required": _missing_platform_capabilities(capabilities),
        **capabilities,
    }


@app.get(
    "/api/v1/platform/tools",
    response_model=ApiPlatformToolListResponse,
    tags=["platform-tools"],
    summary="List tools for Toolbench discovery",
)
async def api_platform_list_tools(search: str = "", limit: int = 100, agent_id: str | None = None):
    _ensure_platform_api_enabled()

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


@app.post(
    "/api/v1/platform/tools/test-invoke",
    response_model=ApiPlatformToolTestInvokeResponse,
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

    _ensure_agent_not_archived(agent_id)

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
    "/api/v1/platform/metadata/prompts-personas",
    response_model=ApiPromptPersonaMetadataResponse,
    tags=["platform-meta"],
    summary="Get prompt and persona metadata",
)
async def api_platform_prompt_persona_metadata(scenario: str = "chat"):
    _ensure_platform_api_enabled()

    resolved_scenario = _normalize_scenario(scenario)

    prompt_records = _active_prompt_records(resolved_scenario)
    persona_records = _active_persona_records(resolved_scenario)

    prompts: list[dict[str, Any]] = []
    for record in prompt_records:
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
    for record in persona_records:
        personas.append(
            {
                "scenario": str(record.get("scenario", "") or resolved_scenario),
                "key": str(record.get("key", "") or ""),
                "preview": str(record.get("preview", "") or ""),
                "length": int(record.get("length", 0) or 0),
            }
        )

    default_prompt_key = _resolve_default_prompt_key(_prompt_option_entries(resolved_scenario), resolved_scenario)
    default_persona_key = _resolve_default_persona_key(_persona_option_entries(resolved_scenario), resolved_scenario)

    return {
        "defaults": {
            "scenario": resolved_scenario,
            "prompt_key": default_prompt_key,
            "persona_key": default_persona_key,
        },
        "prompts": prompts,
        "personas": personas,
    }


@app.get(
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


@app.get(
    "/api/v1/platform/prompt-center/prompts",
    response_model=ApiTemplateListResponse,
    tags=["platform-prompts"],
    summary="List system prompt templates",
)
async def api_prompt_center_list_prompts(include_archived: bool = False, scenario: str | None = None):
    _ensure_platform_api_enabled()

    resolved_scenario = _normalize_scenario(scenario) if scenario else None

    try:
        records = prompt_persona_registry.list_templates(
            "prompt",
            include_archived=include_archived,
            scenario=resolved_scenario,
        )
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = [_as_template_record(record) for record in records]
    return {
        "total": len(payload),
        "scenario": resolved_scenario,
        "include_archived": include_archived,
        "items": payload,
    }


@app.get(
    "/api/v1/platform/prompt-center/prompts/{key}",
    response_model=ApiTemplateRecordResponse,
    tags=["platform-prompts"],
    summary="Get system prompt template",
)
async def api_prompt_center_get_prompt(key: str, archived: bool = False, scenario: str | None = None):
    _ensure_platform_api_enabled()

    resolved_scenario = _normalize_scenario(scenario) if scenario else None

    try:
        record = prompt_persona_registry.get_template(
            "prompt",
            key,
            archived=archived,
            scenario=resolved_scenario,
        )
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not record:
        raise HTTPException(status_code=404, detail="Prompt template not found")
    return _as_template_record(record)


@app.post(
    "/api/v1/platform/prompt-center/prompts",
    response_model=ApiTemplateRecordResponse,
    tags=["platform-prompts"],
    summary="Create system prompt template",
)
async def api_prompt_center_create_prompt(request: PromptTemplateWriteRequest):
    _ensure_platform_api_enabled()

    if not request.content.strip():
        raise HTTPException(status_code=400, detail="content is required")

    try:
        record = prompt_persona_registry.create_template(
            "prompt",
            key=request.key,
            content=request.content,
            label=request.label,
            description=request.description,
            scenario=request.scenario,
        )
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _invalidate_options_cache()
    return _as_template_record(record)


@app.patch(
    "/api/v1/platform/prompt-center/prompts/{key}",
    response_model=ApiTemplateRecordResponse,
    tags=["platform-prompts"],
    summary="Update system prompt template",
)
async def api_prompt_center_update_prompt(key: str, request: PromptTemplatePatchRequest):
    _ensure_platform_api_enabled()

    if request.label is None and request.description is None and request.content is None:
        raise HTTPException(status_code=400, detail="At least one field must be provided")

    try:
        record = prompt_persona_registry.update_template(
            "prompt",
            key=key,
            content=request.content,
            label=request.label,
            description=request.description,
        )
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _invalidate_options_cache()
    return _as_template_record(record)


@app.post(
    "/api/v1/platform/prompt-center/prompts/{key}/archive",
    response_model=ApiTemplateRecordResponse,
    tags=["platform-prompts"],
    summary="Archive system prompt template",
)
async def api_prompt_center_archive_prompt(key: str, scenario: str | None = None):
    _ensure_platform_api_enabled()

    resolved_scenario = _normalize_scenario(scenario) if scenario else None

    try:
        record = prompt_persona_registry.archive_template("prompt", key, scenario=resolved_scenario)
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _invalidate_options_cache()
    return _as_template_record(record)


@app.post(
    "/api/v1/platform/prompt-center/prompts/{key}/restore",
    response_model=ApiTemplateRecordResponse,
    tags=["platform-prompts"],
    summary="Restore archived system prompt template",
)
async def api_prompt_center_restore_prompt(key: str, scenario: str | None = None):
    _ensure_platform_api_enabled()

    resolved_scenario = _normalize_scenario(scenario) if scenario else None

    try:
        record = prompt_persona_registry.restore_template("prompt", key, scenario=resolved_scenario)
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _invalidate_options_cache()
    return _as_template_record(record)


@app.delete(
    "/api/v1/platform/prompt-center/prompts/{key}/purge",
    tags=["platform-prompts"],
    summary="Purge archived system prompt template",
)
async def api_prompt_center_purge_prompt(key: str, scenario: str | None = None):
    _ensure_platform_api_enabled()

    resolved_scenario = _normalize_scenario(scenario) if scenario else None

    try:
        prompt_persona_registry.purge_template("prompt", key, scenario=resolved_scenario)
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _invalidate_options_cache()
    return {"ok": True, "key": key, "kind": "prompt"}


@app.get(
    "/api/v1/platform/prompt-center/personas",
    response_model=ApiTemplateListResponse,
    tags=["platform-prompts"],
    summary="List persona templates",
)
async def api_prompt_center_list_personas(include_archived: bool = False, scenario: str | None = None):
    _ensure_platform_api_enabled()

    resolved_scenario = _normalize_scenario(scenario) if scenario else None

    try:
        records = prompt_persona_registry.list_templates(
            "persona",
            include_archived=include_archived,
            scenario=resolved_scenario,
        )
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = [_as_template_record(record) for record in records]
    return {
        "total": len(payload),
        "scenario": resolved_scenario,
        "include_archived": include_archived,
        "items": payload,
    }


@app.get(
    "/api/v1/platform/prompt-center/personas/{key}",
    response_model=ApiTemplateRecordResponse,
    tags=["platform-prompts"],
    summary="Get persona template",
)
async def api_prompt_center_get_persona(key: str, archived: bool = False, scenario: str | None = None):
    _ensure_platform_api_enabled()

    resolved_scenario = _normalize_scenario(scenario) if scenario else None

    try:
        record = prompt_persona_registry.get_template(
            "persona",
            key,
            archived=archived,
            scenario=resolved_scenario,
        )
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not record:
        raise HTTPException(status_code=404, detail="Persona template not found")
    return _as_template_record(record)


@app.post(
    "/api/v1/platform/prompt-center/personas",
    response_model=ApiTemplateRecordResponse,
    tags=["platform-prompts"],
    summary="Create persona template",
)
async def api_prompt_center_create_persona(request: PersonaTemplateWriteRequest):
    _ensure_platform_api_enabled()

    if not request.content.strip():
        raise HTTPException(status_code=400, detail="content is required")

    try:
        record = prompt_persona_registry.create_template(
            "persona",
            key=request.key,
            content=request.content,
            label=request.label,
            description=request.description,
            scenario=request.scenario,
        )
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _invalidate_options_cache()
    return _as_template_record(record)


@app.patch(
    "/api/v1/platform/prompt-center/personas/{key}",
    response_model=ApiTemplateRecordResponse,
    tags=["platform-prompts"],
    summary="Update persona template",
)
async def api_prompt_center_update_persona(key: str, request: PersonaTemplatePatchRequest):
    _ensure_platform_api_enabled()

    if request.label is None and request.description is None and request.content is None:
        raise HTTPException(status_code=400, detail="At least one field must be provided")

    try:
        record = prompt_persona_registry.update_template(
            "persona",
            key=key,
            content=request.content,
            label=request.label,
            description=request.description,
        )
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _invalidate_options_cache()
    return _as_template_record(record)


@app.post(
    "/api/v1/platform/prompt-center/personas/{key}/archive",
    response_model=ApiTemplateRecordResponse,
    tags=["platform-prompts"],
    summary="Archive persona template",
)
async def api_prompt_center_archive_persona(key: str, scenario: str | None = None):
    _ensure_platform_api_enabled()

    resolved_scenario = _normalize_scenario(scenario) if scenario else None

    try:
        record = prompt_persona_registry.archive_template("persona", key, scenario=resolved_scenario)
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _invalidate_options_cache()
    return _as_template_record(record)


@app.post(
    "/api/v1/platform/prompt-center/personas/{key}/restore",
    response_model=ApiTemplateRecordResponse,
    tags=["platform-prompts"],
    summary="Restore archived persona template",
)
async def api_prompt_center_restore_persona(key: str, scenario: str | None = None):
    _ensure_platform_api_enabled()

    resolved_scenario = _normalize_scenario(scenario) if scenario else None

    try:
        record = prompt_persona_registry.restore_template("persona", key, scenario=resolved_scenario)
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _invalidate_options_cache()
    return _as_template_record(record)


@app.delete(
    "/api/v1/platform/prompt-center/personas/{key}/purge",
    tags=["platform-prompts"],
    summary="Purge archived persona template",
)
async def api_prompt_center_purge_persona(key: str, scenario: str | None = None):
    _ensure_platform_api_enabled()

    resolved_scenario = _normalize_scenario(scenario) if scenario else None

    try:
        prompt_persona_registry.purge_template("persona", key, scenario=resolved_scenario)
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _invalidate_options_cache()
    return {"ok": True, "key": key, "kind": "persona"}


@app.get(
    "/api/v1/platform/tool-center/tools",
    response_model=ApiToolCenterListResponse,
    tags=["platform-tools"],
    summary="List Tool Center entries",
)
async def api_tool_center_list_tools(
    include_archived: bool = False,
    include_builtin: bool = True,
    include_source: bool = False,
    search: str = "",
):
    _ensure_platform_api_enabled()

    query = str(search or "").strip().lower()

    def _matches_query(*values: str) -> bool:
        if not query:
            return True
        combined = "\n".join(str(value or "") for value in values).lower()
        return query in combined

    managed_records = custom_tool_registry.list_tools(
        include_archived=include_archived,
        include_source=include_source,
    )
    remote_tools = agent_platform.list_available_tools(search=None, limit=500)
    remote_by_id = {
        str(tool.get("id", "") or ""): tool
        for tool in remote_tools
        if str(tool.get("id", "") or "").strip()
    }

    items: list[dict[str, Any]] = []
    managed_ids: set[str] = set()
    for managed in managed_records:
        tool_id = str(managed.get("tool_id", "") or "")
        if tool_id:
            managed_ids.add(tool_id)
        if not _matches_query(
            str(managed.get("slug", "") or ""),
            str(managed.get("name", "") or ""),
            str(managed.get("description", "") or ""),
        ):
            continue
        remote_tool = None if bool(managed.get("archived", False)) else remote_by_id.get(tool_id)
        items.append(
            _as_tool_center_item(
                managed_entry=managed,
                remote_tool=remote_tool,
                include_source=include_source,
            )
        )

    if include_builtin:
        for remote in remote_tools:
            tool_id = str(remote.get("id", "") or "")
            if not tool_id or tool_id in managed_ids:
                continue
            if not _matches_query(
                str(remote.get("name", "") or ""),
                str(remote.get("description", "") or ""),
                str(remote.get("tool_type", "") or ""),
            ):
                continue

            items.append(
                _as_tool_center_item(
                    managed_entry=None,
                    remote_tool=remote,
                    include_source=False,
                )
            )

    return {
        "total": len(items),
        "include_archived": include_archived,
        "include_builtin": include_builtin,
        "items": items,
    }


@app.get(
    "/api/v1/platform/tool-center/tools/{slug}",
    response_model=ApiToolCenterItemResponse,
    tags=["platform-tools"],
    summary="Get Tool Center managed custom tool",
)
async def api_tool_center_get_tool(slug: str, include_source: bool = True):
    _ensure_platform_api_enabled()

    try:
        managed = custom_tool_registry.get_tool(slug, include_source=include_source)
    except ToolRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not managed:
        raise HTTPException(status_code=404, detail="Managed custom tool not found")

    remote_tool: dict[str, Any] | None = None
    if not bool(managed.get("archived", False)):
        tool_id = str(managed.get("tool_id", "") or "")
        if tool_id:
            try:
                remote_tool = agent_platform.retrieve_tool(tool_id=tool_id)
            except Exception:
                remote_tool = None

    return _as_tool_center_item(
        managed_entry=managed,
        remote_tool=remote_tool,
        include_source=include_source,
    )


@app.post(
    "/api/v1/platform/tool-center/tools",
    response_model=ApiToolCenterItemResponse,
    tags=["platform-tools"],
    summary="Create managed custom tool",
)
async def api_tool_center_create_tool(request: ToolCenterCreateRequest):
    _ensure_platform_api_enabled()

    if not request.source_code.strip():
        raise HTTPException(status_code=400, detail="source_code is required")

    tags = _managed_tool_tags(request.tags)

    try:
        created_remote = agent_platform.create_tool(
            source_code=request.source_code,
            description=request.description,
            tags=tags,
            source_type=request.source_type,
            enable_parallel_execution=request.enable_parallel_execution,
            default_requires_approval=request.default_requires_approval,
            return_char_limit=request.return_char_limit,
            pip_requirements=request.pip_requirements,
            npm_requirements=request.npm_requirements,
        )

        managed = custom_tool_registry.create_tool(
            slug=request.slug,
            tool_id=str(created_remote.get("id", "") or ""),
            name=str(created_remote.get("name", "") or request.slug),
            description=str(created_remote.get("description", "") or request.description),
            source_code=request.source_code,
            tags=[str(tag) for tag in (created_remote.get("tags", tags) or []) if str(tag).strip()],
            source_type=str(created_remote.get("source_type", request.source_type) or request.source_type),
            tool_type=str(created_remote.get("tool_type", "custom") or "custom"),
        )
    except (ToolRegistryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _as_tool_center_item(managed_entry=managed, remote_tool=created_remote, include_source=True)


@app.patch(
    "/api/v1/platform/tool-center/tools/{slug}",
    response_model=ApiToolCenterItemResponse,
    tags=["platform-tools"],
    summary="Update managed custom tool",
)
async def api_tool_center_update_tool(slug: str, request: ToolCenterUpdateRequest):
    _ensure_platform_api_enabled()

    if (
        request.source_code is None
        and request.description is None
        and request.tags is None
        and request.source_type is None
        and request.enable_parallel_execution is None
        and request.default_requires_approval is None
        and request.return_char_limit is None
        and request.pip_requirements is None
        and request.npm_requirements is None
    ):
        raise HTTPException(status_code=400, detail="At least one updatable field is required")

    try:
        managed = custom_tool_registry.get_tool(slug, include_source=True)
        if not managed:
            raise HTTPException(status_code=404, detail="Managed custom tool not found")
        if bool(managed.get("archived", False)):
            raise HTTPException(status_code=400, detail="Archived tool must be restored before update")

        tool_id = str(managed.get("tool_id", "") or "")
        if not tool_id:
            raise HTTPException(status_code=400, detail="Managed custom tool is missing tool_id")

        merged_tags = request.tags
        if merged_tags is not None:
            merged_tags = _managed_tool_tags(merged_tags)

        updated_remote = agent_platform.update_tool(
            tool_id=tool_id,
            source_code=request.source_code,
            description=request.description,
            tags=merged_tags,
            source_type=request.source_type,
            enable_parallel_execution=request.enable_parallel_execution,
            default_requires_approval=request.default_requires_approval,
            return_char_limit=request.return_char_limit,
            pip_requirements=request.pip_requirements,
            npm_requirements=request.npm_requirements,
        )

        updated_managed = custom_tool_registry.update_tool(
            slug=slug,
            tool_id=str(updated_remote.get("id", "") or tool_id),
            name=str(updated_remote.get("name", "") or managed.get("name", "")),
            description=str(updated_remote.get("description", "") or request.description or managed.get("description", "")),
            source_code=request.source_code,
            tags=[str(tag) for tag in (updated_remote.get("tags", merged_tags or managed.get("tags", [])) or []) if str(tag).strip()],
            source_type=str(updated_remote.get("source_type", request.source_type or managed.get("source_type", "python")) or "python"),
            tool_type=str(updated_remote.get("tool_type", managed.get("tool_type", "custom")) or "custom"),
        )
    except HTTPException:
        raise
    except (ToolRegistryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _as_tool_center_item(managed_entry=updated_managed, remote_tool=updated_remote, include_source=True)


@app.post(
    "/api/v1/platform/tool-center/tools/{slug}/archive",
    response_model=ApiToolCenterItemResponse,
    tags=["platform-tools"],
    summary="Archive managed custom tool",
)
async def api_tool_center_archive_tool(slug: str):
    _ensure_platform_api_enabled()

    try:
        managed = custom_tool_registry.get_tool(slug, include_source=True)
        if not managed:
            raise HTTPException(status_code=404, detail="Managed custom tool not found")
        if bool(managed.get("archived", False)):
            raise HTTPException(status_code=400, detail="Tool is already archived")

        tool_id = str(managed.get("tool_id", "") or "")
        if not tool_id:
            raise HTTPException(status_code=400, detail="Managed custom tool is missing tool_id")

        agent_platform.delete_tool(tool_id=tool_id)
        archived = custom_tool_registry.archive_tool(slug)
    except HTTPException:
        raise
    except (ToolRegistryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _as_tool_center_item(managed_entry=archived, remote_tool=None, include_source=True)


@app.post(
    "/api/v1/platform/tool-center/tools/{slug}/restore",
    response_model=ApiToolCenterItemResponse,
    tags=["platform-tools"],
    summary="Restore archived managed custom tool",
)
async def api_tool_center_restore_tool(slug: str):
    _ensure_platform_api_enabled()

    try:
        managed = custom_tool_registry.get_tool(slug, include_source=True)
        if not managed:
            raise HTTPException(status_code=404, detail="Managed custom tool not found")
        if not bool(managed.get("archived", False)):
            raise HTTPException(status_code=400, detail="Tool is not archived")

        source_code = str(managed.get("source_code", "") or "")
        if not source_code.strip():
            raise HTTPException(status_code=400, detail="Archived source_code is missing")

        tags = _managed_tool_tags([str(tag) for tag in (managed.get("tags", []) or []) if str(tag).strip()])
        restored_remote = agent_platform.create_tool(
            source_code=source_code,
            description=str(managed.get("description", "") or ""),
            tags=tags,
            source_type=str(managed.get("source_type", "python") or "python"),
        )

        restored = custom_tool_registry.restore_tool(
            slug=slug,
            tool_id=str(restored_remote.get("id", "") or ""),
            name=str(restored_remote.get("name", "") or slug),
            description=str(restored_remote.get("description", "") or managed.get("description", "")),
            tags=[str(tag) for tag in (restored_remote.get("tags", tags) or []) if str(tag).strip()],
            source_type=str(restored_remote.get("source_type", managed.get("source_type", "python")) or "python"),
            tool_type=str(restored_remote.get("tool_type", managed.get("tool_type", "custom")) or "custom"),
        )
    except HTTPException:
        raise
    except (ToolRegistryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _as_tool_center_item(managed_entry=restored, remote_tool=restored_remote, include_source=True)


@app.delete(
    "/api/v1/platform/tool-center/tools/{slug}/purge",
    tags=["platform-tools"],
    summary="Purge archived managed custom tool",
)
async def api_tool_center_purge_tool(slug: str):
    _ensure_platform_api_enabled()

    try:
        custom_tool_registry.purge_tool(slug)
    except ToolRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"ok": True, "slug": slug, "kind": "custom_tool"}


@app.post(
    "/api/v1/platform/agents/{agent_id}/messages",
    response_model=ApiRuntimeMessageResponse,
    tags=["platform-runtime"],
    summary="Send runtime message with optional overrides",
)
async def api_platform_send_message(agent_id: str, request: PlatformRuntimeMessageRequest):
    _ensure_platform_api_enabled()
    _ensure_agent_not_archived(agent_id)

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
    "/api/v1/platform/agents/{agent_id}/system",
    response_model=ApiSystemUpdateResponse,
    tags=["platform-control"],
    summary="Update persisted system prompt",
)
async def api_platform_update_system(agent_id: str, request: PlatformSystemUpdateRequest):
    _ensure_platform_api_enabled()
    _ensure_agent_not_archived(agent_id)

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
            source="api/v1/platform/agents/{agent_id}/system",
        )
        return payload
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch(
    "/api/v1/platform/agents/{agent_id}/model",
    response_model=ApiModelUpdateResponse,
    tags=["platform-control"],
    summary="Update persisted agent model",
)
async def api_platform_update_model(agent_id: str, request: PlatformModelUpdateRequest):
    _ensure_platform_api_enabled()
    _ensure_agent_not_archived(agent_id)

    model_handle = request.model.strip()
    if not model_handle:
        raise HTTPException(status_code=400, detail="model is required")

    try:
        return agent_platform.update_agent_model(agent_id=agent_id, model_handle=model_handle)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch(
    "/api/v1/platform/agents/{agent_id}/core-memory/blocks/{block_label}",
    response_model=ApiMemoryBlockUpdateResponse,
    tags=["platform-control"],
    summary="Update core-memory block value",
)
async def api_platform_update_memory_block(
    agent_id: str,
    block_label: str,
    request: PlatformMemoryBlockUpdateRequest,
):
    _ensure_platform_api_enabled()
    _ensure_agent_not_archived(agent_id)

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
                source=f"api/v1/platform/agents/{{agent_id}}/core-memory/blocks/{label}",
            )
        return payload
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch(
    "/api/v1/platform/agents/{agent_id}/tools/attach/{tool_id}",
    response_model=ApiToolAttachDetachResponse,
    tags=["platform-tools"],
    summary="Attach tool to agent",
)
async def api_platform_attach_tool(agent_id: str, tool_id: str):
    _ensure_platform_api_enabled()
    _ensure_agent_not_archived(agent_id)

    resolved_tool_id = tool_id.strip()
    if not resolved_tool_id:
        raise HTTPException(status_code=400, detail="tool_id is required")

    try:
        return agent_platform.attach_tool(agent_id=agent_id, tool_id=resolved_tool_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch(
    "/api/v1/platform/agents/{agent_id}/tools/detach/{tool_id}",
    response_model=ApiToolAttachDetachResponse,
    tags=["platform-tools"],
    summary="Detach tool from agent",
)
async def api_platform_detach_tool(agent_id: str, tool_id: str):
    _ensure_platform_api_enabled()
    _ensure_agent_not_archived(agent_id)

    resolved_tool_id = tool_id.strip()
    if not resolved_tool_id:
        raise HTTPException(status_code=400, detail="tool_id is required")

    try:
        return agent_platform.detach_tool(agent_id=agent_id, tool_id=resolved_tool_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get(
    "/api/v1/platform/test-runs",
    response_model=ApiTestRunListResponse,
    tags=["platform-tests"],
    summary="List orchestrated test runs",
)
async def api_platform_list_test_runs():
    _ensure_platform_api_enabled()

    return {
        "items": test_orchestrator.list_runs(),
    }


@app.post(
    "/api/v1/platform/test-runs",
    response_model=ApiTestRunRecordResponse,
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
    "/api/v1/platform/test-runs/{run_id}",
    response_model=ApiTestRunRecordResponse,
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
    "/api/v1/platform/test-runs/{run_id}/cancel",
    response_model=ApiTestRunRecordResponse,
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
    "/api/v1/platform/test-runs/{run_id}/artifacts",
    response_model=ApiTestArtifactListResponse,
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
    "/api/v1/platform/test-runs/{run_id}/artifacts/{artifact_id}",
    response_model=ApiTestArtifactReadResponse,
    tags=["platform-tests"],
    summary="Read test run artifact content",
)
async def api_platform_read_test_run_artifact(run_id: str, artifact_id: str, max_lines: int = 400):
    _ensure_platform_api_enabled()

    payload = test_orchestrator.read_artifact(run_id, artifact_id, max_lines=max_lines)
    if payload is None:
        raise HTTPException(status_code=404, detail="run_id or artifact_id not found")
    return payload


@app.post(
    "/api/v1/commenting/generate",
    response_model=ApiCommentingGenerateResponse,
    tags=["commenting"],
    summary="Generate a stateless comment for news/comment threads",
)
async def api_commenting_generate(request: CommentingGenerateRequest):
    _ensure_platform_api_enabled()

    resolved_scenario = _normalize_scenario(request.scenario, default="comment")
    if resolved_scenario != "comment":
        raise HTTPException(status_code=400, detail="scenario must be 'comment' for this endpoint")

    text = request.input.strip()
    if not text:
        raise HTTPException(status_code=400, detail="input is required")

    if not request.prompt_key.startswith("comment_"):
        raise HTTPException(status_code=400, detail=f"Prompt key '{request.prompt_key}' is not valid for scenario 'comment'")
    if not request.persona_key.startswith("comment_"):
        raise HTTPException(status_code=400, detail=f"Persona key '{request.persona_key}' is not valid for scenario 'comment'")

    prompt_map = _prompt_content_map("comment")
    persona_map = _persona_content_map("comment")
    if request.prompt_key not in prompt_map:
        raise HTTPException(status_code=400, detail=f"Invalid prompt key: {request.prompt_key}")
    if request.persona_key not in persona_map:
        raise HTTPException(status_code=400, detail=f"Invalid persona key: {request.persona_key}")

    model_options, _ = _runtime_options()
    allowed_models = {str(option.get("key", "") or "") for option in model_options if str(option.get("key", "") or "").strip()}
    model_handle = (request.model or "").strip() or os.getenv("AGENT_PLATFORM_COMMENTING_DEFAULT_MODEL", "").strip()
    if not model_handle and model_options:
        model_handle = str(model_options[0].get("key", "") or "")
    if not model_handle:
        raise HTTPException(status_code=400, detail="No model available for commenting generation")

    if allowed_models and model_handle not in allowed_models:
        normalized_requested_model = commenting_service._resolve_provider_model(model_handle)
        matched_model_handle = next(
            (
                candidate
                for candidate in allowed_models
                if commenting_service._resolve_provider_model(candidate) == normalized_requested_model
            ),
            "",
        )
        if matched_model_handle:
            model_handle = matched_model_handle
        else:
            raise HTTPException(status_code=400, detail=f"Invalid model: {model_handle}")

    persona_text = str(persona_map[request.persona_key] or "")
    try:
        generation_result = commenting_service.generate_comment(
            model=model_handle,
            system_prompt=prompt_map[request.prompt_key],
            persona_prompt=persona_text,
            news_input=text,
            max_tokens=request.max_tokens,
            timeout_seconds=request.timeout_seconds,
            task_shape=request.task_shape,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    content = str(generation_result.get("content", "") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Comment provider returned empty content")
    runtime_defaults = _commenting_runtime_defaults()
    raw_reply = generation_result.get("raw_reply", {})
    if not isinstance(raw_reply, dict):
        raw_reply = {}
    usage = generation_result.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}
    raw_request = generation_result.get("raw_request", {})
    if not isinstance(raw_request, dict):
        raw_request = {}
    selected_attempt = str(generation_result.get("selected_attempt", "") or "").strip() or "unknown"

    return {
        "scenario": "comment",
        "prompt_key": request.prompt_key,
        "persona_key": request.persona_key,
        "model": model_handle,
        "content": content,
        "provider": commenting_service.provider_name,
        "max_tokens": int(generation_result.get("max_tokens", runtime_defaults.max_tokens)),
        "timeout_seconds": float(generation_result.get("timeout_seconds", runtime_defaults.timeout_seconds)),
        "task_shape": str(generation_result.get("task_shape", runtime_defaults.task_shape)),
        "content_source": str(generation_result.get("content_source", "") or "") or None,
        "selected_attempt": selected_attempt,
        "finish_reason": str(generation_result.get("finish_reason", "") or "") or None,
        "usage": usage,
        "received_at": str(generation_result.get("received_at", "") or "") or None,
        "raw_request": raw_request,
        "raw_reply": raw_reply,
    }

@app.post("/api/v1/chat", response_model=ApiChatResponse)
async def api_chat(request: ChatRequest):
    _ensure_platform_api_enabled()
    _ensure_agent_not_archived(request.agent_id)

    is_datetime_turn = _is_datetime_query(request.message)

    try:
        return agent_platform.send_chat_message(
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
