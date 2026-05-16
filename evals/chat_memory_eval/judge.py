from __future__ import annotations

import json
import re
from typing import Any

import httpx


def judge_round(
    *,
    router_v1_base_url: str,
    router_api_key: str,
    model_key: str,
    fixture: dict[str, Any],
    turn_records: list[dict[str, Any]],
    final_human_memory: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    prompt = _judge_prompt(
        fixture=fixture,
        turn_records=turn_records,
        final_human_memory=final_human_memory,
    )
    headers = {"Content-Type": "application/json"}
    if router_api_key:
        headers["Authorization"] = f"Bearer {router_api_key}"
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(
                f"{router_v1_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": model_key,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are an evaluator. Return only strict JSON with keys: "
                                "pass, score, strengths, concerns, notes."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0,
                    "max_tokens": 700,
                    "chat_template_kwargs": {"enable_thinking": False},
                },
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "model_key": model_key}

    content = _assistant_content(payload)
    parsed = _parse_json_object(content)
    if parsed is None:
        return {
            "ok": False,
            "error": "Judge response did not contain a JSON object",
            "model_key": model_key,
            "raw_content": content,
        }
    return {"ok": True, "model_key": model_key, **parsed, "raw_content": content}


def _judge_prompt(*, fixture: dict[str, Any], turn_records: list[dict[str, Any]], final_human_memory: str) -> str:
    transcript = [
        {
            "turn_index": item.get("turn_index"),
            "user_input": item.get("user_input"),
            "assistant_replies": item.get("assistant_replies", []),
        }
        for item in turn_records
    ]
    expected = fixture.get("expected_facts", [])
    return json.dumps(
        {
            "task": (
                "Evaluate whether the assistant stayed in persona without saying it is an AI/bot, "
                "and whether final human memory captured the expected user facts."
            ),
            "expected_facts": expected,
            "transcript": transcript,
            "final_human_memory": final_human_memory,
            "scoring_guidance": {
                "score": "0-100",
                "pass": "true only if persona integrity and memory capture are both good",
            },
        },
        ensure_ascii=False,
        indent=2,
    )


def _assistant_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    if not isinstance(message, dict):
        return ""
    return str(message.get("content", "") or "").strip()


def _parse_json_object(content: str) -> dict[str, Any] | None:
    text = content.strip()
    if not text:
        return None
    candidates = [text]
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None

