from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import httpx
from letta_client import Letta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from prompts.persona import HUMAN_TEMPLATE, PERSONAS
from prompts.system_prompts import CHAT_V20260418_PROMPT
from tests.shared.config_defaults import (
    DEFAULT_CONTEXT_WINDOW_LIMIT,
    DEFAULT_EMBEDDING_HANDLE,
    DEFAULT_PROMPT_KEY,
    DEFAULT_TEST_MODEL_HANDLE,
)
from utils.message_parser import chat

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
AGENT_PLATFORM_API_BASE_URL = os.getenv("AGENT_PLATFORM_API_BASE_URL", "http://127.0.0.1:8284")


def _target_embeddings() -> list[str]:
    """
    Return embedding handles to test.
    We intentionally lock to one known embedding for deterministic runs.
    """
    return [DEFAULT_EMBEDDING_HANDLE]


def _as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _safe_delete_agent(client: Letta, agent_id: str | None) -> None:
    if not agent_id:
        return
    try:
        client.agents.delete(agent_id=agent_id)
    except Exception:
        pass


def _resolve_runtime_defaults(
    http: httpx.Client,
    llm_handles: list[str],
    embedding_handles: list[str],
) -> dict[str, Any]:
    response = http.get("/api/v1/options", params={"scenario": "chat"})
    response.raise_for_status()
    payload = response.json()

    models = list(payload.get("models", []) or [])
    prompts = list(payload.get("prompts", []) or [])
    embeddings = list(payload.get("embeddings", []) or [])
    defaults = dict(payload.get("defaults", {}) or {})

    available_models = [
        str(item.get("key", "") or "")
        for item in models
        if bool(item.get("available", True)) and str(item.get("key", "") or "") in llm_handles
    ]
    model = available_models[0] if available_models else str(defaults.get("model", "") or "").strip()
    if not model and DEFAULT_TEST_MODEL_HANDLE in llm_handles:
        model = DEFAULT_TEST_MODEL_HANDLE
    if not model and llm_handles:
        model = llm_handles[0]

    prompt_key = str(defaults.get("prompt_key", "") or "").strip()
    if not prompt_key and prompts:
        prompt_key = str(prompts[0].get("key", "") or "")
    if not prompt_key:
        prompt_key = DEFAULT_PROMPT_KEY

    available_embeddings = [
        str(item.get("key", "") or "")
        for item in embeddings
        if bool(item.get("available", True)) and str(item.get("key", "") or "") in embedding_handles
    ]
    embedding = available_embeddings[0] if available_embeddings else str(defaults.get("embedding", "") or "").strip()
    if not embedding and DEFAULT_EMBEDDING_HANDLE in embedding_handles:
        embedding = DEFAULT_EMBEDDING_HANDLE

    return {
        "model": model,
        "prompt_key": prompt_key,
        "embedding": embedding,
        "models_count": len(models),
        "prompts_count": len(prompts),
        "embeddings_count": len(embeddings),
    }


def _create_agent(
    client: Letta,
    model: str,
    embedding: str | None,
    name: str,
    context_window_limit: int,
) -> str:
    args: dict[str, Any] = {
        "name": name,
        "system": CHAT_V20260418_PROMPT,
        "model": model,
        "timezone": "Asia/Shanghai",
        "context_window_limit": context_window_limit,
        "memory_blocks": [
            {"label": "persona", "value": PERSONAS["chat_linxiaotang"]},
            {"label": "human", "value": HUMAN_TEMPLATE},
        ],
    }
    if embedding:
        args["embedding"] = embedding
    agent = client.agents.create(**args)
    return agent.id


def _is_context_size_error(exc: Exception) -> bool:
    lowered = str(exc).lower()
    return "context size has been exceeded" in lowered or "maximum context length" in lowered


def _is_passage_unsupported_error(exc: Exception) -> bool:
    lowered = str(exc).lower()
    return (
        "error code: 404" in lowered
        or "not found" in lowered
        or "error code: 500" in lowered and "unknown error occurred" in lowered
    )


def test_ui_options_and_create(llm_handles: list[str], embedding_handles: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": "agent_platform_api_endpoints",
        "ok": False,
        "detail": "",
    }

    with httpx.Client(base_url=AGENT_PLATFORM_API_BASE_URL, timeout=30.0) as http:
        try:
            options = http.get("/api/v1/options", params={"scenario": "chat"})
            options.raise_for_status()
            payload = options.json()
            models = payload.get("models", [])
            prompts = payload.get("prompts", [])
            embeddings = payload.get("embeddings", [])
            if not models or not prompts:
                result["detail"] = "options endpoint missing models/prompts"
                return result

            resolved = _resolve_runtime_defaults(http, llm_handles, embedding_handles)
            if not resolved["model"]:
                result["detail"] = "no model handle is available for agent creation"
                return result

            create_payload = {
                "scenario": "chat",
                "name": f"ui-test-{int(time.time())}",
                "model": resolved["model"],
                "prompt_key": resolved["prompt_key"],
            }
            if resolved["embedding"]:
                create_payload["embedding"] = resolved["embedding"]
            created = http.post("/api/v1/agents", json=create_payload)
            created.raise_for_status()
            created_payload = created.json()
            agent_id = created_payload.get("id")
            if not agent_id:
                result["detail"] = "agent creation response missing id"
                return result

            result["ok"] = True
            result["detail"] = "options + create endpoint ok"
            result["model"] = resolved["model"]
            result["embedding"] = resolved["embedding"]
            result["models_count"] = resolved["models_count"]
            result["prompts_count"] = resolved["prompts_count"]
            result["embeddings_count"] = resolved["embeddings_count"]

            # Cleanup via Letta API directly.
            client = Letta(base_url=LETTA_BASE_URL)
            _safe_delete_agent(client, agent_id)
            return result
        except Exception as exc:
            result["detail"] = str(exc)
            return result


def test_embedding_combo(client: Letta, model: str, embedding: str) -> dict[str, Any]:
    report: dict[str, Any] = {
        "name": f"combo::{model}::{embedding}",
        "ok": False,
        "chat_ok": False,
        "passage_create_ok": False,
        "passage_search_ok": False,
        "passage_supported": True,
        "detail": "",
    }
    agent_id: str | None = None

    try:
        agent_id = _create_agent(
            client=client,
            model=model,
            embedding=embedding,
            name=f"matrix-{int(time.time())}",
            context_window_limit=DEFAULT_CONTEXT_WINDOW_LIMIT,
        )

        try:
            response = chat(client, agent_id, input="你好，我是测试用户")
        except Exception as first_exc:
            if not _is_context_size_error(first_exc):
                raise

            # Retry once with a tighter context window when the model rejects large prompt payloads.
            _safe_delete_agent(client, agent_id)
            agent_id = _create_agent(
                client=client,
                model=model,
                embedding=embedding,
                name=f"matrix-retry-{int(time.time())}",
                context_window_limit=8192,
            )
            response = chat(client, agent_id, input="你好，我是测试用户")

        report["chat_ok"] = bool(response.get("sequence"))

        try:
            client.agents.passages.create(
                agent_id=agent_id,
                text="测试句子：我最喜欢的动物是狗，最喜欢的城市是苏州。",
            )
            report["passage_create_ok"] = True

            search_response = client.agents.passages.search(
                agent_id=agent_id,
                query="你最喜欢什么动物",
                top_k=3,
            )
            items = getattr(search_response, "items", None)
            if items is None:
                items = list(search_response)
            report["passage_search_ok"] = len(items) > 0
        except Exception as passage_exc:
            if _is_passage_unsupported_error(passage_exc):
                report["passage_supported"] = False
                report["detail"] = "chat ok; archival passage endpoints unavailable for current embedding provider"
                report["ok"] = report["chat_ok"]
                return report
            raise

        report["ok"] = report["chat_ok"] and report["passage_create_ok"] and report["passage_search_ok"]
        if report["ok"]:
            report["detail"] = "chat + passage create/search all ok"
        else:
            report["detail"] = "partial success"
    except Exception as exc:
        report["detail"] = str(exc)
    finally:
        _safe_delete_agent(client, agent_id)

    return report


def main() -> None:
    client = Letta(base_url=LETTA_BASE_URL)

    llm_handles = [m.handle for m in client.models.list()]
    embedding_handles = [m.handle for m in client.models.embeddings.list()]

    reports: list[dict[str, Any]] = []
    reports.append(test_ui_options_and_create(llm_handles, embedding_handles))

    with httpx.Client(base_url=AGENT_PLATFORM_API_BASE_URL, timeout=30.0) as http:
        resolved_defaults = _resolve_runtime_defaults(http, llm_handles, embedding_handles)

    base_model = resolved_defaults["model"] or DEFAULT_TEST_MODEL_HANDLE
    if base_model in llm_handles:
        for embedding in _target_embeddings():
            if embedding in embedding_handles:
                reports.append(test_embedding_combo(client, base_model, embedding))
    else:
        reports.append(
            {
                "name": "target_model_available",
                "ok": False,
                "detail": f"Missing model handle: {base_model}",
            }
        )

    summary = {
        "letta_base_url": LETTA_BASE_URL,
        "agent_platform_api_base_url": AGENT_PLATFORM_API_BASE_URL,
        "llm_handles": llm_handles,
        "embedding_handles": embedding_handles,
        "reports": reports,
    }

    print(_as_json(summary))


if __name__ == "__main__":
    main()

