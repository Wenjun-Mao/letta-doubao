from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import httpx
from letta_client import Letta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from prompts.persona import HUMAN_TEMPLATE, PERSONAS
from prompts.system_prompts import CUSTOM_V1_PROMPT
from utils.message_parser import chat

LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
DEV_UI_BASE_URL = os.getenv("DEV_UI_BASE_URL", "http://127.0.0.1:8284")


def _target_embeddings() -> list[str]:
    """
    Return embedding handles to test.
    Defaults to a single handle to avoid loading local embedding models into VRAM.
    Override with TEST_EMBEDDING_HANDLES="h1,h2" when needed.
    """
    raw = os.getenv("TEST_EMBEDDING_HANDLES", "letta/letta-free")
    handles = [item.strip() for item in raw.split(",") if item.strip()]
    return handles or ["letta/letta-free"]


def _as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _safe_delete_agent(client: Letta, agent_id: str | None) -> None:
    if not agent_id:
        return
    try:
        client.agents.delete(agent_id=agent_id)
    except Exception:
        pass


def _create_agent(client: Letta, model: str, embedding: str | None, name: str) -> str:
    args: dict[str, Any] = {
        "name": name,
        "system": CUSTOM_V1_PROMPT,
        "model": model,
        "timezone": "Asia/Shanghai",
        "context_window_limit": 16384,
        "memory_blocks": [
            {"label": "persona", "value": PERSONAS["linxiaotang"]},
            {"label": "human", "value": HUMAN_TEMPLATE},
        ],
    }
    if embedding:
        args["embedding"] = embedding
    agent = client.agents.create(**args)
    return agent.id


def test_ui_options_and_create() -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": "dev_ui_endpoints",
        "ok": False,
        "detail": "",
    }

    with httpx.Client(base_url=DEV_UI_BASE_URL, timeout=30.0) as http:
        try:
            options = http.get("/api/options")
            options.raise_for_status()
            payload = options.json()
            models = payload.get("models", [])
            prompts = payload.get("prompts", [])
            embeddings = payload.get("embeddings", [])
            if not models or not prompts:
                result["detail"] = "options endpoint missing models/prompts"
                return result

            create_payload = {
                "name": f"ui-test-{int(time.time())}",
                "model": "lmstudio_openai/qwen3.5-27b",
                "prompt_key": "custom_v1",
                "embedding": "lmstudio_openai/text-embedding-qwen3-embedding-0.6b",
            }
            created = http.post("/api/agents", json=create_payload)
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
        "detail": "",
    }
    agent_id: str | None = None

    try:
        agent_id = _create_agent(
            client=client,
            model=model,
            embedding=embedding,
            name=f"matrix-{int(time.time())}",
        )

        response = chat(client, agent_id, input="你好，我是测试用户")
        report["chat_ok"] = bool(response.get("sequence"))

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


def test_doubao_model_handle(client: Letta) -> dict[str, Any]:
    report: dict[str, Any] = {
        "name": "doubao_handle_model",
        "ok": False,
        "detail": "",
    }
    agent_id: str | None = None

    try:
        agent_id = _create_agent(
            client=client,
            model="openai-proxy/doubao-seed-1-8-251228",
            embedding="lmstudio_openai/text-embedding-qwen3-embedding-0.6b",
            name=f"doubao-handle-{int(time.time())}",
        )
        # If create succeeded, try one message.
        chat(client, agent_id, input="你好")
        report["ok"] = True
        report["detail"] = "doubao handle works in current server"
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

    # 27B-only matrix as requested (no 35B tests).
    base_model = "lmstudio_openai/qwen3.5-27b"
    for embedding in _target_embeddings():
        if embedding in embedding_handles:
            reports.append(test_embedding_combo(client, base_model, embedding))

    reports.append(test_doubao_model_handle(client))

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
