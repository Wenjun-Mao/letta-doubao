from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from agent_platform_api.settings import get_settings
from agent_platform_api.services.commenting_helpers import (
    build_all_in_system_prompt,
    build_classic_user_payload,
    build_structured_system_prompt,
    extract_comment_from_reasoning,
    extract_structured_comment,
    is_publishable_comment,
    normalize_content,
    sanitize_comment,
    structured_response_format,
)


class _RetryableCommentingError(RuntimeError):
    """Raised for provider responses that should be retried."""


DEFAULT_COMMENTING_RETRY_COUNT = 0
MAX_COMMENTING_RETRY_COUNT = 5
DEFAULT_COMMENTING_CACHE_PROMPT = False
DEFAULT_COMMENTING_TEMPERATURE = 0.6
DEFAULT_COMMENTING_TOP_P = 1.0
_RETRYABLE_COMMENTING_EXCEPTIONS = (
    _RetryableCommentingError,
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.RemoteProtocolError,
    httpx.WriteError,
)
_VERSION_PATH_RE = re.compile(r"/v\d+(?:\.\d+)?$", re.IGNORECASE)


class CommentingService:
    """Stateless comment generation through an OpenAI-compatible chat completions API."""

    _MODEL_HANDLE_PREFIXES = (
        "lmstudio_openai/",
        "openai-proxy/",
        "openai/",
        "anthropic/",
    )
    _TASK_SHAPES = {"classic", "all_in_system", "structured_output"}

    def __init__(self, *, settings_factory=get_settings):
        self._settings_factory = settings_factory

    @staticmethod
    def _clamp_max_tokens(value: int) -> int:
        if int(value) <= 0:
            # `0` is treated as "no max_tokens parameter" for provider requests.
            return 0
        return max(64, min(8192, int(value)))

    @staticmethod
    def _clamp_timeout_seconds(value: float) -> float:
        return max(5.0, min(600.0, float(value)))

    @staticmethod
    def _clamp_retry_count(value: int | None) -> int:
        if value is None:
            return DEFAULT_COMMENTING_RETRY_COUNT
        return max(0, min(MAX_COMMENTING_RETRY_COUNT, int(value)))

    @staticmethod
    def _clamp_temperature(value: float | None) -> float:
        return DEFAULT_COMMENTING_TEMPERATURE if value is None else max(0.0, min(2.0, float(value)))

    @staticmethod
    def _clamp_top_p(value: float | None) -> float:
        return DEFAULT_COMMENTING_TOP_P if value is None else max(0.01, min(1.0, float(value)))

    @staticmethod
    def _is_llama_cpp_adapter(source_adapter: str | None) -> bool:
        return str(source_adapter or "").strip().lower() == "llama_cpp_server"

    @classmethod
    def _resolve_task_shape(cls, value: str | None) -> str:
        resolved = str(value or "").strip().lower()
        if not resolved:
            return "classic"
        if resolved in cls._TASK_SHAPES:
            return resolved
        raise ValueError(f"Unsupported task_shape: {resolved}")

    def runtime_defaults(self) -> dict[str, Any]:
        settings = self._settings_factory()
        return {
            "max_tokens": self._clamp_max_tokens(settings.commenting_max_tokens),
            "timeout_seconds": self._clamp_timeout_seconds(settings.commenting_timeout_seconds),
            "task_shape": self._resolve_task_shape(settings.commenting_task_shape),
            "cache_prompt": bool(settings.commenting_cache_prompt),
            "temperature": self._clamp_temperature(settings.commenting_temperature),
            "top_p": self._clamp_top_p(settings.commenting_top_p),
        }

    @staticmethod
    def _chat_completions_url(base_url: str) -> str:
        base = str(base_url or "").strip().rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        if _VERSION_PATH_RE.search(base):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    @classmethod
    def _resolve_provider_model(cls, model: str) -> str:
        resolved_model = model.strip()
        lowered_model = resolved_model.lower()
        for prefix in cls._MODEL_HANDLE_PREFIXES:
            if lowered_model.startswith(prefix):
                return resolved_model[len(prefix):].strip()
        return resolved_model

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
            response = session.post(self._chat_completions_url(base_url), json=payload, headers=headers)

        if response.status_code >= 500 or response.status_code == 429:
            raise _RetryableCommentingError(
                f"Comment provider temporary failure ({response.status_code}): {response.text}"
            )
        if response.status_code >= 400:
            raise ValueError(f"Comment provider request failed ({response.status_code}): {response.text}")

        try:
            data = response.json()
        except Exception:
            data = self._parse_sse_chat_completion_response(response.text)
            if data is None:  # pragma: no cover
                raise ValueError(f"Comment provider returned non-JSON response: {response.text}")

        if not isinstance(data, dict):
            raise ValueError("Comment provider returned invalid payload")
        return data

    def _post_chat_completions(
        self,
        payload: dict[str, Any],
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float,
        retry_count: int,
    ) -> dict[str, Any]:
        retrying = self._build_retrying(retry_count)
        for attempt in retrying:
            with attempt:
                return self._post_chat_completions_once(
                    payload,
                    base_url=base_url,
                    api_key=api_key,
                    timeout_seconds=timeout_seconds,
                )
        raise RuntimeError("Comment provider retry execution did not produce a result")

    def _build_retrying(self, retry_count: int) -> Retrying:
        return Retrying(
            stop=stop_after_attempt(1 + self._clamp_retry_count(retry_count)),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type(_RETRYABLE_COMMENTING_EXCEPTIONS),
            reraise=True,
        )

    @staticmethod
    def _generation_result(
        *,
        content: str,
        content_source: str,
        selected_attempt: str,
        finish_reason: str,
        data: dict[str, Any],
        payload: dict[str, Any],
        runtime: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "content": content,
            "content_source": content_source,
            "selected_attempt": selected_attempt,
            "finish_reason": finish_reason,
            "usage": data.get("usage", {}) if isinstance(data.get("usage", {}), dict) else {},
            "received_at": datetime.now(timezone.utc).isoformat(),
            "raw_request": payload,
            "raw_reply": data,
            **runtime,
        }

    def generate_comment(
        self,
        *,
        base_url: str,
        api_key: str = "",
        model: str,
        system_prompt: str,
        persona_prompt: str,
        news_input: str,
        max_tokens: int | None = None,
        timeout_seconds: float | None = None,
        retry_count: int | None = None,
        task_shape: str | None = None,
        source_adapter: str | None = None,
        cache_prompt: bool | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> dict[str, Any]:
        resolved_base_url = str(base_url or "").strip()
        if not resolved_base_url:
            raise ValueError("base_url is required")

        resolved_model = self._resolve_provider_model(str(model or ""))
        if not resolved_model:
            raise ValueError("model is required")

        runtime_defaults = self.runtime_defaults()
        resolved_max_tokens = runtime_defaults["max_tokens"] if max_tokens is None else self._clamp_max_tokens(max_tokens)
        resolved_timeout_seconds = (
            runtime_defaults["timeout_seconds"]
            if timeout_seconds is None
            else self._clamp_timeout_seconds(timeout_seconds)
        )
        resolved_retry_count = self._clamp_retry_count(retry_count)
        resolved_task_shape = runtime_defaults["task_shape"] if task_shape is None else self._resolve_task_shape(task_shape)
        resolved_cache_prompt = bool(runtime_defaults["cache_prompt"]) if cache_prompt is None else bool(cache_prompt)
        resolved_temperature = float(runtime_defaults["temperature"]) if temperature is None else self._clamp_temperature(temperature)
        resolved_top_p = float(runtime_defaults["top_p"]) if top_p is None else self._clamp_top_p(top_p)
        response_runtime = {
            "max_tokens": resolved_max_tokens,
            "timeout_seconds": resolved_timeout_seconds,
            "task_shape": resolved_task_shape,
            "cache_prompt": resolved_cache_prompt,
            "temperature": resolved_temperature,
            "top_p": resolved_top_p,
        }

        classic_payload = {
            "model": resolved_model,
            "messages": [
                {"role": "system", "content": str(system_prompt or "")},
                {
                    "role": "user",
                    "content": build_classic_user_payload(
                        persona_prompt=persona_prompt,
                        news_input=news_input,
                    ),
                },
            ],
            "temperature": resolved_temperature,
            "top_p": resolved_top_p,
            "max_tokens": resolved_max_tokens,
        }

        all_in_system_payload = {
            "model": resolved_model,
            "messages": [
                {
                    "role": "system",
                    "content": build_all_in_system_prompt(
                        system_prompt=system_prompt,
                        persona_prompt=persona_prompt,
                    ),
                },
                {"role": "user", "content": str(news_input or "").strip()},
            ],
            "temperature": resolved_temperature,
            "top_p": resolved_top_p,
            "max_tokens": resolved_max_tokens,
        }

        structured_output_payload = {
            "model": resolved_model,
            "messages": [
                {
                    "role": "system",
                    "content": build_structured_system_prompt(
                        system_prompt=system_prompt,
                        persona_prompt=persona_prompt,
                    ),
                },
                {"role": "user", "content": str(news_input or "").strip()},
            ],
            "temperature": resolved_temperature,
            "top_p": resolved_top_p,
            "max_tokens": resolved_max_tokens,
            "response_format": structured_response_format(),
        }

        payload_by_shape: dict[str, dict[str, Any]] = {
            "classic": classic_payload,
            "all_in_system": all_in_system_payload,
            "structured_output": structured_output_payload,
        }

        payload = payload_by_shape.get(resolved_task_shape, classic_payload)

        if resolved_max_tokens == 0:
            payload.pop("max_tokens", None)
        if self._is_llama_cpp_adapter(source_adapter):
            payload["cache_prompt"] = resolved_cache_prompt

        try:
            data = self._post_chat_completions(
                payload,
                base_url=resolved_base_url,
                api_key=str(api_key or "").strip(),
                timeout_seconds=resolved_timeout_seconds,
                retry_count=resolved_retry_count,
            )
        except ValueError as exc:
            # Some OpenAI-compatible runtimes reject `response_format` when strict
            # structured decoding is disabled. Fall back to prompt-enforced JSON.
            if resolved_task_shape != "structured_output":
                raise

            error_text = str(exc).lower()
            if "response_format" not in error_text and "json_schema" not in error_text:
                raise

            payload = dict(payload)
            payload.pop("response_format", None)
            data = self._post_chat_completions(
                payload,
                base_url=resolved_base_url,
                api_key=str(api_key or "").strip(),
                timeout_seconds=resolved_timeout_seconds,
                retry_count=resolved_retry_count,
            )

        choices = data.get("choices", [])
        if not isinstance(choices, list) or not choices:
            raise ValueError(
                f"Comment provider returned no choices; task_shape={resolved_task_shape}; max_tokens={resolved_max_tokens}"
            )

        message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        finish_reason = str(choices[0].get("finish_reason", "") or "").strip().lower() if isinstance(choices[0], dict) else ""
        content = normalize_content(message.get("content", ""))
        reasoning = normalize_content(message.get("reasoning_content", ""))

        if resolved_task_shape == "structured_output":
            content = extract_structured_comment(content)
            if not content:
                reasoning_structured = extract_structured_comment(reasoning)
                if reasoning_structured:
                    cleaned_reasoning_structured = sanitize_comment(reasoning_structured)
                    if is_publishable_comment(cleaned_reasoning_structured):
                        return self._generation_result(
                            content=cleaned_reasoning_structured,
                            content_source="structured_json_reasoning_content",
                            selected_attempt=resolved_task_shape,
                            finish_reason=finish_reason,
                            data=data,
                            payload=payload,
                            runtime=response_runtime,
                        )

        if content:
            cleaned_content = sanitize_comment(content)
            if is_publishable_comment(cleaned_content):
                return self._generation_result(
                    content=cleaned_content,
                    content_source="assistant_content",
                    selected_attempt=resolved_task_shape,
                    finish_reason=finish_reason,
                    data=data,
                    payload=payload,
                    runtime=response_runtime,
                )

        recovered = extract_comment_from_reasoning(reasoning)
        if recovered:
            cleaned_recovered = sanitize_comment(recovered)
            if is_publishable_comment(cleaned_recovered):
                return self._generation_result(
                    content=cleaned_recovered,
                    content_source="reasoning_tail_extraction",
                    selected_attempt=resolved_task_shape,
                    finish_reason=finish_reason,
                    data=data,
                    payload=payload,
                    runtime=response_runtime,
                )

        if finish_reason and finish_reason != "stop":
            raise ValueError(
                "Comment provider finished without final content "
                f"(finish_reason={finish_reason}); task_shape={resolved_task_shape}; max_tokens={resolved_max_tokens}"
            )

        raise ValueError(
            f"Comment provider returned empty content; task_shape={resolved_task_shape}; max_tokens={resolved_max_tokens}"
        )

    @staticmethod
    def _parse_sse_chat_completion_response(raw_text: str) -> dict[str, Any] | None:
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
