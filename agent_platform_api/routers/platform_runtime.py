from __future__ import annotations

from fastapi import APIRouter, HTTPException

from agent_platform_api.helpers import append_prompt_persona_revision
from agent_platform_api.models.platform import (
    ApiMemoryBlockUpdateResponse,
    ApiModelUpdateResponse,
    ApiRuntimeMessageResponse,
    ApiSystemUpdateResponse,
    ApiTestArtifactListResponse,
    ApiTestArtifactReadResponse,
    ApiTestRunListResponse,
    ApiTestRunRecordResponse,
    ApiToolAttachDetachResponse,
    PlatformMemoryBlockUpdateRequest,
    PlatformModelUpdateRequest,
    PlatformRuntimeMessageRequest,
    PlatformSystemUpdateRequest,
    PlatformTestRunRequest,
)
from agent_platform_api.runtime import (
    agent_platform,
    ensure_agent_not_archived,
    ensure_platform_api_enabled,
    test_orchestrator,
)

router = APIRouter()


@router.post(
    "/api/v1/platform/agents/{agent_id}/messages",
    response_model=ApiRuntimeMessageResponse,
    tags=["platform-runtime"],
    summary="Send runtime message with optional overrides",
)
async def api_platform_send_message(agent_id: str, request: PlatformRuntimeMessageRequest):
    ensure_platform_api_enabled()
    ensure_agent_not_archived(agent_id)

    text = request.input.strip()
    if not text:
        raise HTTPException(status_code=400, detail="input is required")

    try:
        return agent_platform.send_runtime_message(
            agent_id=agent_id,
            message=text,
            override_model=(request.override_model or "").strip() or None,
            override_system=(request.override_system or "").strip() or None,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch(
    "/api/v1/platform/agents/{agent_id}/system",
    response_model=ApiSystemUpdateResponse,
    tags=["platform-control"],
    summary="Update persisted system prompt",
)
async def api_platform_update_system(agent_id: str, request: PlatformSystemUpdateRequest):
    ensure_platform_api_enabled()
    ensure_agent_not_archived(agent_id)

    system_text = request.system.strip()
    if not system_text:
        raise HTTPException(status_code=400, detail="system is required")

    try:
        payload = agent_platform.update_system_prompt(agent_id=agent_id, system_prompt=system_text)
        append_prompt_persona_revision(
            agent_id=agent_id,
            field="system",
            before=str(payload.get("system_before", "") or ""),
            after=str(payload.get("system_after", "") or ""),
            source="api/v1/platform/agents/{agent_id}/system",
        )
        return payload
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch(
    "/api/v1/platform/agents/{agent_id}/model",
    response_model=ApiModelUpdateResponse,
    tags=["platform-control"],
    summary="Update persisted agent model",
)
async def api_platform_update_model(agent_id: str, request: PlatformModelUpdateRequest):
    ensure_platform_api_enabled()
    ensure_agent_not_archived(agent_id)

    model_handle = request.model.strip()
    if not model_handle:
        raise HTTPException(status_code=400, detail="model is required")

    try:
        return agent_platform.update_agent_model(agent_id=agent_id, model_handle=model_handle)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch(
    "/api/v1/platform/agents/{agent_id}/core-memory/blocks/{block_label}",
    response_model=ApiMemoryBlockUpdateResponse,
    tags=["platform-control"],
    summary="Update core-memory block value",
)
async def api_platform_update_memory_block(
    agent_id: str,
    block_label: str,
    request: PlatformMemoryBlockUpdateRequest,
):
    ensure_platform_api_enabled()
    ensure_agent_not_archived(agent_id)

    label = block_label.strip()
    if not label:
        raise HTTPException(status_code=400, detail="block_label is required")

    try:
        payload = agent_platform.update_core_memory_block(
            agent_id=agent_id,
            block_label=label,
            value=request.value,
        )
        if label in {"persona", "human"}:
            append_prompt_persona_revision(
                agent_id=agent_id,
                field=label,
                before=str(payload.get("value_before", "") or ""),
                after=str(payload.get("value_after", "") or ""),
                source=f"api/v1/platform/agents/{{agent_id}}/core-memory/blocks/{label}",
            )
        return payload
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch(
    "/api/v1/platform/agents/{agent_id}/tools/attach/{tool_id}",
    response_model=ApiToolAttachDetachResponse,
    tags=["platform-tools"],
    summary="Attach tool to agent",
)
async def api_platform_attach_tool(agent_id: str, tool_id: str):
    ensure_platform_api_enabled()
    ensure_agent_not_archived(agent_id)

    resolved_tool_id = tool_id.strip()
    if not resolved_tool_id:
        raise HTTPException(status_code=400, detail="tool_id is required")

    try:
        return agent_platform.attach_tool(agent_id=agent_id, tool_id=resolved_tool_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch(
    "/api/v1/platform/agents/{agent_id}/tools/detach/{tool_id}",
    response_model=ApiToolAttachDetachResponse,
    tags=["platform-tools"],
    summary="Detach tool from agent",
)
async def api_platform_detach_tool(agent_id: str, tool_id: str):
    ensure_platform_api_enabled()
    ensure_agent_not_archived(agent_id)

    resolved_tool_id = tool_id.strip()
    if not resolved_tool_id:
        raise HTTPException(status_code=400, detail="tool_id is required")

    try:
        return agent_platform.detach_tool(agent_id=agent_id, tool_id=resolved_tool_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/api/v1/platform/test-runs",
    response_model=ApiTestRunListResponse,
    tags=["platform-tests"],
    summary="List orchestrated test runs",
)
async def api_platform_list_test_runs():
    ensure_platform_api_enabled()
    return {"items": test_orchestrator.list_runs()}


@router.post(
    "/api/v1/platform/test-runs",
    response_model=ApiTestRunRecordResponse,
    tags=["platform-tests"],
    summary="Create orchestrated test run",
)
async def api_platform_create_test_run(request: PlatformTestRunRequest):
    ensure_platform_api_enabled()

    try:
        return test_orchestrator.create_run(
            run_type=request.run_type,
            model=request.model,
            embedding=request.embedding,
            rounds=request.rounds,
            config_path=request.config_path,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/api/v1/platform/test-runs/{run_id}",
    response_model=ApiTestRunRecordResponse,
    tags=["platform-tests"],
    summary="Get orchestrated test run",
)
async def api_platform_get_test_run(run_id: str):
    ensure_platform_api_enabled()

    run = test_orchestrator.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run_id not found")
    return run


@router.post(
    "/api/v1/platform/test-runs/{run_id}/cancel",
    response_model=ApiTestRunRecordResponse,
    tags=["platform-tests"],
    summary="Cancel orchestrated test run",
)
async def api_platform_cancel_test_run(run_id: str):
    ensure_platform_api_enabled()

    run = test_orchestrator.cancel_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run_id not found")
    return run


@router.get(
    "/api/v1/platform/test-runs/{run_id}/artifacts",
    response_model=ApiTestArtifactListResponse,
    tags=["platform-tests"],
    summary="List test run artifacts",
)
async def api_platform_list_test_run_artifacts(run_id: str):
    ensure_platform_api_enabled()

    artifacts = test_orchestrator.list_artifacts(run_id)
    if artifacts is None:
        raise HTTPException(status_code=404, detail="run_id not found")
    return {
        "run_id": run_id,
        "items": artifacts,
    }


@router.get(
    "/api/v1/platform/test-runs/{run_id}/artifacts/{artifact_id}",
    response_model=ApiTestArtifactReadResponse,
    tags=["platform-tests"],
    summary="Read test run artifact content",
)
async def api_platform_read_test_run_artifact(run_id: str, artifact_id: str, max_lines: int = 400):
    ensure_platform_api_enabled()

    payload = test_orchestrator.read_artifact(run_id, artifact_id, max_lines=max_lines)
    if payload is None:
        raise HTTPException(status_code=404, detail="run_id or artifact_id not found")
    return payload

