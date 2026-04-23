from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LabelSchemaWriteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    key: str
    label: str = ""
    description: str = ""
    schema_: dict[str, Any] = Field(alias="schema")


class LabelSchemaPatchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    label: str | None = None
    description: str | None = None
    schema_: dict[str, Any] | None = Field(default=None, alias="schema")


class ApiLabelSchemaRecordResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    key: str
    label: str
    description: str
    schema_: dict[str, Any] = Field(alias="schema")
    preview: str
    archived: bool
    source_path: str
    updated_at: str


class ApiLabelSchemaListResponse(BaseModel):
    total: int
    include_archived: bool
    items: list[ApiLabelSchemaRecordResponse] = Field(default_factory=list)
