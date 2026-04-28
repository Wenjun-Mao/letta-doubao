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
from agent_platform_api.openapi_metadata import TAG_PROMPT_CENTER
from agent_platform_api.runtime import ensure_platform_api_enabled, invalidate_options_cache, prompt_persona_registry
from agent_platform_api.registries.prompt_persona_store import RegistryError

router = APIRouter()


def _is_label_persona_selector(*, scenario: str | None, key: str | None = None) -> bool:
    resolved_scenario = str(scenario or "").strip().lower()
    resolved_key = str(key or "").strip().lower()
    return resolved_scenario == "label" or resolved_key.startswith("label_")


@router.get(
    "/api/v1/platform/prompt-center/prompts",
    response_model=ApiTemplateListResponse,
    tags=[TAG_PROMPT_CENTER],
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
    tags=[TAG_PROMPT_CENTER],
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
    tags=[TAG_PROMPT_CENTER],
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
    tags=[TAG_PROMPT_CENTER],
    summary="Update system prompt template",
)
async def api_prompt_center_update_prompt(
    key: str,
    request: PromptTemplatePatchRequest,
    scenario: str | None = None,
):
    ensure_platform_api_enabled()
    resolved_scenario = normalize_scenario(scenario) if scenario else None
    if request.label is None and request.description is None and request.content is None:
        raise HTTPException(status_code=400, detail="At least one field must be provided")

    try:
        record = prompt_persona_registry.update_template(
            "prompt",
            key=key,
            content=request.content,
            label=request.label,
            description=request.description,
            scenario=resolved_scenario,
        )
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    invalidate_options_cache()
    return as_template_record(record)


@router.post(
    "/api/v1/platform/prompt-center/prompts/{key}/archive",
    response_model=ApiTemplateRecordResponse,
    tags=[TAG_PROMPT_CENTER],
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
    tags=[TAG_PROMPT_CENTER],
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
    tags=[TAG_PROMPT_CENTER],
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
    tags=[TAG_PROMPT_CENTER],
    summary="List persona templates",
)
async def api_prompt_center_list_personas(include_archived: bool = False, scenario: str | None = None):
    ensure_platform_api_enabled()
    resolved_scenario = normalize_scenario(scenario) if scenario else None
    if _is_label_persona_selector(scenario=resolved_scenario):
        return {
            "total": 0,
            "scenario": resolved_scenario,
            "include_archived": include_archived,
            "items": [],
        }

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
    tags=[TAG_PROMPT_CENTER],
    summary="Get persona template",
)
async def api_prompt_center_get_persona(key: str, archived: bool = False, scenario: str | None = None):
    ensure_platform_api_enabled()
    resolved_scenario = normalize_scenario(scenario) if scenario else None
    if _is_label_persona_selector(scenario=resolved_scenario, key=key):
        raise HTTPException(status_code=404, detail="Label scenario does not expose persona templates")

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
    tags=[TAG_PROMPT_CENTER],
    summary="Create persona template",
)
async def api_prompt_center_create_persona(request: PersonaTemplateWriteRequest):
    ensure_platform_api_enabled()
    if _is_label_persona_selector(scenario=request.scenario, key=request.key):
        raise HTTPException(status_code=400, detail="Label scenario does not support persona templates")
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
    tags=[TAG_PROMPT_CENTER],
    summary="Update persona template",
)
async def api_prompt_center_update_persona(
    key: str,
    request: PersonaTemplatePatchRequest,
    scenario: str | None = None,
):
    ensure_platform_api_enabled()
    resolved_scenario = normalize_scenario(scenario) if scenario else None
    if _is_label_persona_selector(scenario=resolved_scenario, key=key):
        raise HTTPException(status_code=400, detail="Label scenario does not support persona templates")
    if request.label is None and request.description is None and request.content is None:
        raise HTTPException(status_code=400, detail="At least one field must be provided")

    try:
        record = prompt_persona_registry.update_template(
            "persona",
            key=key,
            content=request.content,
            label=request.label,
            description=request.description,
            scenario=resolved_scenario,
        )
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    invalidate_options_cache()
    return as_template_record(record)


@router.post(
    "/api/v1/platform/prompt-center/personas/{key}/archive",
    response_model=ApiTemplateRecordResponse,
    tags=[TAG_PROMPT_CENTER],
    summary="Archive persona template",
)
async def api_prompt_center_archive_persona(key: str, scenario: str | None = None):
    ensure_platform_api_enabled()
    resolved_scenario = normalize_scenario(scenario) if scenario else None
    if _is_label_persona_selector(scenario=resolved_scenario, key=key):
        raise HTTPException(status_code=400, detail="Label scenario does not support persona templates")

    try:
        record = prompt_persona_registry.archive_template("persona", key, scenario=resolved_scenario)
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    invalidate_options_cache()
    return as_template_record(record)


@router.post(
    "/api/v1/platform/prompt-center/personas/{key}/restore",
    response_model=ApiTemplateRecordResponse,
    tags=[TAG_PROMPT_CENTER],
    summary="Restore archived persona template",
)
async def api_prompt_center_restore_persona(key: str, scenario: str | None = None):
    ensure_platform_api_enabled()
    resolved_scenario = normalize_scenario(scenario) if scenario else None
    if _is_label_persona_selector(scenario=resolved_scenario, key=key):
        raise HTTPException(status_code=400, detail="Label scenario does not support persona templates")

    try:
        record = prompt_persona_registry.restore_template("persona", key, scenario=resolved_scenario)
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    invalidate_options_cache()
    return as_template_record(record)


@router.delete(
    "/api/v1/platform/prompt-center/personas/{key}/purge",
    tags=[TAG_PROMPT_CENTER],
    summary="Purge archived persona template",
)
async def api_prompt_center_purge_persona(key: str, scenario: str | None = None):
    ensure_platform_api_enabled()
    resolved_scenario = normalize_scenario(scenario) if scenario else None
    if _is_label_persona_selector(scenario=resolved_scenario, key=key):
        raise HTTPException(status_code=400, detail="Label scenario does not support persona templates")

    try:
        prompt_persona_registry.purge_template("persona", key, scenario=resolved_scenario)
    except RegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    invalidate_options_cache()
    return {"ok": True, "key": key, "kind": "persona"}

