from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from utils.commenting_helpers import (
    build_all_in_system_prompt,
    build_compact_user_payload,
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


_RETRY_KWARGS = {
    "stop": stop_after_attempt(3),
    "wait": wait_exponential(multiplier=1, min=1, max=8),
    "retry": retry_if_exception_type(
        (
            _RetryableCommentingError,
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.ReadError,
            httpx.RemoteProtocolError,
            httpx.WriteError,
        )
    ),
    "reraise": True,
}


class CommentingService:
    """Stateless comment generation through an OpenAI-compatible chat completions API."""

    _MODEL_HANDLE_PREFIXES = (
        "lmstudio_openai/",
        "openai-proxy/",
        "openai/",
        "anthropic/",
    )
    _TASK_SHAPES = {"compact", "all_in_system", "structured_output"}
    _TASK_SHAPE_ALIASES = {
        "auto": "compact",
        "agent_studio": "all_in_system",
    }

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        provider_name: str | None = None,
    ):
        self.base_url = self._resolve_base_url(base_url)
        self.api_key = (api_key or os.getenv("AGENT_PLATFORM_COMMENTING_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
        self.timeout_seconds = float(
            timeout_seconds
            if timeout_seconds is not None
            else os.getenv("AGENT_PLATFORM_COMMENTING_TIMEOUT_SECONDS", "60")
        )
        self.max_tokens = int(os.getenv("AGENT_PLATFORM_COMMENTING_MAX_TOKENS", "0"))
        self.task_shape_default = self._resolve_task_shape(os.getenv("AGENT_PLATFORM_COMMENTING_TASK_SHAPE", "compact"))
        self.provider_name = (
            provider_name
            or os.getenv("AGENT_PLATFORM_COMMENTING_PROVIDER")
            or "openai-compatible"
        ).strip()

    @staticmethod
    def _clamp_max_tokens(value: int) -> int:
        if int(value) <= 0:
            # `0` is treated as "no max_tokens parameter" for provider requests.
            return 0
        return max(64, min(8192, int(value)))

    @staticmethod
    def _clamp_timeout_seconds(value: float) -> float:
        return max(5.0, min(600.0, float(value)))

    @classmethod
    def _resolve_task_shape(cls, value: str | None) -> str:
        resolved = str(value or "").strip().lower()
        if resolved in cls._TASK_SHAPES:
            return resolved
        return cls._TASK_SHAPE_ALIASES.get(resolved, "compact")

    def runtime_defaults(self) -> dict[str, Any]:
        return {
            "max_tokens": self._clamp_max_tokens(self.max_tokens),
            "timeout_seconds": self._clamp_timeout_seconds(self.timeout_seconds),
            "task_shape": self.task_shape_default,
        }

    def _chat_completions_url(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    @staticmethod
    def _resolve_base_url(explicit_base_url: str | None) -> str:
        candidates = [
            explicit_base_url,
            os.getenv("AGENT_PLATFORM_COMMENTING_BASE_URL"),
            os.getenv("LMSTUDIO_BASE_URL"),
            os.getenv("OPENAI_BASE_URL"),
            os.getenv("OPENAI_API_BASE"),
            "http://127.0.0.1:1234/v1",
        ]

        for candidate in candidates:
            resolved = str(candidate or "").strip()
            if resolved:
                return resolved

        return "http://127.0.0.1:1234/v1"

    @classmethod
    def _resolve_provider_model(cls, model: str) -> str:
        resolved_model = model.strip()
        lowered_model = resolved_model.lower()
        for prefix in cls._MODEL_HANDLE_PREFIXES:
            if lowered_model.startswith(prefix):
                return resolved_model[len(prefix):].strip()
        return resolved_model

    @retry(**_RETRY_KWARGS)
    def _post_chat_completions(self, payload: dict[str, Any], *, timeout_seconds: float) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        with httpx.Client(timeout=timeout_seconds) as session:
            response = session.post(self._chat_completions_url(), json=payload, headers=headers)

        if response.status_code >= 500 or response.status_code == 429:
            raise _RetryableCommentingError(
                f"Comment provider temporary failure ({response.status_code}): {response.text}"
            )
        if response.status_code >= 400:
            raise ValueError(f"Comment provider request failed ({response.status_code}): {response.text}")

        try:
            data = response.json()
        except Exception as exc:  # pragma: no cover
            raise ValueError(f"Comment provider returned non-JSON response: {response.text}") from exc

        if not isinstance(data, dict):
            raise ValueError("Comment provider returned invalid payload")
        return data

    def generate_comment(
        self,
        *,
        model: str,
        system_prompt: str,
        persona_prompt: str,
        news_input: str,
        max_tokens: int | None = None,
        timeout_seconds: float | None = None,
        task_shape: str | None = None,
    ) -> dict[str, Any]:
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
        resolved_task_shape = runtime_defaults["task_shape"] if task_shape is None else self._resolve_task_shape(task_shape)

        compact_payload = {
            "model": resolved_model,
            "messages": [
                {"role": "system", "content": str(system_prompt or "")},
                {
                    "role": "user",
                    "content": build_compact_user_payload(
                        persona_prompt=persona_prompt,
                        news_input=news_input,
                    ),
                },
            ],
            "temperature": 0.6,
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
            "temperature": 0.6,
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
            "temperature": 0.2,
            "max_tokens": resolved_max_tokens,
            "response_format": structured_response_format(),
        }

        payload_by_shape: dict[str, dict[str, Any]] = {
            "compact": compact_payload,
            "all_in_system": all_in_system_payload,
            "structured_output": structured_output_payload,
        }

        payload = payload_by_shape.get(resolved_task_shape, compact_payload)

        if resolved_max_tokens == 0:
            payload.pop("max_tokens", None)

        try:
            data = self._post_chat_completions(payload, timeout_seconds=resolved_timeout_seconds)
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
            data = self._post_chat_completions(payload, timeout_seconds=resolved_timeout_seconds)

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
                        return {
                            "content": cleaned_reasoning_structured,
                            "content_source": "structured_json_reasoning_content",
                            "selected_attempt": resolved_task_shape,
                            "finish_reason": finish_reason,
                            "usage": data.get("usage", {}) if isinstance(data.get("usage", {}), dict) else {},
                            "received_at": datetime.now(timezone.utc).isoformat(),
                            "raw_request": payload,
                            "raw_reply": data,
                            "max_tokens": resolved_max_tokens,
                            "timeout_seconds": resolved_timeout_seconds,
                            "task_shape": resolved_task_shape,
                        }

        if content:
            cleaned_content = sanitize_comment(content)
            if is_publishable_comment(cleaned_content):
                return {
                    "content": cleaned_content,
                    "content_source": "assistant_content",
                    "selected_attempt": resolved_task_shape,
                    "finish_reason": finish_reason,
                    "usage": data.get("usage", {}) if isinstance(data.get("usage", {}), dict) else {},
                    "received_at": datetime.now(timezone.utc).isoformat(),
                    "raw_request": payload,
                    "raw_reply": data,
                    "max_tokens": resolved_max_tokens,
                    "timeout_seconds": resolved_timeout_seconds,
                    "task_shape": resolved_task_shape,
                }

        recovered = extract_comment_from_reasoning(reasoning)
        if recovered:
            cleaned_recovered = sanitize_comment(recovered)
            if is_publishable_comment(cleaned_recovered):
                return {
                    "content": cleaned_recovered,
                    "content_source": "reasoning_tail_extraction",
                    "selected_attempt": resolved_task_shape,
                    "finish_reason": finish_reason,
                    "usage": data.get("usage", {}) if isinstance(data.get("usage", {}), dict) else {},
                    "received_at": datetime.now(timezone.utc).isoformat(),
                    "raw_request": payload,
                    "raw_reply": data,
                    "max_tokens": resolved_max_tokens,
                    "timeout_seconds": resolved_timeout_seconds,
                    "task_shape": resolved_task_shape,
                }

        if finish_reason and finish_reason != "stop":
            raise ValueError(
                "Comment provider finished without final content "
                f"(finish_reason={finish_reason}); task_shape={resolved_task_shape}; max_tokens={resolved_max_tokens}"
            )

        raise ValueError(
            f"Comment provider returned empty content; task_shape={resolved_task_shape}; max_tokens={resolved_max_tokens}"
        )
