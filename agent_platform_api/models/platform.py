from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


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
