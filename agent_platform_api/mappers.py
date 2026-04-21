from __future__ import annotations

from typing import Any

from agent_platform_api.runtime import MANAGED_TOOL_TAG


def agent_lifecycle_payload(
    record: dict[str, Any],
    *,
    fallback_name: str = "",
    fallback_model: str = "",
) -> dict[str, Any]:
    return {
        "id": str(record.get("id", "") or ""),
        "name": str(record.get("name", "") or fallback_name),
        "model": str(record.get("model", "") or fallback_model),
        "archived": bool(record.get("archived", False)),
        "archived_at": record.get("archived_at"),
        "updated_at": str(record.get("updated_at", "") or ""),
    }


def as_template_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": str(record.get("kind", "") or ""),
        "scenario": str(record.get("scenario", "") or "chat"),
        "key": str(record.get("key", "") or ""),
        "label": str(record.get("label", "") or ""),
        "description": str(record.get("description", "") or ""),
        "content": str(record.get("content", "") or ""),
        "preview": str(record.get("preview", "") or ""),
        "length": int(record.get("length", 0) or 0),
        "archived": bool(record.get("archived", False)),
        "source_path": str(record.get("source_path", "") or ""),
        "updated_at": str(record.get("updated_at", "") or ""),
    }


def managed_tool_tags(extra_tags: list[str] | None = None) -> list[str]:
    tags = [MANAGED_TOOL_TAG]
    for raw in extra_tags or []:
        tag = str(raw or "").strip()
        if not tag or tag in tags:
            continue
        tags.append(tag)
    return tags


def as_tool_center_item(
    *,
    managed_entry: dict[str, Any] | None,
    remote_tool: dict[str, Any] | None,
    include_source: bool,
) -> dict[str, Any]:
    if managed_entry:
        return {
            "slug": str(managed_entry.get("slug", "") or ""),
            "tool_id": str(managed_entry.get("tool_id", "") or ""),
            "name": str((remote_tool or {}).get("name", managed_entry.get("name", "")) or ""),
            "description": str((remote_tool or {}).get("description", managed_entry.get("description", "")) or ""),
            "tool_type": str((remote_tool or {}).get("tool_type", managed_entry.get("tool_type", "custom")) or "custom"),
            "source_type": str((remote_tool or {}).get("source_type", managed_entry.get("source_type", "python")) or "python"),
            "tags": [str(tag) for tag in ((remote_tool or {}).get("tags", managed_entry.get("tags", [])) or []) if str(tag).strip()],
            "managed": True,
            "read_only": False,
            "archived": bool(managed_entry.get("archived", False)),
            "source_path": str(managed_entry.get("source_path", "") or "") or None,
            "source_code": str(managed_entry.get("source_code", "") or "") if include_source else None,
            "created_at": str((remote_tool or {}).get("created_at", managed_entry.get("created_at", "")) or ""),
            "last_updated_at": str((remote_tool or {}).get("last_updated_at", managed_entry.get("updated_at", "")) or ""),
            "updated_at": str(managed_entry.get("updated_at", "") or "") or None,
            "archived_at": managed_entry.get("archived_at"),
        }

    tool = remote_tool or {}
    return {
        "slug": None,
        "tool_id": str(tool.get("id", "") or ""),
        "name": str(tool.get("name", "") or ""),
        "description": str(tool.get("description", "") or ""),
        "tool_type": str(tool.get("tool_type", "") or ""),
        "source_type": str(tool.get("source_type", "") or ""),
        "tags": [str(tag) for tag in (tool.get("tags", []) or []) if str(tag).strip()],
        "managed": False,
        "read_only": True,
        "archived": False,
        "source_path": None,
        "source_code": None,
        "created_at": str(tool.get("created_at", "") or ""),
        "last_updated_at": str(tool.get("last_updated_at", "") or ""),
        "updated_at": None,
        "archived_at": None,
    }

