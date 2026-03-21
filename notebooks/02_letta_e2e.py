import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
import marimo as mo
from dotenv import load_dotenv
from letta_client import Letta

app = mo.App(width="medium")

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _to_json(payload: Any, *, indent: int | None = None) -> str:
    return json.dumps(payload, indent=indent, ensure_ascii=False, default=str)


def _json_block(payload: Any) -> str:
    return f"```json\n{_to_json(payload, indent=2)}\n```"


def _wait_for_server(base_url: str, timeout_seconds: int = 180) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    model_handle = _require_env("LETTA_MODEL_HANDLE")
    embedding_handle = _require_env("LETTA_EMBEDDING_HANDLE")
    deadline = time.time() + timeout_seconds
    last_error: str | None = None

    while time.time() < deadline:
        try:
            with httpx.Client(base_url=base_url.rstrip("/"), timeout=20.0, follow_redirects=True) as client:
                llm_models_response = client.get("/v1/models/")
                llm_models_response.raise_for_status()
                llm_models = llm_models_response.json()

                embedding_models_response = client.get("/v1/models/embedding")
                embedding_models_response.raise_for_status()
                embedding_models = embedding_models_response.json()

            llm_handles = {item["handle"] for item in llm_models}
            embedding_handles = {item["handle"] for item in embedding_models}

            if model_handle in llm_handles and embedding_handle in embedding_handles:
                return llm_models, embedding_models
        except Exception as exc:
            last_error = str(exc)

        time.sleep(3)

    raise RuntimeError(
        "Letta server did not become ready with the expected model handles. "
        f"Last error: {last_error or 'n/a'}"
    )


def _message_payload(message: Any) -> Any:
    if hasattr(message, "model_dump"):
        return message.model_dump(exclude_none=True)
    if hasattr(message, "dict"):
        return message.dict()
    return str(message)


def run_letta_e2e() -> dict[str, Any]:
    base_url = os.getenv("LETTA_BASE_URL", "http://localhost:8283").rstrip("/")
    model_handle = _require_env("LETTA_MODEL_HANDLE")
    embedding_handle = _require_env("LETTA_EMBEDDING_HANDLE")

    llm_models, embedding_models = _wait_for_server(base_url=base_url)
    client = Letta(base_url=base_url)

    agent = client.agents.create(
        name=f"doubao-e2e-{int(time.time())}",
        model=model_handle,
        embedding=embedding_handle,
        memory_blocks=[
            {"label": "persona", "value": "You answer exactly and concisely."},
            {"label": "human", "value": "The user is validating a Letta stack backed by Doubao."},
        ],
    )

    response = client.agents.messages.create(
        agent_id=agent.id,
        input="In your final answer include the exact text 'Letta via Doubao ok'.",
    )
    response_messages = [_message_payload(message) for message in response.messages]
    rendered_messages = _to_json(response_messages)

    if "Letta via Doubao ok" not in rendered_messages:
        raise RuntimeError("The Letta response did not include the expected confirmation text")

    return {
        "base_url": base_url,
        "agent_id": agent.id,
        "model_handle": model_handle,
        "embedding_handle": embedding_handle,
        "llm_model_found": any(model["handle"] == model_handle for model in llm_models),
        "embedding_model_found": any(model["handle"] == embedding_handle for model in embedding_models),
        "response_messages": response_messages,
    }


@app.cell(hide_code=True)
def _():
    mo.md(
        """
        # Letta End-to-End Smoke Test

        This notebook validates the running docker-compose stack:

        - Letta server startup
        - Doubao-backed model discovery inside Letta
        - agent creation
        - message execution through Letta using the Doubao-backed model
        """
    )
    return


@app.cell
def _():
    result = run_letta_e2e()
    return (result,)


@app.cell
def _(result):
    mo.md(_json_block(result))
    return


if __name__ == "__main__":
    if os.getenv("MARIMO_SMOKE_ONLY") == "1":
        print(_to_json(run_letta_e2e(), indent=2))
    else:
        app.run()
