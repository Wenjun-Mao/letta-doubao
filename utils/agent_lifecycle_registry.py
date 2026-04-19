from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AgentLifecycleRegistryError(ValueError):
    """Raised when archive/restore/purge state transitions are invalid."""


class AgentLifecycleRegistry:
    """File-backed archive state for agents managed by the dev platform API."""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.base_dir = self.project_root / "data" / "agent_lifecycle"
        self.manifest_path = self.base_dir / "registry.json"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_manifest()

    def archived_agent_ids(self) -> set[str]:
        manifest = self._read_manifest()
        agents = manifest.get("agents", {})
        if not isinstance(agents, dict):
            return set()

        archived: set[str] = set()
        for agent_id, payload in agents.items():
            if not isinstance(payload, dict):
                continue
            if bool(payload.get("archived", False)):
                archived.add(str(agent_id))
        return archived

    def get_record(self, agent_id: str) -> dict[str, Any] | None:
        resolved_agent_id = self._normalize_agent_id(agent_id)
        manifest = self._read_manifest()
        payload = manifest.get("agents", {}).get(resolved_agent_id)
        if not isinstance(payload, dict):
            return None
        return self._to_record(resolved_agent_id, payload)

    def is_archived(self, agent_id: str) -> bool:
        record = self.get_record(agent_id)
        return bool(record and record.get("archived", False))

    def archive_agent(self, *, agent_id: str, name: str = "", model: str = "") -> dict[str, Any]:
        resolved_agent_id = self._normalize_agent_id(agent_id)
        manifest = self._read_manifest()
        agents = manifest.setdefault("agents", {})
        if not isinstance(agents, dict):
            agents = {}
            manifest["agents"] = agents

        current = agents.get(resolved_agent_id)
        if isinstance(current, dict) and bool(current.get("archived", False)):
            raise AgentLifecycleRegistryError(f"Agent '{resolved_agent_id}' is already archived")

        now = self._utc_now_iso()
        agents[resolved_agent_id] = {
            "name": str(name or (current or {}).get("name", "")),
            "model": str(model or (current or {}).get("model", "")),
            "archived": True,
            "archived_at": now,
            "updated_at": now,
        }

        self._write_manifest(manifest)
        return self._to_record(resolved_agent_id, agents[resolved_agent_id])

    def restore_agent(self, agent_id: str) -> dict[str, Any]:
        resolved_agent_id = self._normalize_agent_id(agent_id)
        manifest = self._read_manifest()
        agents = manifest.get("agents", {})
        payload = agents.get(resolved_agent_id) if isinstance(agents, dict) else None
        if not isinstance(payload, dict) or not bool(payload.get("archived", False)):
            raise AgentLifecycleRegistryError(f"Agent '{resolved_agent_id}' is not archived")

        payload["archived"] = False
        payload["archived_at"] = None
        payload["updated_at"] = self._utc_now_iso()

        self._write_manifest(manifest)
        return self._to_record(resolved_agent_id, payload)

    def purge_agent(self, agent_id: str) -> None:
        resolved_agent_id = self._normalize_agent_id(agent_id)
        manifest = self._read_manifest()
        agents = manifest.get("agents", {})
        if not isinstance(agents, dict):
            raise AgentLifecycleRegistryError(f"Agent '{resolved_agent_id}' is not archived")

        payload = agents.get(resolved_agent_id)
        if not isinstance(payload, dict) or not bool(payload.get("archived", False)):
            raise AgentLifecycleRegistryError(f"Agent '{resolved_agent_id}' is not archived")

        del agents[resolved_agent_id]
        self._write_manifest(manifest)

    def _ensure_manifest(self) -> None:
        if self.manifest_path.exists():
            return
        self._write_manifest({"version": 1, "agents": {}})

    def _read_manifest(self) -> dict[str, Any]:
        self._ensure_manifest()

        try:
            payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise AgentLifecycleRegistryError(f"Failed to read lifecycle registry: {exc}") from exc

        if not isinstance(payload, dict):
            raise AgentLifecycleRegistryError("Lifecycle registry root must be an object")

        if not isinstance(payload.get("agents"), dict):
            payload["agents"] = {}

        return payload

    def _write_manifest(self, manifest: dict[str, Any]) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _normalize_agent_id(agent_id: str) -> str:
        resolved = str(agent_id or "").strip()
        if not resolved:
            raise AgentLifecycleRegistryError("agent_id is required")
        return resolved

    @staticmethod
    def _to_record(agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": agent_id,
            "name": str(payload.get("name", "") or ""),
            "model": str(payload.get("model", "") or ""),
            "archived": bool(payload.get("archived", False)),
            "archived_at": payload.get("archived_at"),
            "updated_at": str(payload.get("updated_at", "") or ""),
        }

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
