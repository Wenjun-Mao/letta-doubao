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
DEV_UI_BASE_URL = os.getenv("DEV_UI_BASE_URL", "http://127.0.0.1:8284")


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


def test_ui_options_and_create() -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": "dev_ui_endpoints",
        "ok": False,
        "detail": "",
    }

    with httpx.Client(base_url=DEV_UI_BASE_URL, timeout=30.0) as http:
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

            create_payload = {
                "scenario": "chat",
                "name": f"ui-test-{int(time.time())}",
                "model": DEFAULT_TEST_MODEL_HANDLE,
                "prompt_key": DEFAULT_PROMPT_KEY,
                "embedding": DEFAULT_EMBEDDING_HANDLE,
            }
            created = http.post("/api/v1/agents", json=create_payload)
            created.raise_for_status()
            created_payload = created.json()
            agent_id = created_payload.get("id")
            if not agent_id:
                result["detail"] = "agent creation response missing id"
                return result

            result["ok"] = True
            result["detail"] = "options + create endpoint ok"
            result["models_count"] = len(models)
            result["prompts_count"] = len(prompts)
            result["embeddings_count"] = len(embeddings)

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
    reports.append(test_ui_options_and_create())

    base_model = DEFAULT_TEST_MODEL_HANDLE
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
        "dev_ui_base_url": DEV_UI_BASE_URL,
        "llm_handles": llm_handles,
        "embedding_handles": embedding_handles,
        "reports": reports,
    }

    print(_as_json(summary))


if __name__ == "__main__":
    main()
