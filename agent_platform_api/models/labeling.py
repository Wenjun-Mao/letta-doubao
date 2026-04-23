from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .common import LabelingOutputMode, ScenarioType


class ApiLabelSpanResponse(BaseModel):
    label: str
    text: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class ApiLabelingResultResponse(BaseModel):
    spans: list[ApiLabelSpanResponse] = Field(default_factory=list)


class ApiLabelingRuntimeDefaultsResponse(BaseModel):
    max_tokens: int
    timeout_seconds: float
    repair_retry_count: int


class LabelingGenerateRequest(BaseModel):
    scenario: ScenarioType = "label"
    input: str
    prompt_key: str = "label_generic_spans_v1"
    schema_key: str = "label_span_annotations_v1"
    model_key: str
    max_tokens: int | None = Field(default=None, ge=0)
    timeout_seconds: float | None = Field(default=None, gt=0)
    repair_retry_count: int | None = Field(default=None, ge=0, le=3)


class ApiLabelingGenerateResponse(BaseModel):
    scenario: ScenarioType
    model_key: str
    source_id: str
    source_label: str
    provider_model_id: str
    prompt_key: str
    schema_key: str
    output_mode: LabelingOutputMode
    selected_attempt: Literal["primary", "repair"]
    result: ApiLabelingResultResponse
    finish_reason: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    received_at: str | None = None
    raw_request: dict[str, Any] = Field(default_factory=dict)
    raw_reply: dict[str, Any] = Field(default_factory=dict)
    validation_errors: list[str] = Field(default_factory=list)
