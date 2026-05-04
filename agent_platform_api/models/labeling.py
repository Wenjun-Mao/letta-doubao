from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import LabelingOutputMode, ScenarioType


class ApiLabelingRuntimeDefaultsResponse(BaseModel):
    max_tokens: int
    timeout_seconds: float
    repair_retry_count: int
    temperature: float
    top_p: float
    top_k: int | None = None


class LabelingGenerateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "scenario": "label",
                    "input": "Messi scored for Inter Miami against Orlando City.",
                    "prompt_key": "label_football_entities_v1",
                    "schema_key": "label_football_entity_groups_v1",
                    "model_key": "local_llama_server::gemma4",
                    "max_tokens": 1024,
                    "timeout_seconds": 120,
                    "repair_retry_count": 1,
                    "temperature": 0.0,
                    "top_p": 1.0,
                    "top_k": 64,
                }
            ]
        }
    )

    scenario: ScenarioType = Field(default="label", description="Must be `label` for this endpoint.")
    input: str = Field(..., description="Article or text to extract grouped entity lists from.")
    prompt_key: str = Field(default="label_generic_entities_v1", description="Label Lab prompt key from `/api/v1/options?scenario=label`.")
    schema_key: str = Field(default="label_entity_groups_v1", description="Label Schema Center key from `/api/v1/options?scenario=label`.")
    model_key: str = Field(
        ...,
        description="Router-scoped model key from `/api/v1/options?scenario=label`, for example `local_llama_server::gemma4`.",
        examples=["local_llama_server::gemma4"],
    )
    max_tokens: int | None = Field(default=None, ge=0, description="Optional response token budget. Defaults to Label Lab runtime settings.")
    timeout_seconds: float | None = Field(default=None, gt=0, description="Optional provider timeout in seconds. Use a realistic local-model value such as 120.")
    repair_retry_count: int | None = Field(default=None, ge=0, le=3, description="Number of structured-output repair attempts after validation failure.")
    temperature: float | None = Field(default=None, ge=0, le=2, description="Sampling temperature. Defaults to Label Lab runtime settings.")
    top_p: float | None = Field(default=None, gt=0, le=1, description="Nucleus sampling top_p. Defaults to Label Lab runtime settings.")
    top_k: int | None = Field(default=None, gt=0, description="Optional top_k sampling value. Defaults to model profile or Label Lab runtime settings.")


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
    result: dict[str, list[str]] = Field(default_factory=dict)
    finish_reason: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    received_at: str | None = None
    raw_request: dict[str, Any] = Field(default_factory=dict)
    raw_reply: dict[str, Any] = Field(default_factory=dict)
    validation_errors: list[str] = Field(default_factory=list)
    temperature: float
    top_p: float
    top_k: int | None = None
