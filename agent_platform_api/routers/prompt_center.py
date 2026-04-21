from __future__ import annotations

from fastapi import APIRouter, HTTPException

from agent_platform_api.helpers import normalize_scenario
from agent_platform_api.mappers import as_template_record
from agent_platform_api.models.templates import (
    ApiTemplateListResponse,
    ApiTemplateRecordResponse,
    PersonaTemplatePatchRequest,
    PersonaTemplateWriteRequest,
    PromptTemplatePatchRequest,
    PromptTemplateWriteRequest,
)
from agent_platform_api.runtime import ensure_platform_api_enabled, invalidate_options_cache, prompt_persona_registry
from utils.prompt_persona_registry import RegistryError

router = APIRouter()


@router.get(
    "/api/v1/platform/prompt-center/prompts",
    response_model=ApiTemplateListResponse,
    tags=["platform-prompts"],
    summary="List system prompt templates",
)
async def api_prompt_center_list_prompts(include_archived: bool = False, scenario: str | None = None):
    ensure_platform_api_enabled()
    resolved_scenario = normalize_scenario(scenario) if scenario else None

    try:
        records = prompt_persona_registry.list_templates(
            "prompt",
            include_archived=include_archived,
            scenario=resolved_scenario,
        )
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = [as_template_record(record) for record in records]
    return {
        "total": len(payload),
        "scenario": resolved_scenario,
        "include_archived": include_archived,
        "items": payload,
    }


@router.get(
    "/api/v1/platform/prompt-center/prompts/{key}",
    response_model=ApiTemplateRecordResponse,
    tags=["platform-prompts"],
    summary="Get system prompt template",
)
async def api_prompt_center_get_prompt(key: str, archived: bool = False, scenario: str | None = None):
    ensure_platform_api_enabled()
    resolved_scenario = normalize_scenario(scenario) if scenario else None

    try:
        record = prompt_persona_registry.get_template(
            "prompt",
            key,
            archived=archived,
            scenario=resolved_scenario,
        )
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not record:
        raise HTTPException(status_code=404, detail="Prompt template not found")
    return as_template_record(record)


@router.post(
    "/api/v1/platform/prompt-center/prompts",
    response_model=ApiTemplateRecordResponse,
    tags=["platform-prompts"],
    summary="Create system prompt template",
)
async def api_prompt_center_create_prompt(request: PromptTemplateWriteRequest):
    ensure_platform_api_enabled()
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="content is required")

    try:
        record = prompt_persona_registry.create_template(
            "prompt",
            key=request.key,
            content=request.content,
            label=request.label,
            description=request.description,
            scenario=request.scenario,
        )
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    invalidate_options_cache()
    return as_template_record(record)


@router.patch(
    "/api/v1/platform/prompt-center/prompts/{key}",
    response_model=ApiTemplateRecordResponse,
    tags=["platform-prompts"],
    summary="Update system prompt template",
)
async def api_prompt_center_update_prompt(key: str, request: PromptTemplatePatchRequest):
    ensure_platform_api_enabled()
    if request.label is None and request.description is None and request.content is None:
        raise HTTPException(status_code=400, detail="At least one field must be provided")

    try:
        record = prompt_persona_registry.update_template(
            "prompt",
            key=key,
            content=request.content,
            label=request.label,
            description=request.description,
        )
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    invalidate_options_cache()
    return as_template_record(record)


@router.post(
    "/api/v1/platform/prompt-center/prompts/{key}/archive",
    response_model=ApiTemplateRecordResponse,
    tags=["platform-prompts"],
    summary="Archive system prompt template",
)
async def api_prompt_center_archive_prompt(key: str, scenario: str | None = None):
    ensure_platform_api_enabled()
    resolved_scenario = normalize_scenario(scenario) if scenario else None

    try:
        record = prompt_persona_registry.archive_template("prompt", key, scenario=resolved_scenario)
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    invalidate_options_cache()
    return as_template_record(record)


@router.post(
    "/api/v1/platform/prompt-center/prompts/{key}/restore",
    response_model=ApiTemplateRecordResponse,
    tags=["platform-prompts"],
    summary="Restore archived system prompt template",
)
async def api_prompt_center_restore_prompt(key: str, scenario: str | None = None):
    ensure_platform_api_enabled()
    resolved_scenario = normalize_scenario(scenario) if scenario else None

    try:
        record = prompt_persona_registry.restore_template("prompt", key, scenario=resolved_scenario)
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    invalidate_options_cache()
    return as_template_record(record)


@router.delete(
    "/api/v1/platform/prompt-center/prompts/{key}/purge",
    tags=["platform-prompts"],
    summary="Purge archived system prompt template",
)
async def api_prompt_center_purge_prompt(key: str, scenario: str | None = None):
    ensure_platform_api_enabled()
    resolved_scenario = normalize_scenario(scenario) if scenario else None

    try:
        prompt_persona_registry.purge_template("prompt", key, scenario=resolved_scenario)
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    invalidate_options_cache()
    return {"ok": True, "key": key, "kind": "prompt"}


@router.get(
    "/api/v1/platform/prompt-center/personas",
    response_model=ApiTemplateListResponse,
    tags=["platform-prompts"],
    summary="List persona templates",
)
async def api_prompt_center_list_personas(include_archived: bool = False, scenario: str | None = None):
    ensure_platform_api_enabled()
    resolved_scenario = normalize_scenario(scenario) if scenario else None

    try:
        records = prompt_persona_registry.list_templates(
            "persona",
            include_archived=include_archived,
            scenario=resolved_scenario,
        )
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = [as_template_record(record) for record in records]
    return {
        "total": len(payload),
        "scenario": resolved_scenario,
        "include_archived": include_archived,
        "items": payload,
    }


@router.get(
    "/api/v1/platform/prompt-center/personas/{key}",
    response_model=ApiTemplateRecordResponse,
    tags=["platform-prompts"],
    summary="Get persona template",
)
async def api_prompt_center_get_persona(key: str, archived: bool = False, scenario: str | None = None):
    ensure_platform_api_enabled()
    resolved_scenario = normalize_scenario(scenario) if scenario else None

    try:
        record = prompt_persona_registry.get_template(
            "persona",
            key,
            archived=archived,
            scenario=resolved_scenario,
        )
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not record:
        raise HTTPException(status_code=404, detail="Persona template not found")
    return as_template_record(record)


@router.post(
    "/api/v1/platform/prompt-center/personas",
    response_model=ApiTemplateRecordResponse,
    tags=["platform-prompts"],
    summary="Create persona template",
)
async def api_prompt_center_create_persona(request: PersonaTemplateWriteRequest):
    ensure_platform_api_enabled()
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="content is required")

    try:
        record = prompt_persona_registry.create_template(
            "persona",
            key=request.key,
            content=request.content,
            label=request.label,
            description=request.description,
            scenario=request.scenario,
        )
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    invalidate_options_cache()
    return as_template_record(record)


@router.patch(
    "/api/v1/platform/prompt-center/personas/{key}",
    response_model=ApiTemplateRecordResponse,
    tags=["platform-prompts"],
    summary="Update persona template",
)
async def api_prompt_center_update_persona(key: str, request: PersonaTemplatePatchRequest):
    ensure_platform_api_enabled()
    if request.label is None and request.description is None and request.content is None:
        raise HTTPException(status_code=400, detail="At least one field must be provided")

    try:
        record = prompt_persona_registry.update_template(
            "persona",
            key=key,
            content=request.content,
            label=request.label,
            description=request.description,
        )
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    invalidate_options_cache()
    return as_template_record(record)


@router.post(
    "/api/v1/platform/prompt-center/personas/{key}/archive",
    response_model=ApiTemplateRecordResponse,
    tags=["platform-prompts"],
    summary="Archive persona template",
)
async def api_prompt_center_archive_persona(key: str, scenario: str | None = None):
    ensure_platform_api_enabled()
    resolved_scenario = normalize_scenario(scenario) if scenario else None

    try:
        record = prompt_persona_registry.archive_template("persona", key, scenario=resolved_scenario)
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    invalidate_options_cache()
    return as_template_record(record)


@router.post(
    "/api/v1/platform/prompt-center/personas/{key}/restore",
    response_model=ApiTemplateRecordResponse,
    tags=["platform-prompts"],
    summary="Restore archived persona template",
)
async def api_prompt_center_restore_persona(key: str, scenario: str | None = None):
    ensure_platform_api_enabled()
    resolved_scenario = normalize_scenario(scenario) if scenario else None

    try:
        record = prompt_persona_registry.restore_template("persona", key, scenario=resolved_scenario)
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    invalidate_options_cache()
    return as_template_record(record)


@router.delete(
    "/api/v1/platform/prompt-center/personas/{key}/purge",
    tags=["platform-prompts"],
    summary="Purge archived persona template",
)
async def api_prompt_center_purge_persona(key: str, scenario: str | None = None):
    ensure_platform_api_enabled()
    resolved_scenario = normalize_scenario(scenario) if scenario else None

    try:
        prompt_persona_registry.purge_template("persona", key, scenario=resolved_scenario)
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    invalidate_options_cache()
    return {"ok": True, "key": key, "kind": "persona"}

