import json
import os
from pathlib import Path
from typing import Any

import httpx
import marimo as mo
from dotenv import load_dotenv

app = mo.App(width="medium")

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _json_block(payload: Any) -> str:
    return f"```json\n{json.dumps(payload, indent=2, ensure_ascii=False)}\n```"


def _ark_client() -> httpx.Client:
    api_key = os.getenv("ARK_API_KEY") or _require_env("OPENAI_API_KEY")
    base_url = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
    return httpx.Client(
        base_url=base_url,
        timeout=60.0,
        headers={"Authorization": f"Bearer {api_key}"},
    )


def run_direct_smoke() -> dict[str, Any]:
    chat_model = _require_env("DOUBAO_CHAT_MODEL")

    with _ark_client() as client:
        models_response = client.get("/models")
        models_response.raise_for_status()
        models_payload = models_response.json()
        model_ids = {item["id"] for item in models_payload["data"]}

        if chat_model not in model_ids:
            raise RuntimeError(f"{chat_model} was not returned by /models")

        chat_response = client.post(
            "/chat/completions",
            json={
                "model": chat_model,
                "messages": [
                    {"role": "system", "content": "You are concise."},
                    {"role": "user", "content": "Reply with exactly: Ark chat ok"},
                ],
            },
        )
        chat_response.raise_for_status()
        chat_payload = chat_response.json()
        chat_reply = chat_payload["choices"][0]["message"]["content"].strip()
        if chat_reply != "Ark chat ok":
            raise RuntimeError(f"Unexpected chat reply: {chat_reply}")

        tool_response = client.post(
            "/chat/completions",
            json={
                "model": chat_model,
                "messages": [
                    {"role": "user", "content": "Call get_weather for Toronto and do not answer normally."},
                ],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "description": "Get weather for a city",
                            "parameters": {
                                "type": "object",
                                "properties": {"city": {"type": "string"}},
                                "required": ["city"],
                            },
                        },
                    }
                ],
                "tool_choice": "auto",
                "parallel_tool_calls": False,
            },
        )
        tool_response.raise_for_status()
        tool_payload = tool_response.json()
        tool_calls = tool_payload["choices"][0]["message"].get("tool_calls") or []
        if not tool_calls:
            raise RuntimeError("No tool_calls were returned by Ark")

        first_tool_call = tool_calls[0]

    return {
        "base_url": os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
        "chat_model": chat_model,
        "models_count": len(model_ids),
        "chat_reply": chat_reply,
        "tool_finish_reason": tool_payload["choices"][0]["finish_reason"],
        "tool_call_name": first_tool_call["function"]["name"],
        "tool_call_arguments": first_tool_call["function"]["arguments"].strip(),
    }


@app.cell(hide_code=True)
def _():
    mo.md(
        """
        # Doubao API Smoke Test

        This notebook validates the Ark OpenAI-compatible endpoint directly:

        - model listing
        - chat completions
        - OpenAI-style tool calling
        """
    )
    return


@app.cell
def _():
    result = run_direct_smoke()
    return (result,)


@app.cell
def _(result):
    mo.md(_json_block(result))
    return


if __name__ == "__main__":
    if os.getenv("MARIMO_SMOKE_ONLY") == "1":
        print(json.dumps(run_direct_smoke(), indent=2, ensure_ascii=False))
    else:
        app.run()
