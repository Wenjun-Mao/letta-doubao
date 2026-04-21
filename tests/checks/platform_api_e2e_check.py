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
    DEFAULT_EMBEDDING_HANDLE,
    DEFAULT_PROMPT_KEY,
    DEFAULT_TEST_MODEL_HANDLE,
)

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
AGENT_PLATFORM_API_BASE_URL = os.getenv("AGENT_PLATFORM_API_BASE_URL", "http://127.0.0.1:8284")
AGENT_PLATFORM_API_CLIENT_TIMEOUT_SECONDS = float(os.getenv("AGENT_PLATFORM_API_CLIENT_TIMEOUT_SECONDS", "180"))


def _as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _safe_delete_agent(client: Letta, agent_id: str | None) -> None:
    if not agent_id:
        return
    try:
        client.agents.delete(agent_id=agent_id)
    except Exception:
        pass


def _poll_run(http: httpx.Client, run_id: str, timeout_seconds: int = 240) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        response = http.get(f"/api/v1/platform/test-runs/{run_id}")
        response.raise_for_status()
        payload = response.json()
        status = payload.get("status")
        if status in {"passed", "failed", "cancelled", "error"}:
            return payload
        time.sleep(2.0)

    raise RuntimeError(f"Timed out waiting for test run {run_id}")


def _resolve_runtime_defaults(http: httpx.Client) -> dict[str, str]:
    response = http.get("/api/v1/options", params={"scenario": "chat"})
    response.raise_for_status()
    payload = response.json()

    models = list(payload.get("models", []) or [])
    embeddings = list(payload.get("embeddings", []) or [])
    prompts = list(payload.get("prompts", []) or [])
    personas = list(payload.get("personas", []) or [])
    defaults = dict(payload.get("defaults", {}) or {})

    model = str(defaults.get("model", "") or "").strip()
    if not model:
        available_models = [str(item.get("key", "") or "") for item in models if bool(item.get("available", True))]
        model = available_models[0] if available_models else str(models[0].get("key", "") or "")
    if not model:
        model = DEFAULT_TEST_MODEL_HANDLE

    prompt_key = str(defaults.get("prompt_key", "") or "").strip()
    if not prompt_key and prompts:
        prompt_key = str(prompts[0].get("key", "") or "")
    if not prompt_key:
        prompt_key = DEFAULT_PROMPT_KEY

    persona_key = str(defaults.get("persona_key", "") or "").strip()
    if not persona_key and personas:
        persona_key = str(personas[0].get("key", "") or "")

    embedding = str(defaults.get("embedding", "") or "").strip()
    if not embedding:
        available_embeddings = [str(item.get("key", "") or "") for item in embeddings if bool(item.get("available", True))]
        embedding = available_embeddings[0] if available_embeddings else ""
    if not embedding and any(str(item.get("key", "") or "") == DEFAULT_EMBEDDING_HANDLE for item in embeddings):
        embedding = DEFAULT_EMBEDDING_HANDLE

    return {
        "scenario": "chat",
        "model": model,
        "prompt_key": prompt_key,
        "persona_key": persona_key,
        "embedding": embedding,
    }


def main() -> None:
    summary: dict[str, Any] = {
        "name": "platform_api_e2e_check",
        "ok": False,
        "steps": {},
        "detail": "",
    }

    letta_client = Letta(base_url=LETTA_BASE_URL)
    agent_id: str | None = None

    try:
        with httpx.Client(base_url=AGENT_PLATFORM_API_BASE_URL, timeout=AGENT_PLATFORM_API_CLIENT_TIMEOUT_SECONDS) as http:
            capabilities_response = http.get("/api/v1/platform/capabilities")
            capabilities_response.raise_for_status()
            capabilities = capabilities_response.json()
            summary["steps"]["capabilities"] = {
                "ok": True,
                "missing_required": capabilities.get("missing_required", []),
                "runtime": capabilities.get("runtime", {}),
                "control": capabilities.get("control", {}),
            }

            runtime_defaults = _resolve_runtime_defaults(http)
            resolved_model = str(runtime_defaults.get("model", "") or DEFAULT_TEST_MODEL_HANDLE)
            resolved_prompt_key = str(runtime_defaults.get("prompt_key", "") or DEFAULT_PROMPT_KEY)
            resolved_persona_key = str(runtime_defaults.get("persona_key", "") or "")
            resolved_embedding = str(runtime_defaults.get("embedding", "") or "")

            create_payload = {
                "scenario": "chat",
                "name": f"platform-e2e-{int(time.time())}",
                "model": resolved_model,
                "prompt_key": resolved_prompt_key,
                "persona_key": resolved_persona_key,
            }
            if resolved_embedding:
                create_payload["embedding"] = resolved_embedding

            guard_payload = {
                "scenario": "comment",
                "name": f"platform-e2e-guard-{int(time.time())}",
                "model": resolved_model,
                "prompt_key": resolved_prompt_key,
                "persona_key": resolved_persona_key,
            }
            if resolved_embedding:
                guard_payload["embedding"] = resolved_embedding
            scenario_guard = http.post("/api/v1/agents", json=guard_payload)
            if scenario_guard.status_code != 400:
                raise RuntimeError(
                    "Expected /api/v1/agents to reject non-chat scenario, "
                    f"got status={scenario_guard.status_code}"
                )
            summary["steps"]["scenario_guard"] = {
                "ok": True,
                "status": scenario_guard.status_code,
            }

            create_response = http.post("/api/v1/agents", json=create_payload)
            create_response.raise_for_status()
            created = create_response.json()
            agent_id = str(created.get("id", "") or "")
            if not agent_id:
                raise RuntimeError("Agent creation did not return an id")

            summary["steps"]["create_agent"] = {
                "ok": True,
                "agent_id": agent_id,
            }

            message_response = http.post(
                f"/api/v1/platform/agents/{agent_id}/messages",
                json={"input": "你好，我是平台接口E2E测试"},
            )
            message_response.raise_for_status()
            message_payload = message_response.json()
            sequence = message_payload.get("result", {}).get("sequence", [])
            if not sequence:
                raise RuntimeError("Platform runtime message returned an empty sequence")
            summary["steps"]["runtime_message"] = {
                "ok": True,
                "total_steps": int(message_payload.get("result", {}).get("total_steps", 0)),
            }

            tool_probe_response = http.post(
                "/api/v1/platform/tools/test-invoke",
                json={
                    "agent_id": agent_id,
                    "input": "请判断是否需要调用工具，然后返回简短回答。",
                },
            )
            tool_probe_response.raise_for_status()
            tool_probe_payload = tool_probe_response.json()
            summary["steps"]["tool_test_invoke"] = {
                "ok": True,
                "tool_call_count": int(tool_probe_payload.get("tool_call_count", 0)),
                "tool_return_count": int(tool_probe_payload.get("tool_return_count", 0)),
            }

            system_text = f"E2E system update at {int(time.time())}"
            system_response = http.patch(
                f"/api/v1/platform/agents/{agent_id}/system",
                json={"system": system_text},
            )
            system_response.raise_for_status()
            system_payload = system_response.json()
            if system_payload.get("system_after") != system_text:
                raise RuntimeError("System prompt update did not persist expected value")
            summary["steps"]["update_system"] = {
                "ok": True,
            }

            model_response = http.patch(
                f"/api/v1/platform/agents/{agent_id}/model",
                json={"model": resolved_model},
            )
            model_response.raise_for_status()
            summary["steps"]["update_model"] = {
                "ok": True,
                "model_after": model_response.json().get("model_after", ""),
            }

            human_value = "姓名：平台E2E用户\n偏好：测试Agent Platform API"
            block_response = http.patch(
                f"/api/v1/platform/agents/{agent_id}/core-memory/blocks/human",
                json={"value": human_value},
            )
            block_response.raise_for_status()
            block_payload = block_response.json()
            if block_payload.get("value_after") != human_value:
                raise RuntimeError("Core-memory block update did not persist expected value")
            summary["steps"]["update_core_memory_block"] = {
                "ok": True,
            }

            revisions_response = http.get(
                "/api/v1/platform/metadata/prompts-personas/revisions",
                params={"agent_id": agent_id, "limit": 40},
            )
            revisions_response.raise_for_status()
            revisions_payload = revisions_response.json()
            revision_items = revisions_payload.get("items", [])
            if not revision_items:
                raise RuntimeError("Prompt/persona revision history returned no records")

            revision_fields = {str(item.get("field", "") or "") for item in revision_items}
            if "system" not in revision_fields or "human" not in revision_fields:
                raise RuntimeError(
                    "Prompt/persona revision history is missing expected fields "
                    f"(found={sorted(revision_fields)})"
                )

            summary["steps"]["prompt_persona_revisions"] = {
                "ok": True,
                "total": int(revisions_payload.get("total", 0)),
                "fields": sorted(revision_fields),
            }

            attached_tools = list(letta_client.agents.tools.list(agent_id=agent_id))
            if attached_tools:
                tool_id = str(getattr(attached_tools[0], "id", "") or "")
                if tool_id:
                    detach_response = http.patch(f"/api/v1/platform/agents/{agent_id}/tools/detach/{tool_id}")
                    detach_response.raise_for_status()

                    attach_response = http.patch(f"/api/v1/platform/agents/{agent_id}/tools/attach/{tool_id}")
                    attach_response.raise_for_status()

                    summary["steps"]["tool_attach_detach"] = {
                        "ok": True,
                        "tool_id": tool_id,
                    }
                else:
                    summary["steps"]["tool_attach_detach"] = {
                        "ok": True,
                        "skipped": True,
                        "reason": "first attached tool had no id",
                    }
            else:
                summary["steps"]["tool_attach_detach"] = {
                    "ok": True,
                    "skipped": True,
                    "reason": "agent has no attached tools",
                }

            orchestrator_response = http.post(
                "/api/v1/platform/test-runs",
                json={
                    "run_type": "agent_bootstrap_check",
                    "model": resolved_model,
                    "embedding": resolved_embedding,
                },
            )
            orchestrator_response.raise_for_status()
            run_id = str(orchestrator_response.json().get("run_id", "") or "")
            if not run_id:
                raise RuntimeError("Platform test-orchestrator did not return run_id")

            run_result = _poll_run(http, run_id=run_id)
            if run_result.get("status") != "passed":
                raise RuntimeError(
                    "Orchestrated test run failed: "
                    f"status={run_result.get('status')} exit_code={run_result.get('exit_code')}"
                )

            summary["steps"]["orchestrator"] = {
                "ok": True,
                "run_id": run_id,
                "status": run_result.get("status"),
            }

        summary["ok"] = True
        summary["detail"] = "all platform API checks passed"

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
        print(f"[FAIL] platform_api_e2e_check: {exc}")
        raise

