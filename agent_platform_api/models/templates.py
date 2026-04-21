from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .common import ScenarioType


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
