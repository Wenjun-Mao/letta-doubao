from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import LabelingOutputMode


class PlatformRuntimeMessageRequest(BaseModel):
    input: str
    override_model: str | None = None
    override_system: str | None = None
    timeout_seconds: float | None = Field(default=None, gt=0, le=600)
    retry_count: int | None = Field(default=None, ge=0, le=5)


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
    timeout_seconds: float | None = Field(default=None, gt=0, le=600)
    retry_count: int | None = Field(default=None, ge=0, le=5)


class PlatformTestRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_type: Literal[
        "platform_api_e2e_check",
        "ade_mvp_smoke_e2e_check",
    ]


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


class ApiPlatformModelCatalogSourceModelResponse(BaseModel):
    provider_model_id: str
    model_type: str


class ApiPlatformModelCatalogSourceResponse(BaseModel):
    id: str
    label: str
    kind: str
    adapter: str = "generic_openai"
    base_url: str
    enabled_for: list[str]
    letta_handle_prefix: str
    status: str
    detail: str
    allowlist_applied: bool | None = None
    allowlist_checked_at: str | None = None
    raw_model_count: int = 0
    filtered_model_count: int = 0
    models: list[ApiPlatformModelCatalogSourceModelResponse] = Field(default_factory=list)


class ApiPlatformModelCatalogEntryResponse(BaseModel):
    model_key: str
    source_id: str
    source_label: str
    source_kind: str
    source_adapter: str = "generic_openai"
    provider_model_id: str
    model_type: str
    letta_handle: str | None = None
    agent_studio_available: bool
    comment_lab_available: bool
    label_lab_available: bool
    structured_output_mode: LabelingOutputMode | None = None
    sampling_defaults: dict[str, Any] = Field(default_factory=dict)
    scenario_sampling_defaults: dict[str, dict[str, Any]] = Field(default_factory=dict)
    supports_top_k: bool = False
    supports_thinking: bool = False
    thinking_default_enabled: bool = False
    profile_applied: bool = False
    profile_source: str = ""
    agent_studio_candidate: bool = False
    agent_studio_compatible: bool = True


class ApiPlatformModelCatalogResponse(BaseModel):
    generated_at: float
    sources: list[ApiPlatformModelCatalogSourceResponse] = Field(default_factory=list)
    items: list[ApiPlatformModelCatalogEntryResponse] = Field(default_factory=list)
