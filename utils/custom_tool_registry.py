from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


class ToolRegistryError(ValueError):
    """Raised when custom tool registry operations fail."""


class CustomToolRegistry:
    """Workspace-persisted custom tool registry for ADE Tool Center."""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        self.base_dir = self.project_root / "tools" / "custom"
        self.archive_dir = self.base_dir / "archive"
        self.manifest_path = self.base_dir / "registry.json"

        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_manifest()

    def list_tools(self, *, include_archived: bool = False, include_source: bool = False) -> list[dict[str, Any]]:
        manifest = self._load_manifest()
        output: list[dict[str, Any]] = []
        tools = manifest.get("tools", {}) if isinstance(manifest.get("tools", {}), dict) else {}

        for slug, payload in tools.items():
            if not isinstance(payload, dict):
                continue
            archived = bool(payload.get("archived", False))
            if archived and not include_archived:
                continue

            item = self._record_for(slug=slug, payload=payload, include_source=include_source)
            output.append(item)

        output.sort(key=lambda entry: (bool(entry.get("archived", False)), str(entry.get("slug", ""))))
        return output

    def get_tool(self, slug: str, *, include_source: bool = False) -> dict[str, Any] | None:
        normalized = self._normalize_slug(slug)
        manifest = self._load_manifest()
        payload = manifest.get("tools", {}).get(normalized)
        if not isinstance(payload, dict):
            return None
        return self._record_for(slug=normalized, payload=payload, include_source=include_source)

    def create_tool(
        self,
        *,
        slug: str,
        tool_id: str,
        name: str,
        description: str,
        source_code: str,
        tags: list[str] | None = None,
        source_type: str = "python",
        tool_type: str = "custom",
    ) -> dict[str, Any]:
        normalized = self._normalize_slug(slug)
        manifest = self._load_manifest()
        tools = manifest.setdefault("tools", {})
        if normalized in tools:
            raise ToolRegistryError(f"Tool '{normalized}' already exists")

        now = self._now_iso()
        active_path = self._source_path_for(slug=normalized, archived=False)
        active_path.parent.mkdir(parents=True, exist_ok=True)
        active_path.write_text(source_code, encoding="utf-8")

        tools[normalized] = {
            "slug": normalized,
            "tool_id": str(tool_id or ""),
            "name": str(name or normalized),
            "description": str(description or ""),
            "tags": [str(tag) for tag in (tags or []) if str(tag).strip()],
            "source_type": str(source_type or "python"),
            "tool_type": str(tool_type or "custom"),
            "archived": False,
            "created_at": now,
            "updated_at": now,
            "archived_at": None,
        }
        self._save_manifest(manifest)
        return self.get_tool(normalized, include_source=True) or {}

    def update_tool(
        self,
        *,
        slug: str,
        tool_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        source_code: str | None = None,
        tags: list[str] | None = None,
        source_type: str | None = None,
        tool_type: str | None = None,
    ) -> dict[str, Any]:
        normalized = self._normalize_slug(slug)
        manifest = self._load_manifest()
        tools = manifest.setdefault("tools", {})
        payload = tools.get(normalized)
        if not isinstance(payload, dict):
            raise ToolRegistryError(f"Tool '{normalized}' not found")
        if bool(payload.get("archived", False)):
            raise ToolRegistryError(f"Tool '{normalized}' is archived")

        if tool_id is not None:
            payload["tool_id"] = str(tool_id)
        if name is not None:
            payload["name"] = str(name)
        if description is not None:
            payload["description"] = str(description)
        if tags is not None:
            payload["tags"] = [str(tag) for tag in tags if str(tag).strip()]
        if source_type is not None:
            payload["source_type"] = str(source_type)
        if tool_type is not None:
            payload["tool_type"] = str(tool_type)

        if source_code is not None:
            active_path = self._source_path_for(slug=normalized, archived=False)
            active_path.parent.mkdir(parents=True, exist_ok=True)
            active_path.write_text(source_code, encoding="utf-8")

        payload["updated_at"] = self._now_iso()
        self._save_manifest(manifest)
        return self.get_tool(normalized, include_source=True) or {}

    def archive_tool(self, slug: str) -> dict[str, Any]:
        normalized = self._normalize_slug(slug)
        manifest = self._load_manifest()
        tools = manifest.setdefault("tools", {})
        payload = tools.get(normalized)
        if not isinstance(payload, dict):
            raise ToolRegistryError(f"Tool '{normalized}' not found")
        if bool(payload.get("archived", False)):
            raise ToolRegistryError(f"Tool '{normalized}' is already archived")

        active_path = self._source_path_for(slug=normalized, archived=False)
        archived_path = self._source_path_for(slug=normalized, archived=True)

        if not active_path.exists():
            raise ToolRegistryError(f"Source file for tool '{normalized}' was not found")
        if archived_path.exists():
            raise ToolRegistryError(f"Archived source already exists for '{normalized}'")

        archived_path.parent.mkdir(parents=True, exist_ok=True)
        active_path.replace(archived_path)

        now = self._now_iso()
        payload["archived"] = True
        payload["archived_at"] = now
        payload["updated_at"] = now
        self._save_manifest(manifest)
        return self.get_tool(normalized, include_source=True) or {}

    def restore_tool(
        self,
        *,
        slug: str,
        tool_id: str,
        name: str,
        description: str,
        tags: list[str] | None = None,
        source_type: str | None = None,
        tool_type: str | None = None,
    ) -> dict[str, Any]:
        normalized = self._normalize_slug(slug)
        manifest = self._load_manifest()
        tools = manifest.setdefault("tools", {})
        payload = tools.get(normalized)
        if not isinstance(payload, dict):
            raise ToolRegistryError(f"Archived tool '{normalized}' not found")
        if not bool(payload.get("archived", False)):
            raise ToolRegistryError(f"Tool '{normalized}' is not archived")

        archived_path = self._source_path_for(slug=normalized, archived=True)
        active_path = self._source_path_for(slug=normalized, archived=False)
        if not archived_path.exists():
            raise ToolRegistryError(f"Archived source file for '{normalized}' was not found")
        if active_path.exists():
            raise ToolRegistryError(f"Active source file already exists for '{normalized}'")

        active_path.parent.mkdir(parents=True, exist_ok=True)
        archived_path.replace(active_path)

        now = self._now_iso()
        payload["tool_id"] = str(tool_id)
        payload["name"] = str(name or normalized)
        payload["description"] = str(description or "")
        payload["tags"] = [str(tag) for tag in (tags or []) if str(tag).strip()]
        if source_type is not None:
            payload["source_type"] = str(source_type)
        if tool_type is not None:
            payload["tool_type"] = str(tool_type)
        payload["archived"] = False
        payload["archived_at"] = None
        payload["updated_at"] = now
        self._save_manifest(manifest)
        return self.get_tool(normalized, include_source=True) or {}

    def purge_tool(self, slug: str) -> None:
        normalized = self._normalize_slug(slug)
        manifest = self._load_manifest()
        tools = manifest.setdefault("tools", {})
        payload = tools.get(normalized)
        if not isinstance(payload, dict):
            raise ToolRegistryError(f"Archived tool '{normalized}' not found")
        if not bool(payload.get("archived", False)):
            raise ToolRegistryError(f"Tool '{normalized}' must be archived before purge")

        source_path = self._source_path_for(slug=normalized, archived=True)
        if source_path.exists():
            source_path.unlink()
        del tools[normalized]
        self._save_manifest(manifest)

    def _record_for(self, *, slug: str, payload: dict[str, Any], include_source: bool) -> dict[str, Any]:
        archived = bool(payload.get("archived", False))
        source_path = self._source_path_for(slug=slug, archived=archived)
        record = {
            "slug": slug,
            "tool_id": str(payload.get("tool_id", "") or ""),
            "name": str(payload.get("name", "") or slug),
            "description": str(payload.get("description", "") or ""),
            "tags": [str(tag) for tag in (payload.get("tags") or []) if str(tag).strip()],
            "source_type": str(payload.get("source_type", "") or "python"),
            "tool_type": str(payload.get("tool_type", "") or "custom"),
            "archived": archived,
            "created_at": str(payload.get("created_at", "") or ""),
            "updated_at": str(payload.get("updated_at", "") or ""),
            "archived_at": payload.get("archived_at"),
            "source_path": source_path.relative_to(self.project_root).as_posix(),
        }

        if include_source:
            record["source_code"] = source_path.read_text(encoding="utf-8", errors="replace") if source_path.exists() else ""
        return record

    def _ensure_manifest(self) -> None:
        if self.manifest_path.exists():
            return
        seed = {"version": 1, "tools": {}}
        self.manifest_path.write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_manifest(self) -> dict[str, Any]:
        self._ensure_manifest()
        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ToolRegistryError(f"Failed to parse tool registry manifest: {exc}") from exc

        if not isinstance(raw, dict):
            raise ToolRegistryError("Tool registry manifest must be an object")
        if "tools" not in raw or not isinstance(raw.get("tools"), dict):
            raw["tools"] = {}
        return raw

    def _save_manifest(self, manifest: dict[str, Any]) -> None:
        payload = dict(manifest)
        payload.setdefault("version", 1)
        payload.setdefault("tools", {})
        self.manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _source_path_for(self, *, slug: str, archived: bool) -> Path:
        return (self.archive_dir if archived else self.base_dir) / f"{slug}.py"

    def _normalize_slug(self, slug: str) -> str:
        normalized = str(slug or "").strip().lower()
        if not _KEY_PATTERN.fullmatch(normalized):
            raise ToolRegistryError(
                "Invalid slug. Use 2-64 chars with lowercase letters, numbers, underscores, or hyphens; must start with a letter."
            )
        return normalized

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
