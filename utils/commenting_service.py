from __future__ import annotations

import os
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


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
        self.provider_name = (
            provider_name
            or os.getenv("AGENT_PLATFORM_COMMENTING_PROVIDER")
            or "openai-compatible"
        ).strip()

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

    @staticmethod
    def _normalize_content(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, dict):
                    text = str(item.get("text", "") or "").strip()
                    if text:
                        parts.append(text)
            return "\n".join(parts).strip()
        return str(value or "").strip()

    @retry(**_RETRY_KWARGS)
    def _post_chat_completions(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        with httpx.Client(timeout=self.timeout_seconds) as session:
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

    def generate_comment(self, *, model: str, system_prompt: str, user_input: str) -> str:
        resolved_model = self._resolve_provider_model(str(model or ""))
        if not resolved_model:
            raise ValueError("model is required")

        payload = {
            "model": resolved_model,
            "messages": [
                {"role": "system", "content": str(system_prompt or "")},
                {"role": "user", "content": str(user_input or "")},
            ],
            "temperature": 0.6,
        }

        data = self._post_chat_completions(payload)
        choices = data.get("choices", [])
        if not isinstance(choices, list) or not choices:
            raise ValueError("Comment provider returned no choices")

        message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        content = self._normalize_content(message.get("content", ""))
        if not content:
            raise ValueError("Comment provider returned empty content")
        return content
