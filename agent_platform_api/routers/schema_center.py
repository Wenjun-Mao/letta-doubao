from __future__ import annotations

from fastapi import APIRouter, HTTPException

from agent_platform_api.mappers import as_label_schema_record
from agent_platform_api.models.schemas import (
    ApiLabelSchemaListResponse,
    ApiLabelSchemaRecordResponse,
    LabelSchemaPatchRequest,
    LabelSchemaWriteRequest,
)
from agent_platform_api.openapi_metadata import TAG_SCHEMA_CENTER
from agent_platform_api.runtime import ensure_platform_api_enabled, invalidate_options_cache, label_schema_registry
from agent_platform_api.registries.label_schema import LabelSchemaRegistryError

router = APIRouter()


@router.get(
    "/api/v1/platform/schema-center/label-schemas",
    response_model=ApiLabelSchemaListResponse,
    tags=[TAG_SCHEMA_CENTER],
    summary="List Label Lab JSON schemas",
)
async def api_schema_center_list_label_schemas(include_archived: bool = False):
    ensure_platform_api_enabled()
    records = label_schema_registry.list_schemas(include_archived=include_archived)
    items = [as_label_schema_record(record) for record in records]
    return {
        "total": len(items),
        "include_archived": include_archived,
        "items": items,
    }


@router.get(
    "/api/v1/platform/schema-center/label-schemas/{key}",
    response_model=ApiLabelSchemaRecordResponse,
    tags=[TAG_SCHEMA_CENTER],
    summary="Get Label Lab JSON schema",
)
async def api_schema_center_get_label_schema(key: str, archived: bool = False):
    ensure_platform_api_enabled()
    try:
        record = label_schema_registry.get_schema(key, archived=archived)
    except LabelSchemaRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Label schema not found")
    return as_label_schema_record(record)


@router.post(
    "/api/v1/platform/schema-center/label-schemas",
    response_model=ApiLabelSchemaRecordResponse,
    tags=[TAG_SCHEMA_CENTER],
    summary="Create Label Lab JSON schema",
)
async def api_schema_center_create_label_schema(request: LabelSchemaWriteRequest):
    ensure_platform_api_enabled()
    try:
        record = label_schema_registry.create_schema(
            key=request.key,
            schema=request.schema_,
            label=request.label,
            description=request.description,
        )
    except LabelSchemaRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    invalidate_options_cache()
    return as_label_schema_record(record)


@router.patch(
    "/api/v1/platform/schema-center/label-schemas/{key}",
    response_model=ApiLabelSchemaRecordResponse,
    tags=[TAG_SCHEMA_CENTER],
    summary="Update Label Lab JSON schema",
)
async def api_schema_center_update_label_schema(key: str, request: LabelSchemaPatchRequest):
    ensure_platform_api_enabled()
    if request.label is None and request.description is None and request.schema_ is None:
        raise HTTPException(status_code=400, detail="At least one field must be provided")
    try:
        record = label_schema_registry.update_schema(
            key=key,
            schema=request.schema_,
            label=request.label,
            description=request.description,
        )
    except LabelSchemaRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    invalidate_options_cache()
    return as_label_schema_record(record)


@router.post(
    "/api/v1/platform/schema-center/label-schemas/{key}/archive",
    response_model=ApiLabelSchemaRecordResponse,
    tags=[TAG_SCHEMA_CENTER],
    summary="Archive Label Lab JSON schema",
)
async def api_schema_center_archive_label_schema(key: str):
    ensure_platform_api_enabled()
    try:
        record = label_schema_registry.archive_schema(key)
    except LabelSchemaRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    invalidate_options_cache()
    return as_label_schema_record(record)


@router.post(
    "/api/v1/platform/schema-center/label-schemas/{key}/restore",
    response_model=ApiLabelSchemaRecordResponse,
    tags=[TAG_SCHEMA_CENTER],
    summary="Restore archived Label Lab JSON schema",
)
async def api_schema_center_restore_label_schema(key: str):
    ensure_platform_api_enabled()
    try:
        record = label_schema_registry.restore_schema(key)
    except LabelSchemaRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    invalidate_options_cache()
    return as_label_schema_record(record)


@router.delete(
    "/api/v1/platform/schema-center/label-schemas/{key}/purge",
    tags=[TAG_SCHEMA_CENTER],
    summary="Purge archived Label Lab JSON schema",
)
async def api_schema_center_purge_label_schema(key: str):
    ensure_platform_api_enabled()
    try:
        label_schema_registry.purge_schema(key)
    except LabelSchemaRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    invalidate_options_cache()
    return {"ok": True, "key": key, "kind": "label_schema"}
