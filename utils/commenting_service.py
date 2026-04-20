from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
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

    @staticmethod
    def _extract_comment_from_reasoning(reasoning_text: str) -> str:
        """Heuristically recover a final comment from provider reasoning when content is empty.

        Some local providers can emit long reasoning and leave assistant `content` empty under
        certain prompt shapes. We only use this as a final fallback and keep extraction strict.
        """
        text = str(reasoning_text or "").strip()
        if not text:
            return ""

        # Prefer explicitly marked final lines often emitted by local reasoning templates.
        patterns = [
            r"(?:Final\s*decision|Final\s*answer|Selected\s*Comment|最终决定|最终答案|最终评论)\s*[:：]\s*(.+)$",
            r"(?:输出|评论)\s*[:：]\s*(.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
            if match:
                candidate = str(match.group(1) or "").strip().strip('"\'`')
                if candidate:
                    return candidate

        # Look for quoted Chinese draft lines often present in reasoning logs.
        quoted_candidates: list[str] = []
        for pattern in (r"[\"“](.+?)[\"”]", r"[「『](.+?)[」』]"):
            for match in re.finditer(pattern, text, flags=re.DOTALL):
                candidate = str(match.group(1) or "").strip()
                if candidate and re.search(r"[\u4e00-\u9fff]", candidate):
                    quoted_candidates.append(candidate)

        if quoted_candidates:
            punctuated = [c for c in quoted_candidates if c.endswith(("。", "！", "？", "!", "?", "～", "~"))]
            if punctuated:
                return punctuated[-1].strip().strip('"\'`')
            return quoted_candidates[-1].strip().strip('"\'`')

        # Collect likely draft lines and prefer the latest complete sentence.
        line_candidates: list[str] = []
        for raw_line in text.splitlines():
            line = str(raw_line or "").strip()
            if not line:
                continue
            line = re.sub(r"^[\-\*\d\.\)\s]+", "", line).strip()
            if len(line) < 12:
                continue
            if not re.search(r"[\u4e00-\u9fff]", line):
                continue
            lowered = line.lower()
            if any(marker in lowered for marker in ("thinking process", "analyze", "draft", "option ", "step ")):
                continue
            line_candidates.append(line)

        if line_candidates:
            punctuated = [c for c in line_candidates if c.endswith(("。", "！", "？", "!", "?", "～", "~"))]
            if punctuated:
                return punctuated[-1].strip().strip('"\'`')
            # If none are punctuated, use the longest line candidate.
            return max(line_candidates, key=len).strip().strip('"\'`')

        # Fall back to the last non-empty line if no explicit marker exists.
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return ""
        last = lines[-1].strip().strip('"\'`')
        return last

    @staticmethod
    def _is_publishable_comment(value: str) -> bool:
        text = str(value or "").strip()
        if len(text) < 8:
            return False

        if "**" in text or text.startswith("#"):
            return False

        lowered = text.lower()
        obvious_reasoning_markers = (
            "thinking process",
            "analyze the request",
            "drafting",
            "final decision",
            "option 1",
            "option 2",
            "option 3",
            "步骤",
            "思考过程",
            "最终决定",
            "persona:",
            "persona：",
            "assistant:",
            "assistant：",
            "system:",
            "system：",
        )
        if any(marker in lowered for marker in obvious_reasoning_markers):
            return False

        if text.startswith(("-", "*", "1.", "2.", "3.")):
            return False

        invalid_tail = (",", "，", ":", "：", ";", "；", "、", "-", "—", "（", "(")
        if text.endswith(invalid_tail):
            return False

        valid_tail = ("。", "！", "？", "!", "?", "～", "~", "」", "』", "”", '"')
        if not text.endswith(valid_tail):
            return False

        return True

    @staticmethod
    def _sanitize_comment(value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""

        # Drop obvious trailing separators from partially generated text.
        text = re.sub(r"[\s,，:：;；、\-—]+$", "", text).strip()
        if not text:
            return ""

        valid_tail = ("。", "！", "？", "!", "?", "～", "~", "」", "』", "”", '"')
        if not text.endswith(valid_tail):
            text = f"{text}。"
        return text

    @staticmethod
    def _build_compact_user_payload(*, persona_prompt: str, news_input: str) -> str:
        """Compact shape keeps persona and content together in the user message."""
        return (
            "你正在执行新闻评论生成任务。\n"
            "请严格使用给定persona语气写一条可直接发布的中文评论。\n\n"
            "[Persona]\n"
            f"{str(persona_prompt or '').strip()}\n\n"
            "[任务输入]\n"
            f"{str(news_input or '').strip()}"
        )

    @staticmethod
    def _build_all_in_system_prompt(*, system_prompt: str, persona_prompt: str) -> str:
        """All-in-system shape places both global and persona guidance in system."""
        return (
            f"{str(system_prompt or '').strip()}\n\n"
            "[Persona]\n"
            f"{str(persona_prompt or '').strip()}"
        )

    @staticmethod
    def _build_structured_system_prompt(*, system_prompt: str, persona_prompt: str) -> str:
        return (
            f"{CommentingService._build_all_in_system_prompt(system_prompt=system_prompt, persona_prompt=persona_prompt)}\n\n"
            "输出要求：\n"
            "1. 你必须返回 JSON 对象。\n"
            "2. JSON 仅允许一个字段: comment。\n"
            "3. comment 必须是可发布的中文评论，不要附加解释。"
        )

    @staticmethod
    def _structured_response_format() -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "comment_output",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "comment": {
                            "type": "string",
                            "minLength": 1,
                        }
                    },
                    "required": ["comment"],
                    "additionalProperties": False,
                },
            },
        }

    @staticmethod
    def _extract_structured_comment(content_text: str) -> str:
        text = str(content_text or "").strip()
        if not text:
            return ""

        # Many providers wrap JSON in markdown fences; normalize that first.
        fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
        if fence_match:
            text = str(fence_match.group(1) or "").strip()

        def _comment_from_json(raw: str) -> str:
            try:
                parsed = json.loads(raw)
            except Exception:
                return ""
            if isinstance(parsed, dict):
                value = parsed.get("comment")
                if isinstance(value, str):
                    return value.strip()
            return ""

        direct = _comment_from_json(text)
        if direct:
            return direct

        # Recover from wrappers such as: prefix ... {"comment": "..."} ... suffix
        object_match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if object_match:
            nested = _comment_from_json(str(object_match.group(0) or ""))
            if nested:
                return nested

        return ""

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
                    "content": self._build_compact_user_payload(
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
                    "content": self._build_all_in_system_prompt(
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
                    "content": self._build_structured_system_prompt(
                        system_prompt=system_prompt,
                        persona_prompt=persona_prompt,
                    ),
                },
                {"role": "user", "content": str(news_input or "").strip()},
            ],
            "temperature": 0.2,
            "max_tokens": resolved_max_tokens,
            "response_format": self._structured_response_format(),
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
        content = self._normalize_content(message.get("content", ""))
        reasoning = self._normalize_content(message.get("reasoning_content", ""))

        if resolved_task_shape == "structured_output":
            content = self._extract_structured_comment(content)
            if not content:
                reasoning_structured = self._extract_structured_comment(reasoning)
                if reasoning_structured:
                    cleaned_reasoning_structured = self._sanitize_comment(reasoning_structured)
                    if self._is_publishable_comment(cleaned_reasoning_structured):
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
            cleaned_content = self._sanitize_comment(content)
            if self._is_publishable_comment(cleaned_content):
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

        recovered = self._extract_comment_from_reasoning(reasoning)
        if recovered:
            cleaned_recovered = self._sanitize_comment(recovered)
            if self._is_publishable_comment(cleaned_recovered):
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
