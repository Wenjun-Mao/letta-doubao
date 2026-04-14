from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from tests.shared.config_defaults import DEFAULT_DEV_UI_BASE_URL

DEV_UI_BASE_URL = os.getenv("DEV_UI_BASE_URL", DEFAULT_DEV_UI_BASE_URL)


def _as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _status_ok(response: httpx.Response, allowed: tuple[int, ...]) -> bool:
    return int(response.status_code) in set(allowed)


def _require_status(
    response: httpx.Response,
    *,
    allowed: tuple[int, ...],
    action: str,
) -> None:
    if _status_ok(response, allowed):
        return
    raise RuntimeError(
        f"{action} failed: status={response.status_code} body={response.text}"
    )


def _cleanup_template(http: httpx.Client, *, kind: str, key: str) -> None:
    base = f"/api/v1/platform/prompt-center/{kind}/{key}"
    try:
        active = http.get(base)
        if active.status_code == 200:
            archive = http.post(f"{base}/archive")
            if archive.status_code not in {200, 400}:
                raise RuntimeError(
                    f"cleanup {kind} archive failed: status={archive.status_code} body={archive.text}"
                )
    except Exception:
        pass

    try:
        purge = http.delete(f"{base}/purge")
        if purge.status_code not in {200, 400, 404}:
            raise RuntimeError(
                f"cleanup {kind} purge failed: status={purge.status_code} body={purge.text}"
            )
    except Exception:
        pass


def _cleanup_tool(http: httpx.Client, *, slug: str) -> None:
    base = f"/api/v1/platform/tool-center/tools/{slug}"

    try:
        payload = http.get(base)
        if payload.status_code == 200:
            archived = bool(payload.json().get("archived", False))
            if not archived:
                archive = http.post(f"{base}/archive")
                if archive.status_code not in {200, 400}:
                    raise RuntimeError(
                        f"cleanup tool archive failed: status={archive.status_code} body={archive.text}"
                    )
    except Exception:
        pass

    try:
        purge = http.delete(f"{base}/purge")
        if purge.status_code not in {200, 400, 404}:
            raise RuntimeError(
                f"cleanup tool purge failed: status={purge.status_code} body={purge.text}"
            )
    except Exception:
        pass


def _run_prompt_flow(http: httpx.Client, *, key: str) -> dict[str, Any]:
    create = http.post(
        "/api/v1/platform/prompt-center/prompts",
        json={
            "key": key,
            "label": "Tmp Prompt Archive",
            "description": "Temp prompt for archive restore purge edge checks",
            "content": "你是一个用于归档恢复删除接口测试的临时提示词。",
        },
    )
    _require_status(create, allowed=(200,), action="prompt create")

    archive = http.post(f"/api/v1/platform/prompt-center/prompts/{key}/archive")
    _require_status(archive, allowed=(200,), action="prompt archive")

    archive_again = http.post(f"/api/v1/platform/prompt-center/prompts/{key}/archive")
    _require_status(archive_again, allowed=(400,), action="prompt archive again")

    restore = http.post(f"/api/v1/platform/prompt-center/prompts/{key}/restore")
    _require_status(restore, allowed=(200,), action="prompt restore")

    restore_again = http.post(f"/api/v1/platform/prompt-center/prompts/{key}/restore")
    _require_status(restore_again, allowed=(400,), action="prompt restore non-archived")

    archive_for_purge = http.post(f"/api/v1/platform/prompt-center/prompts/{key}/archive")
    _require_status(archive_for_purge, allowed=(200,), action="prompt archive for purge")

    purge = http.delete(f"/api/v1/platform/prompt-center/prompts/{key}/purge")
    _require_status(purge, allowed=(200,), action="prompt purge")

    restore_after_purge = http.post(f"/api/v1/platform/prompt-center/prompts/{key}/restore")
    _require_status(restore_after_purge, allowed=(400, 404), action="prompt restore after purge")

    key_non_archived = f"{key}_na"
    create_non_archived = http.post(
        "/api/v1/platform/prompt-center/prompts",
        json={
            "key": key_non_archived,
            "label": "Tmp Prompt Non Archived",
            "description": "Temp prompt for purge non-archived validation",
            "content": "这个提示词用于验证未归档时 purge 会失败。",
        },
    )
    _require_status(create_non_archived, allowed=(200,), action="prompt create non-archived")

    purge_non_archived = http.delete(f"/api/v1/platform/prompt-center/prompts/{key_non_archived}/purge")
    _require_status(purge_non_archived, allowed=(400,), action="prompt purge non-archived")

    archive_non_archived = http.post(f"/api/v1/platform/prompt-center/prompts/{key_non_archived}/archive")
    _require_status(archive_non_archived, allowed=(200,), action="prompt archive cleanup")

    purge_non_archived_cleanup = http.delete(f"/api/v1/platform/prompt-center/prompts/{key_non_archived}/purge")
    _require_status(purge_non_archived_cleanup, allowed=(200,), action="prompt purge cleanup")

    return {
        "ok": True,
        "key": key,
        "negative_checks": {
            "archive_again": archive_again.status_code,
            "restore_non_archived": restore_again.status_code,
            "restore_after_purge": restore_after_purge.status_code,
            "purge_non_archived": purge_non_archived.status_code,
        },
    }


def _run_persona_flow(http: httpx.Client, *, key: str) -> dict[str, Any]:
    create = http.post(
        "/api/v1/platform/prompt-center/personas",
        json={
            "key": key,
            "label": "Tmp Persona Archive",
            "description": "Temp persona for archive restore purge edge checks",
            "content": "你是一个用于归档恢复删除接口测试的临时 persona。",
        },
    )
    _require_status(create, allowed=(200,), action="persona create")

    archive = http.post(f"/api/v1/platform/prompt-center/personas/{key}/archive")
    _require_status(archive, allowed=(200,), action="persona archive")

    archive_again = http.post(f"/api/v1/platform/prompt-center/personas/{key}/archive")
    _require_status(archive_again, allowed=(400,), action="persona archive again")

    restore = http.post(f"/api/v1/platform/prompt-center/personas/{key}/restore")
    _require_status(restore, allowed=(200,), action="persona restore")

    restore_again = http.post(f"/api/v1/platform/prompt-center/personas/{key}/restore")
    _require_status(restore_again, allowed=(400,), action="persona restore non-archived")

    archive_for_purge = http.post(f"/api/v1/platform/prompt-center/personas/{key}/archive")
    _require_status(archive_for_purge, allowed=(200,), action="persona archive for purge")

    purge = http.delete(f"/api/v1/platform/prompt-center/personas/{key}/purge")
    _require_status(purge, allowed=(200,), action="persona purge")

    restore_after_purge = http.post(f"/api/v1/platform/prompt-center/personas/{key}/restore")
    _require_status(restore_after_purge, allowed=(400, 404), action="persona restore after purge")

    key_non_archived = f"{key}_na"
    create_non_archived = http.post(
        "/api/v1/platform/prompt-center/personas",
        json={
            "key": key_non_archived,
            "label": "Tmp Persona Non Archived",
            "description": "Temp persona for purge non-archived validation",
            "content": "这个 persona 用于验证未归档时 purge 会失败。",
        },
    )
    _require_status(create_non_archived, allowed=(200,), action="persona create non-archived")

    purge_non_archived = http.delete(f"/api/v1/platform/prompt-center/personas/{key_non_archived}/purge")
    _require_status(purge_non_archived, allowed=(400,), action="persona purge non-archived")

    archive_non_archived = http.post(f"/api/v1/platform/prompt-center/personas/{key_non_archived}/archive")
    _require_status(archive_non_archived, allowed=(200,), action="persona archive cleanup")

    purge_non_archived_cleanup = http.delete(f"/api/v1/platform/prompt-center/personas/{key_non_archived}/purge")
    _require_status(purge_non_archived_cleanup, allowed=(200,), action="persona purge cleanup")

    return {
        "ok": True,
        "key": key,
        "negative_checks": {
            "archive_again": archive_again.status_code,
            "restore_non_archived": restore_again.status_code,
            "restore_after_purge": restore_after_purge.status_code,
            "purge_non_archived": purge_non_archived.status_code,
        },
    }


def _tool_source(function_name: str) -> str:
    return (
        f"def {function_name}(input_text: str) -> str:\n"
        "    \"\"\"Return uppercase echo payload for API edge-case validation.\n\n"
        "    Args:\n"
        "        input_text: Input text to normalize and echo.\n\n"
        "    Returns:\n"
        "        Uppercase echo payload.\n"
        "    \"\"\"\n"
        "    return f\"EDGE::{input_text.strip().upper()}\"\n"
    )


def _run_tool_flow(http: httpx.Client, *, slug: str) -> dict[str, Any]:
    create = http.post(
        "/api/v1/platform/tool-center/tools",
        json={
            "slug": slug,
            "source_code": _tool_source(slug),
            "description": "Temp managed tool for archive restore purge edge checks",
            "tags": ["edge", "archive"],
            "source_type": "python",
        },
    )
    _require_status(create, allowed=(200,), action="tool create")

    archive = http.post(f"/api/v1/platform/tool-center/tools/{slug}/archive")
    _require_status(archive, allowed=(200,), action="tool archive")

    archive_again = http.post(f"/api/v1/platform/tool-center/tools/{slug}/archive")
    _require_status(archive_again, allowed=(400,), action="tool archive again")

    restore = http.post(f"/api/v1/platform/tool-center/tools/{slug}/restore")
    _require_status(restore, allowed=(200,), action="tool restore")

    restore_again = http.post(f"/api/v1/platform/tool-center/tools/{slug}/restore")
    _require_status(restore_again, allowed=(400,), action="tool restore non-archived")

    archive_for_purge = http.post(f"/api/v1/platform/tool-center/tools/{slug}/archive")
    _require_status(archive_for_purge, allowed=(200,), action="tool archive for purge")

    purge = http.delete(f"/api/v1/platform/tool-center/tools/{slug}/purge")
    _require_status(purge, allowed=(200,), action="tool purge")

    restore_after_purge = http.post(f"/api/v1/platform/tool-center/tools/{slug}/restore")
    _require_status(restore_after_purge, allowed=(400, 404), action="tool restore after purge")

    slug_non_archived = f"{slug}_na"
    create_non_archived = http.post(
        "/api/v1/platform/tool-center/tools",
        json={
            "slug": slug_non_archived,
            "source_code": _tool_source(slug_non_archived),
            "description": "Temp managed tool for purge non-archived validation",
            "tags": ["edge", "non-archived"],
            "source_type": "python",
        },
    )
    _require_status(create_non_archived, allowed=(200,), action="tool create non-archived")

    purge_non_archived = http.delete(f"/api/v1/platform/tool-center/tools/{slug_non_archived}/purge")
    _require_status(purge_non_archived, allowed=(400,), action="tool purge non-archived")

    archive_non_archived = http.post(f"/api/v1/platform/tool-center/tools/{slug_non_archived}/archive")
    _require_status(archive_non_archived, allowed=(200,), action="tool archive cleanup")

    purge_non_archived_cleanup = http.delete(f"/api/v1/platform/tool-center/tools/{slug_non_archived}/purge")
    _require_status(purge_non_archived_cleanup, allowed=(200,), action="tool purge cleanup")

    return {
        "ok": True,
        "slug": slug,
        "negative_checks": {
            "archive_again": archive_again.status_code,
            "restore_non_archived": restore_again.status_code,
            "restore_after_purge": restore_after_purge.status_code,
            "purge_non_archived": purge_non_archived.status_code,
        },
    }


def main() -> None:
    summary: dict[str, Any] = {
        "name": "prompt_tool_archive_api_check",
        "ok": False,
        "steps": {},
        "detail": "",
    }

    stamp = int(time.time())
    prompt_key = f"tmp_prompt_arc_{stamp}"
    persona_key = f"tmp_persona_arc_{stamp}"
    tool_slug = f"tmp_tool_arc_{stamp}"

    try:
        with httpx.Client(base_url=DEV_UI_BASE_URL, timeout=90.0) as http:
            capabilities = http.get("/api/v1/platform/capabilities")
            _require_status(capabilities, allowed=(200,), action="capabilities")
            if not bool(capabilities.json().get("enabled", False)):
                raise RuntimeError("Platform API is not enabled")

            summary["steps"]["prompts_archive_restore_purge"] = _run_prompt_flow(
                http,
                key=prompt_key,
            )
            summary["steps"]["personas_archive_restore_purge"] = _run_persona_flow(
                http,
                key=persona_key,
            )
            summary["steps"]["tools_archive_restore_purge"] = _run_tool_flow(
                http,
                slug=tool_slug,
            )

        summary["ok"] = True
        summary["detail"] = "prompt/persona/tool archive-restore-purge edge checks passed"

    except Exception as exc:
        summary["detail"] = str(exc)
        raise

    finally:
        try:
            with httpx.Client(base_url=DEV_UI_BASE_URL, timeout=30.0) as cleanup_http:
                _cleanup_template(cleanup_http, kind="prompts", key=prompt_key)
                _cleanup_template(cleanup_http, kind="prompts", key=f"{prompt_key}_na")
                _cleanup_template(cleanup_http, kind="personas", key=persona_key)
                _cleanup_template(cleanup_http, kind="personas", key=f"{persona_key}_na")
                _cleanup_tool(cleanup_http, slug=tool_slug)
                _cleanup_tool(cleanup_http, slug=f"{tool_slug}_na")
        except Exception:
            pass

        print(_as_json(summary))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[FAIL] prompt_tool_archive_api_check: {exc}")
        raise
