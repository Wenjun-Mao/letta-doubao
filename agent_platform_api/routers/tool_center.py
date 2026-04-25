from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from agent_platform_api.mappers import as_tool_center_item, managed_tool_tags
from agent_platform_api.models.templates import (
    ApiToolCenterItemResponse,
    ApiToolCenterListResponse,
    ToolCenterCreateRequest,
    ToolCenterUpdateRequest,
)
from agent_platform_api.openapi_metadata import TAG_TOOL_CENTER
from agent_platform_api.runtime import agent_platform, custom_tool_registry, ensure_platform_api_enabled
from agent_platform_api.registries.custom_tool import ToolRegistryError

router = APIRouter()


@router.get(
    "/api/v1/platform/tool-center/tools",
    response_model=ApiToolCenterListResponse,
    tags=[TAG_TOOL_CENTER],
    summary="List Tool Center entries",
)
async def api_tool_center_list_tools(
    include_archived: bool = False,
    include_builtin: bool = True,
    include_source: bool = False,
    search: str = "",
):
    ensure_platform_api_enabled()
    query = str(search or "").strip().lower()

    def matches_query(*values: str) -> bool:
        if not query:
            return True
        combined = "\n".join(str(value or "") for value in values).lower()
        return query in combined

    managed_records = custom_tool_registry.list_tools(
        include_archived=include_archived,
        include_source=include_source,
    )
    remote_tools = agent_platform.list_available_tools(search=None, limit=500)
    remote_by_id = {
        str(tool.get("id", "") or ""): tool
        for tool in remote_tools
        if str(tool.get("id", "") or "").strip()
    }

    items: list[dict[str, Any]] = []
    managed_ids: set[str] = set()
    for managed in managed_records:
        tool_id = str(managed.get("tool_id", "") or "")
        if tool_id:
            managed_ids.add(tool_id)
        if not matches_query(
            str(managed.get("slug", "") or ""),
            str(managed.get("name", "") or ""),
            str(managed.get("description", "") or ""),
        ):
            continue

        remote_tool = None if bool(managed.get("archived", False)) else remote_by_id.get(tool_id)
        items.append(
            as_tool_center_item(
                managed_entry=managed,
                remote_tool=remote_tool,
                include_source=include_source,
            )
        )

    if include_builtin:
        for remote in remote_tools:
            tool_id = str(remote.get("id", "") or "")
            if not tool_id or tool_id in managed_ids:
                continue
            if not matches_query(
                str(remote.get("name", "") or ""),
                str(remote.get("description", "") or ""),
                str(remote.get("tool_type", "") or ""),
            ):
                continue

            items.append(
                as_tool_center_item(
                    managed_entry=None,
                    remote_tool=remote,
                    include_source=False,
                )
            )

    return {
        "total": len(items),
        "include_archived": include_archived,
        "include_builtin": include_builtin,
        "items": items,
    }


@router.get(
    "/api/v1/platform/tool-center/tools/{slug}",
    response_model=ApiToolCenterItemResponse,
    tags=[TAG_TOOL_CENTER],
    summary="Get Tool Center managed custom tool",
)
async def api_tool_center_get_tool(slug: str, include_source: bool = True):
    ensure_platform_api_enabled()

    try:
        managed = custom_tool_registry.get_tool(slug, include_source=include_source)
    except ToolRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not managed:
        raise HTTPException(status_code=404, detail="Managed custom tool not found")

    remote_tool: dict[str, Any] | None = None
    if not bool(managed.get("archived", False)):
        tool_id = str(managed.get("tool_id", "") or "")
        if tool_id:
            try:
                remote_tool = agent_platform.retrieve_tool(tool_id=tool_id)
            except Exception:
                remote_tool = None

    return as_tool_center_item(
        managed_entry=managed,
        remote_tool=remote_tool,
        include_source=include_source,
    )


@router.post(
    "/api/v1/platform/tool-center/tools",
    response_model=ApiToolCenterItemResponse,
    tags=[TAG_TOOL_CENTER],
    summary="Create managed custom tool",
)
async def api_tool_center_create_tool(request: ToolCenterCreateRequest):
    ensure_platform_api_enabled()
    if not request.source_code.strip():
        raise HTTPException(status_code=400, detail="source_code is required")

    tags = managed_tool_tags(request.tags)
    try:
        created_remote = agent_platform.create_tool(
            source_code=request.source_code,
            description=request.description,
            tags=tags,
            source_type=request.source_type,
            enable_parallel_execution=request.enable_parallel_execution,
            default_requires_approval=request.default_requires_approval,
            return_char_limit=request.return_char_limit,
            pip_requirements=request.pip_requirements,
            npm_requirements=request.npm_requirements,
        )
        managed = custom_tool_registry.create_tool(
            slug=request.slug,
            tool_id=str(created_remote.get("id", "") or ""),
            name=str(created_remote.get("name", "") or request.slug),
            description=str(created_remote.get("description", "") or request.description),
            source_code=request.source_code,
            tags=[str(tag) for tag in (created_remote.get("tags", tags) or []) if str(tag).strip()],
            source_type=str(created_remote.get("source_type", request.source_type) or request.source_type),
            tool_type=str(created_remote.get("tool_type", "custom") or "custom"),
        )
    except (ToolRegistryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return as_tool_center_item(managed_entry=managed, remote_tool=created_remote, include_source=True)


@router.patch(
    "/api/v1/platform/tool-center/tools/{slug}",
    response_model=ApiToolCenterItemResponse,
    tags=[TAG_TOOL_CENTER],
    summary="Update managed custom tool",
)
async def api_tool_center_update_tool(slug: str, request: ToolCenterUpdateRequest):
    ensure_platform_api_enabled()

    if (
        request.source_code is None
        and request.description is None
        and request.tags is None
        and request.source_type is None
        and request.enable_parallel_execution is None
        and request.default_requires_approval is None
        and request.return_char_limit is None
        and request.pip_requirements is None
        and request.npm_requirements is None
    ):
        raise HTTPException(status_code=400, detail="At least one updatable field is required")

    try:
        managed = custom_tool_registry.get_tool(slug, include_source=True)
        if not managed:
            raise HTTPException(status_code=404, detail="Managed custom tool not found")
        if bool(managed.get("archived", False)):
            raise HTTPException(status_code=400, detail="Archived tool must be restored before update")

        tool_id = str(managed.get("tool_id", "") or "")
        if not tool_id:
            raise HTTPException(status_code=400, detail="Managed custom tool is missing tool_id")

        merged_tags = request.tags
        if merged_tags is not None:
            merged_tags = managed_tool_tags(merged_tags)

        updated_remote = agent_platform.update_tool(
            tool_id=tool_id,
            source_code=request.source_code,
            description=request.description,
            tags=merged_tags,
            source_type=request.source_type,
            enable_parallel_execution=request.enable_parallel_execution,
            default_requires_approval=request.default_requires_approval,
            return_char_limit=request.return_char_limit,
            pip_requirements=request.pip_requirements,
            npm_requirements=request.npm_requirements,
        )
        updated_managed = custom_tool_registry.update_tool(
            slug=slug,
            tool_id=str(updated_remote.get("id", "") or tool_id),
            name=str(updated_remote.get("name", "") or managed.get("name", "")),
            description=str(
                updated_remote.get("description", "") or request.description or managed.get("description", "")
            ),
            source_code=request.source_code,
            tags=[
                str(tag)
                for tag in (updated_remote.get("tags", merged_tags or managed.get("tags", [])) or [])
                if str(tag).strip()
            ],
            source_type=str(
                updated_remote.get("source_type", request.source_type or managed.get("source_type", "python"))
                or "python"
            ),
            tool_type=str(updated_remote.get("tool_type", managed.get("tool_type", "custom")) or "custom"),
        )
    except HTTPException:
        raise
    except (ToolRegistryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return as_tool_center_item(managed_entry=updated_managed, remote_tool=updated_remote, include_source=True)


@router.post(
    "/api/v1/platform/tool-center/tools/{slug}/archive",
    response_model=ApiToolCenterItemResponse,
    tags=[TAG_TOOL_CENTER],
    summary="Archive managed custom tool",
)
async def api_tool_center_archive_tool(slug: str):
    ensure_platform_api_enabled()

    try:
        managed = custom_tool_registry.get_tool(slug, include_source=True)
        if not managed:
            raise HTTPException(status_code=404, detail="Managed custom tool not found")
        if bool(managed.get("archived", False)):
            raise HTTPException(status_code=400, detail="Tool is already archived")

        tool_id = str(managed.get("tool_id", "") or "")
        if not tool_id:
            raise HTTPException(status_code=400, detail="Managed custom tool is missing tool_id")

        agent_platform.delete_tool(tool_id=tool_id)
        archived = custom_tool_registry.archive_tool(slug)
    except HTTPException:
        raise
    except (ToolRegistryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return as_tool_center_item(managed_entry=archived, remote_tool=None, include_source=True)


@router.post(
    "/api/v1/platform/tool-center/tools/{slug}/restore",
    response_model=ApiToolCenterItemResponse,
    tags=[TAG_TOOL_CENTER],
    summary="Restore archived managed custom tool",
)
async def api_tool_center_restore_tool(slug: str):
    ensure_platform_api_enabled()

    try:
        managed = custom_tool_registry.get_tool(slug, include_source=True)
        if not managed:
            raise HTTPException(status_code=404, detail="Managed custom tool not found")
        if not bool(managed.get("archived", False)):
            raise HTTPException(status_code=400, detail="Tool is not archived")

        source_code = str(managed.get("source_code", "") or "")
        if not source_code.strip():
            raise HTTPException(status_code=400, detail="Archived source_code is missing")

        tags = managed_tool_tags([str(tag) for tag in (managed.get("tags", []) or []) if str(tag).strip()])
        restored_remote = agent_platform.create_tool(
            source_code=source_code,
            description=str(managed.get("description", "") or ""),
            tags=tags,
            source_type=str(managed.get("source_type", "python") or "python"),
        )
        restored = custom_tool_registry.restore_tool(
            slug=slug,
            tool_id=str(restored_remote.get("id", "") or ""),
            name=str(restored_remote.get("name", "") or slug),
            description=str(restored_remote.get("description", "") or managed.get("description", "")),
            tags=[str(tag) for tag in (restored_remote.get("tags", tags) or []) if str(tag).strip()],
            source_type=str(
                restored_remote.get("source_type", managed.get("source_type", "python")) or "python"
            ),
            tool_type=str(
                restored_remote.get("tool_type", managed.get("tool_type", "custom")) or "custom"
            ),
        )
    except HTTPException:
        raise
    except (ToolRegistryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return as_tool_center_item(managed_entry=restored, remote_tool=restored_remote, include_source=True)


@router.delete(
    "/api/v1/platform/tool-center/tools/{slug}/purge",
    tags=[TAG_TOOL_CENTER],
    summary="Purge archived managed custom tool",
)
async def api_tool_center_purge_tool(slug: str):
    ensure_platform_api_enabled()

    try:
        custom_tool_registry.purge_tool(slug)
    except ToolRegistryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"ok": True, "slug": slug, "kind": "custom_tool"}

