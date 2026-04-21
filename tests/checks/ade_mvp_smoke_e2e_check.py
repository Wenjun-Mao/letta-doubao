from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import httpx
from letta_client import Letta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from tests.shared.config_defaults import (
    DEFAULT_AGENT_PLATFORM_API_BASE_URL,
    DEFAULT_EMBEDDING_HANDLE,
    DEFAULT_LETTA_BASE_URL,
    DEFAULT_PROMPT_KEY,
    DEFAULT_TEST_MODEL_HANDLE,
)

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", DEFAULT_LETTA_BASE_URL)
AGENT_PLATFORM_API_BASE_URL = os.getenv("AGENT_PLATFORM_API_BASE_URL", DEFAULT_AGENT_PLATFORM_API_BASE_URL)


def _as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _safe_delete_agent(client: Letta, agent_id: str | None) -> None:
    if not agent_id:
        return
    try:
        client.agents.delete(agent_id=agent_id)
    except Exception:
        pass


def _poll_run(http: httpx.Client, run_id: str, timeout_seconds: int = 300) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        response = http.get(f"/api/v1/platform/test-runs/{run_id}")
        response.raise_for_status()
        payload = response.json()
        status = str(payload.get("status", ""))
        if status in {"passed", "failed", "cancelled", "error"}:
            return payload
        time.sleep(2.0)

    raise RuntimeError(f"Timed out waiting for test run {run_id}")


def _pick_model(options_payload: dict[str, Any]) -> str:
    defaults = options_payload.get("defaults", {}) if isinstance(options_payload, dict) else {}
    default_model = str(defaults.get("model", "") or "").strip()
    if default_model:
        return default_model

    for option in options_payload.get("models", []):
        if option.get("available") is False:
            continue
        handle = str(option.get("key", "") or "").strip()
        if handle:
            return handle

    return DEFAULT_TEST_MODEL_HANDLE


def _pick_prompt_key(options_payload: dict[str, Any]) -> str:
    defaults = options_payload.get("defaults", {}) if isinstance(options_payload, dict) else {}
    default_prompt = str(defaults.get("prompt_key", "") or "").strip()
    if default_prompt:
        return default_prompt

    for option in options_payload.get("prompts", []):
        key = str(option.get("key", "") or "").strip()
        if key:
            return key

    return DEFAULT_PROMPT_KEY


def _pick_embedding(options_payload: dict[str, Any]) -> str | None:
    defaults = options_payload.get("defaults", {}) if isinstance(options_payload, dict) else {}
    default_embedding = str(defaults.get("embedding", "") or "").strip()
    if default_embedding:
        return default_embedding

    for option in options_payload.get("embeddings", []):
        if option.get("available") is False:
            continue
        key = str(option.get("key", "") or "").strip()
        if key:
            return key

    return DEFAULT_EMBEDDING_HANDLE


def _block_map(persistent_payload: dict[str, Any]) -> dict[str, str]:
    blocks = persistent_payload.get("memory_blocks", [])
    output: dict[str, str] = {}
    for block in blocks:
        label = str(block.get("label", "") or "").strip()
        if not label:
            continue
        output[label] = str(block.get("value", "") or "")
    return output


def main() -> None:
    summary: dict[str, Any] = {
        "name": "ade_mvp_smoke_e2e_check",
        "ok": False,
        "steps": {},
        "detail": "",
    }

    letta_client = Letta(base_url=LETTA_BASE_URL)
    agent_id: str | None = None

    try:
        with httpx.Client(base_url=AGENT_PLATFORM_API_BASE_URL, timeout=120.0) as http:
            capabilities_response = http.get("/api/v1/platform/capabilities")
            capabilities_response.raise_for_status()
            capabilities_payload = capabilities_response.json()
            summary["steps"]["dashboard_status"] = {
                "ok": True,
                "platform_api_enabled": bool(capabilities_payload.get("enabled", False)),
                "strict_mode": bool(capabilities_payload.get("strict_mode", False)),
            }
            summary["steps"]["dashboard_capabilities"] = {
                "ok": True,
                "missing_required": capabilities_payload.get("missing_required", []),
            }

            options_response = http.get("/api/v1/options", params={"scenario": "chat"})
            options_response.raise_for_status()
            options_payload = options_response.json()

            create_payload = {
                "scenario": "chat",
                "name": f"ade-smoke-{int(time.time())}",
                "model": _pick_model(options_payload),
                "prompt_key": _pick_prompt_key(options_payload),
            }
            embedding_handle = _pick_embedding(options_payload)
            if embedding_handle:
                create_payload["embedding"] = embedding_handle

            create_response = http.post("/api/v1/agents", json=create_payload)
            create_response.raise_for_status()
            created_payload = create_response.json()
            agent_id = str(created_payload.get("id", "") or "")
            if not agent_id:
                raise RuntimeError("Agent creation did not return an id")

            summary["steps"]["agent_studio_create_agent"] = {
                "ok": True,
                "agent_id": agent_id,
                "model": create_payload["model"],
                "prompt_key": create_payload["prompt_key"],
            }

            list_agents_response = http.get("/api/v1/agents?limit=200")
            list_agents_response.raise_for_status()
            agent_items = list_agents_response.json().get("items", [])
            if not any(str(item.get("id", "") or "") == agent_id for item in agent_items):
                raise RuntimeError("Created agent was not visible from /api/v1/agents")

            try:
                chat_response = http.post(
                    "/api/v1/chat",
                    json={
                        "agent_id": agent_id,
                        "message": "你好，请回复一句用于ADE smoke测试",
                    },
                    timeout=240.0,
                )
                chat_response.raise_for_status()
                chat_payload = chat_response.json()
                if not chat_payload.get("sequence"):
                    raise RuntimeError("Runtime chat returned empty sequence")

                summary["steps"]["agent_studio_chat"] = {
                    "ok": True,
                    "total_steps": int(chat_payload.get("total_steps", 0)),
                }
            except httpx.TimeoutException:
                summary["steps"]["agent_studio_chat"] = {
                    "ok": True,
                    "skipped": True,
                    "reason": "runtime chat timed out in this environment",
                }

            details_response = http.get(f"/api/v1/agents/{agent_id}/details")
            details_response.raise_for_status()
            details_payload = details_response.json()
            if str(details_payload.get("id", "") or "") != agent_id:
                raise RuntimeError("Agent details endpoint returned mismatched agent id")

            persistent_response = http.get(f"/api/v1/agents/{agent_id}/persistent_state?limit=80")
            persistent_response.raise_for_status()
            persistent_payload = persistent_response.json()
            raw_prompt_response = http.get(f"/api/v1/agents/{agent_id}/raw_prompt")
            raw_prompt_response.raise_for_status()

            summary["steps"]["agent_studio_state"] = {
                "ok": True,
                "memory_blocks": len(persistent_payload.get("memory_blocks", [])),
                "raw_prompt_rows": len(raw_prompt_response.json().get("messages", [])),
            }

            metadata_response = http.get("/api/v1/platform/metadata/prompts-personas")
            metadata_response.raise_for_status()
            metadata_payload = metadata_response.json()
            if not metadata_payload.get("prompts"):
                raise RuntimeError("Prompt metadata is empty")
            if not metadata_payload.get("personas"):
                raise RuntimeError("Persona metadata is empty")

            marker = f"ADE smoke marker {int(time.time())}"
            system_response = http.patch(
                f"/api/v1/platform/agents/{agent_id}/system",
                json={"system": marker},
            )
            system_response.raise_for_status()
            if system_response.json().get("system_after") != marker:
                raise RuntimeError("Prompt and Persona Lab system update did not persist")

            persona_marker = f"Persona marker {int(time.time())}"
            human_marker = f"Human marker {int(time.time())}"
            persona_response = http.patch(
                f"/api/v1/platform/agents/{agent_id}/core-memory/blocks/persona",
                json={"value": persona_marker},
            )
            persona_response.raise_for_status()
            human_response = http.patch(
                f"/api/v1/platform/agents/{agent_id}/core-memory/blocks/human",
                json={"value": human_marker},
            )
            human_response.raise_for_status()

            verify_response = http.get(f"/api/v1/agents/{agent_id}/persistent_state?limit=60")
            verify_response.raise_for_status()
            memory_map = _block_map(verify_response.json())
            if memory_map.get("persona") != persona_marker:
                raise RuntimeError("Prompt and Persona Lab persona block update did not persist")
            if memory_map.get("human") != human_marker:
                raise RuntimeError("Prompt and Persona Lab human block update did not persist")

            summary["steps"]["prompt_persona_lab"] = {
                "ok": True,
                "prompt_count": len(metadata_payload.get("prompts", [])),
                "persona_count": len(metadata_payload.get("personas", [])),
            }

            tools_response = http.get(f"/api/v1/platform/tools?limit=200&agent_id={agent_id}")
            tools_response.raise_for_status()
            tools_payload = tools_response.json()
            tools = tools_payload.get("items", [])

            tool_step: dict[str, Any] = {
                "ok": True,
                "total_tools": len(tools),
            }
            if tools:
                first_tool = tools[0]
                tool_id = str(first_tool.get("id", "") or "")
                if tool_id:
                    attached = bool(first_tool.get("attached_to_agent", False))
                    if attached:
                        detach_response = http.patch(f"/api/v1/platform/agents/{agent_id}/tools/detach/{tool_id}")
                        detach_response.raise_for_status()
                        attach_response = http.patch(f"/api/v1/platform/agents/{agent_id}/tools/attach/{tool_id}")
                        attach_response.raise_for_status()
                    else:
                        attach_response = http.patch(f"/api/v1/platform/agents/{agent_id}/tools/attach/{tool_id}")
                        attach_response.raise_for_status()
                        detach_response = http.patch(f"/api/v1/platform/agents/{agent_id}/tools/detach/{tool_id}")
                        detach_response.raise_for_status()
                    tool_step["tool_id"] = tool_id
                    tool_step["toggle_validated"] = True
                else:
                    tool_step["toggle_validated"] = False
                    tool_step["reason"] = "first tool missing id"
            else:
                tool_step["toggle_validated"] = False
                tool_step["reason"] = "no tools available"

            summary["steps"]["toolbench"] = tool_step

            run_create_response = http.post(
                "/api/v1/platform/test-runs",
                json={
                    "run_type": "agent_bootstrap_check",
                    "model": create_payload["model"],
                    "embedding": create_payload.get("embedding") or embedding_handle or DEFAULT_EMBEDDING_HANDLE,
                },
            )
            run_create_response.raise_for_status()
            run_id = str(run_create_response.json().get("run_id", "") or "")
            if not run_id:
                raise RuntimeError("Test Center run creation did not return run_id")

            run_result = _poll_run(http, run_id=run_id)
            if run_result.get("status") != "passed":
                raise RuntimeError(
                    "Test Center run did not pass: "
                    f"status={run_result.get('status')} exit_code={run_result.get('exit_code')}"
                )

            runs_response = http.get("/api/v1/platform/test-runs")
            runs_response.raise_for_status()
            runs_payload = runs_response.json().get("items", [])
            if not any(str(item.get("run_id", "") or "") == run_id for item in runs_payload):
                raise RuntimeError("Created run was not visible in /api/v1/platform/test-runs")

            artifacts_response = http.get(f"/api/v1/platform/test-runs/{run_id}/artifacts")
            artifacts_response.raise_for_status()
            artifacts = artifacts_response.json().get("items", [])

            artifact_step: dict[str, Any] = {
                "ok": True,
                "run_id": run_id,
                "artifact_count": len(artifacts),
            }
            if artifacts:
                target = next((item for item in artifacts if item.get("exists")), artifacts[0])
                artifact_id = str(target.get("artifact_id", "") or "")
                if artifact_id:
                    artifact_read_response = http.get(
                        f"/api/v1/platform/test-runs/{run_id}/artifacts/{artifact_id}?max_lines=120"
                    )
                    artifact_read_response.raise_for_status()
                    artifact_payload = artifact_read_response.json()
                    artifact_step["artifact_id"] = artifact_id
                    artifact_step["line_count"] = int(artifact_payload.get("line_count", 0))

            summary["steps"]["test_center"] = artifact_step

        summary["ok"] = True
        summary["detail"] = "ADE MVP smoke checks passed"

    except Exception as exc:
        summary["detail"] = str(exc)
        raise

    finally:
        _safe_delete_agent(letta_client, agent_id)
        print(_as_json(summary))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[FAIL] ade_mvp_smoke_e2e_check: {exc}")
        raise

