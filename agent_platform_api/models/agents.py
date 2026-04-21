from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .commenting import ApiCommentingRuntimeDefaultsResponse
from .common import ScenarioType


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


class ApiChatResponse(BaseModel):
    total_steps: int = 0
    sequence: list[dict[str, Any]] = Field(default_factory=list)
    memory_diff: dict[str, Any] = Field(default_factory=dict)
