from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from tests.shared.config_defaults import DEFAULT_AGENT_PLATFORM_API_BASE_URL

AGENT_PLATFORM_API_BASE_URL = os.getenv("AGENT_PLATFORM_API_BASE_URL", DEFAULT_AGENT_PLATFORM_API_BASE_URL)


def _as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _status_ok(response: httpx.Response, allowed: tuple[int, ...]) -> bool:
    return int(response.status_code) in set(allowed)


def _require_status(response: httpx.Response, *, allowed: tuple[int, ...], action: str) -> None:
    if _status_ok(response, allowed):
        return
    raise RuntimeError(f"{action} failed: status={response.status_code} body={response.text}")


def _resolve_create_payload(options_payload: dict[str, Any], stamp: int) -> dict[str, Any]:
    models = list(options_payload.get("models", []) or [])
    prompts = list(options_payload.get("prompts", []) or [])
    personas = list(options_payload.get("personas", []) or [])
    defaults = dict(options_payload.get("defaults", {}) or {})

    model_key = str(defaults.get("model", "") or "").strip()
    if not model_key:
        available_models = [str(item.get("key", "") or "") for item in models if bool(item.get("available", True))]
        model_key = available_models[0] if available_models else str(models[0].get("key", "") or "")

    prompt_key = str(defaults.get("prompt_key", "") or "").strip()
    if not prompt_key and prompts:
        prompt_key = str(prompts[0].get("key", "") or "")

    persona_key = str(defaults.get("persona_key", "") or "").strip()
    if not persona_key and personas:
        persona_key = str(personas[0].get("key", "") or "")

    if not model_key:
        raise RuntimeError("No model option is available for agent creation")
    if not prompt_key:
        raise RuntimeError("No prompt template option is available for agent creation")
    if not persona_key:
        raise RuntimeError("No persona option is available for agent creation")

    embedding_value = str(defaults.get("embedding", "") or "").strip() or None

    return {
        "scenario": "chat",
        "name": f"tmp-agent-archive-{stamp}",
        "model": model_key,
        "prompt_key": prompt_key,
        "persona_key": persona_key,
        "embedding": embedding_value,
    }


def _cleanup_agent(http: httpx.Client, agent_id: str | None) -> None:
    if not agent_id:
        return

    archive = http.post(f"/api/v1/platform/agents/{agent_id}/archive")
    if archive.status_code not in {200, 400, 404}:
        raise RuntimeError(f"cleanup archive failed: status={archive.status_code} body={archive.text}")

    purge_platform = http.delete(f"/api/v1/platform/agents/{agent_id}/purge")
    if purge_platform.status_code in {200, 400, 404}:
        return

    purge_alias = http.delete(f"/api/v1/agents/{agent_id}")
    if purge_alias.status_code not in {200, 400, 404}:
        raise RuntimeError(f"cleanup purge failed: status={purge_alias.status_code} body={purge_alias.text}")


def _agent_present(items: list[dict[str, Any]], agent_id: str) -> bool:
    return any(str(item.get("id", "") or "") == agent_id for item in items)


def _agent_archived_flag(items: list[dict[str, Any]], agent_id: str) -> bool | None:
    for item in items:
        if str(item.get("id", "") or "") != agent_id:
            continue
        return bool(item.get("archived", False))
    return None


def main() -> None:
    summary: dict[str, Any] = {
        "name": "agent_archive_api_check",
        "ok": False,
        "steps": {},
        "detail": "",
    }

    stamp = int(time.time())
    primary_agent_id: str | None = None
    alias_agent_id: str | None = None

    try:
        with httpx.Client(base_url=AGENT_PLATFORM_API_BASE_URL, timeout=90.0) as http:
            capabilities = http.get("/api/v1/platform/capabilities")
            _require_status(capabilities, allowed=(200,), action="capabilities")
            if not bool(capabilities.json().get("enabled", False)):
                raise RuntimeError("Platform API is not enabled")

            options = http.get("/api/v1/options", params={"scenario": "chat"})
            _require_status(options, allowed=(200,), action="options")
            create_payload = _resolve_create_payload(options.json(), stamp)

            create_primary = http.post("/api/v1/agents", json=create_payload)
            _require_status(create_primary, allowed=(200,), action="create primary agent")
            primary_agent_id = str(create_primary.json().get("id", "") or "")
            if not primary_agent_id:
                raise RuntimeError("Primary agent creation returned empty id")

            list_active_before = http.get("/api/v1/agents")
            _require_status(list_active_before, allowed=(200,), action="list active before archive")
            list_active_before_items = list(list_active_before.json().get("items", []) or [])
            if not _agent_present(list_active_before_items, primary_agent_id):
                raise RuntimeError("Newly created agent is missing from default active list")

            archive = http.post(f"/api/v1/platform/agents/{primary_agent_id}/archive")
            _require_status(archive, allowed=(200,), action="archive primary agent")
            if not bool(archive.json().get("archived", False)):
                raise RuntimeError("Archive response did not return archived=true")

            list_active_after_archive = http.get("/api/v1/agents")
            _require_status(list_active_after_archive, allowed=(200,), action="list active after archive")
            if _agent_present(list(list_active_after_archive.json().get("items", []) or []), primary_agent_id):
                raise RuntimeError("Archived agent still appears in default active list")

            list_with_archived = http.get("/api/v1/agents", params={"include_archived": "true"})
            _require_status(list_with_archived, allowed=(200,), action="list include archived")
            list_with_archived_items = list(list_with_archived.json().get("items", []) or [])
            if not _agent_present(list_with_archived_items, primary_agent_id):
                raise RuntimeError("Archived agent missing from include_archived list")
            archived_flag = _agent_archived_flag(list_with_archived_items, primary_agent_id)
            if archived_flag is not True:
                raise RuntimeError("include_archived list did not mark archived agent correctly")

            chat_blocked = http.post(
                "/api/v1/chat",
                json={"agent_id": primary_agent_id, "message": "Archive state guard check"},
            )
            _require_status(chat_blocked, allowed=(409, 410), action="chat guard while archived")

            restore = http.post(f"/api/v1/platform/agents/{primary_agent_id}/restore")
            _require_status(restore, allowed=(200,), action="restore primary agent")
            if bool(restore.json().get("archived", True)):
                raise RuntimeError("Restore response did not return archived=false")

            purge_non_archived = http.delete(f"/api/v1/platform/agents/{primary_agent_id}/purge")
            _require_status(purge_non_archived, allowed=(400,), action="purge non-archived agent")

            archive_for_purge = http.post(f"/api/v1/platform/agents/{primary_agent_id}/archive")
            _require_status(archive_for_purge, allowed=(200,), action="archive for purge")

            purge_primary = http.delete(f"/api/v1/platform/agents/{primary_agent_id}/purge")
            _require_status(purge_primary, allowed=(200,), action="purge primary agent")

            restore_after_purge = http.post(f"/api/v1/platform/agents/{primary_agent_id}/restore")
            _require_status(restore_after_purge, allowed=(400, 404), action="restore after purge")

            create_alias_payload = dict(create_payload)
            create_alias_payload["name"] = f"tmp-agent-delete-alias-{stamp}"
            create_alias = http.post("/api/v1/agents", json=create_alias_payload)
            _require_status(create_alias, allowed=(200,), action="create alias agent")
            alias_agent_id = str(create_alias.json().get("id", "") or "")
            if not alias_agent_id:
                raise RuntimeError("Alias agent creation returned empty id")

            alias_archive = http.post(f"/api/v1/platform/agents/{alias_agent_id}/archive")
            _require_status(alias_archive, allowed=(200,), action="archive alias agent")

            alias_delete = http.delete(f"/api/v1/agents/{alias_agent_id}")
            _require_status(alias_delete, allowed=(200,), action="delete alias agent")

            summary["steps"]["archive_restore_purge"] = {
                "ok": True,
                "primary_agent_id": primary_agent_id,
                "guards": {
                    "chat_while_archived": chat_blocked.status_code,
                    "purge_non_archived": purge_non_archived.status_code,
                    "restore_after_purge": restore_after_purge.status_code,
                },
            }
            summary["steps"]["delete_alias"] = {
                "ok": True,
                "alias_agent_id": alias_agent_id,
                "delete_status": alias_delete.status_code,
            }

        summary["ok"] = True
        summary["detail"] = "agent archive/restore/purge/delete alias checks passed"

    except Exception as exc:
        summary["detail"] = str(exc)
        raise

    finally:
        try:
            with httpx.Client(base_url=AGENT_PLATFORM_API_BASE_URL, timeout=30.0) as cleanup_http:
                _cleanup_agent(cleanup_http, primary_agent_id)
                _cleanup_agent(cleanup_http, alias_agent_id)
        except Exception:
            pass

        print(_as_json(summary))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[FAIL] agent_archive_api_check: {exc}")
        raise

