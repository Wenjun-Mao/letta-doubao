from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .common import CommentingTaskShape, ScenarioType


class ApiCommentingRuntimeDefaultsResponse(BaseModel):
    max_tokens: int
    timeout_seconds: float
    task_shape: CommentingTaskShape


class CommentingGenerateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "scenario": "comment",
                    "input": "Summarize the reader reaction and write one concise editor-style reply.",
                    "prompt_key": "comment_v20260418",
                    "persona_key": "comment_linxiaotang",
                    "model_key": "local_llama_server::gemma4",
                    "max_tokens": 512,
                    "timeout_seconds": 120,
                    "retry_count": 1,
                    "task_shape": "classic",
                }
            ]
        }
    )

    scenario: ScenarioType = Field(default="comment", description="Must be `comment` for this endpoint.")
    input: str = Field(..., description="News article, comment thread, or source text to comment on.")
    prompt_key: str = Field(default="comment_v20260418", description="Comment Lab prompt key from `/api/v1/options?scenario=comment`.")
    persona_key: str = Field(default="comment_linxiaotang", description="Comment Lab persona key from `/api/v1/options?scenario=comment`.")
    model_key: str | None = Field(
        default=None,
        description="Router-scoped model key from `/api/v1/options?scenario=comment`, for example `local_llama_server::gemma4`.",
        examples=["local_llama_server::gemma4"],
    )
    model: str | None = Field(
        default=None,
        description="Legacy selector kept for backward compatibility. Prefer `model_key`.",
        deprecated=True,
    )
    max_tokens: int | None = Field(default=None, ge=0, description="Optional response token budget. Defaults to Comment Lab runtime settings.")
    timeout_seconds: float | None = Field(default=None, gt=0, description="Optional provider timeout in seconds. Use a realistic local-model value such as 120.")
    retry_count: int | None = Field(default=None, ge=0, le=5, description="Optional provider retry count for transient failures.")
    task_shape: CommentingTaskShape | None = Field(default=None, description="Prompt-packing strategy. Defaults to the Comment Lab runtime setting.")


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
