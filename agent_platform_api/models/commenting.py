from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .common import CommentingTaskShape, ScenarioType


class ApiCommentingRuntimeDefaultsResponse(BaseModel):
    max_tokens: int
    timeout_seconds: float
    task_shape: CommentingTaskShape


class CommentingGenerateRequest(BaseModel):
    scenario: ScenarioType = "comment"
    input: str
    prompt_key: str = "comment_v20260418"
    persona_key: str = "comment_linxiaotang"
    model_key: str | None = None
    model: str | None = None
    max_tokens: int | None = Field(default=None, ge=0)
    timeout_seconds: float | None = Field(default=None, gt=0)
    retry_count: int | None = Field(default=None, ge=0, le=5)
    task_shape: CommentingTaskShape | None = None


class ApiCommentingGenerateResponse(BaseModel):
    scenario: ScenarioType
    model_key: str
    source_id: str
    source_label: str
    provider_model_id: str
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
