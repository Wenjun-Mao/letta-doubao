from __future__ import annotations

import json
import re
from typing import Any

import httpx
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential


class RetryableLabelingProviderError(RuntimeError):
    """Raised for provider responses that should be retried."""


_VERSION_PATH_RE = re.compile(r"/v\d+(?:\.\d+)?$", re.IGNORECASE)
_MODEL_HANDLE_PREFIXES = (
    "lmstudio_openai/",
    "openai-proxy/",
    "openai/",
    "anthropic/",
)
_RETRYABLE_LABELING_EXCEPTIONS = (
    RetryableLabelingProviderError,
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.RemoteProtocolError,
    httpx.WriteError,
)


def chat_completions_url(base_url: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if _VERSION_PATH_RE.search(base):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def resolve_provider_model(model: str) -> str:
    resolved_model = str(model or "").strip()
    lowered_model = resolved_model.lower()
    for prefix in _MODEL_HANDLE_PREFIXES:
        if lowered_model.startswith(prefix):
            return resolved_model[len(prefix) :].strip()
    return resolved_model


def parse_sse_chat_completion_response(raw_text: str) -> dict[str, Any] | None:
    text = str(raw_text or "").strip()
    if not text or "data:" not in text:
        return None

    chunks: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("data:"):
            continue
        data_text = stripped[5:].strip()
        if not data_text or data_text == "[DONE]":
            continue
        try:
            parsed = json.loads(data_text)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            chunks.append(parsed)

    if not chunks:
        return None

    choices_by_index: dict[int, dict[str, Any]] = {}
    result: dict[str, Any] = {
        "id": "",
        "object": "chat.completion",
        "created": 0,
        "model": "",
        "choices": [],
        "usage": {},
    }

    for chunk in chunks:
        result["id"] = str(chunk.get("id") or result["id"] or "")
        result["object"] = str(chunk.get("object") or result["object"] or "chat.completion")
        result["created"] = int(chunk.get("created") or result["created"] or 0)
        result["model"] = str(chunk.get("model") or result["model"] or "")

        usage = chunk.get("usage")
        if isinstance(usage, dict) and usage:
            result["usage"] = usage

        raw_choices = chunk.get("choices")
        if not isinstance(raw_choices, list):
            continue

        for raw_choice in raw_choices:
            if not isinstance(raw_choice, dict):
                continue
            index = int(raw_choice.get("index") or 0)
            choice_state = choices_by_index.setdefault(
                index,
                {
                    "index": index,
                    "message": {"role": "assistant", "content": "", "reasoning_content": ""},
                    "finish_reason": None,
                },
            )
            message = choice_state["message"]
            delta = raw_choice.get("delta")
            if isinstance(delta, dict):
                role = str(delta.get("role") or "").strip()
                if role:
                    message["role"] = role
                for field in ("content", "reasoning_content"):
                    chunk_value = delta.get(field)
                    if chunk_value is None:
                        continue
                    message[field] = f"{message.get(field, '')}{chunk_value}"

            finish_reason = raw_choice.get("finish_reason")
            if finish_reason is not None:
                choice_state["finish_reason"] = finish_reason

    result["choices"] = [choices_by_index[index] for index in sorted(choices_by_index)]
    if not result["choices"]:
        return None
    return result


class LabelingProviderClient:
    def _build_retrying(self) -> Retrying:
        return Retrying(
            stop=stop_after_attempt(2),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type(_RETRYABLE_LABELING_EXCEPTIONS),
            reraise=True,
        )

    def _post_chat_completions_once(
        self,
        payload: dict[str, Any],
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        with httpx.Client(timeout=timeout_seconds) as session:
            response = session.post(chat_completions_url(base_url), json=payload, headers=headers)

        if response.status_code >= 500 or response.status_code == 429:
            raise RetryableLabelingProviderError(
                f"Label provider temporary failure ({response.status_code}): {response.text}"
            )
        if response.status_code >= 400:
            raise ValueError(f"Label provider request failed ({response.status_code}): {response.text}")

        try:
            data = response.json()
        except Exception:
            data = parse_sse_chat_completion_response(response.text)
            if data is None:
                raise ValueError(f"Label provider returned non-JSON response: {response.text}")

        if not isinstance(data, dict):
            raise ValueError("Label provider returned invalid payload")
        return data

    def post_chat_completions(
        self,
        payload: dict[str, Any],
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        retrying = self._build_retrying()
        for attempt in retrying:
            with attempt:
                return self._post_chat_completions_once(
                    payload,
                    base_url=base_url,
                    api_key=api_key,
                    timeout_seconds=timeout_seconds,
                )
        raise RuntimeError("Label provider retry execution did not produce a result")
