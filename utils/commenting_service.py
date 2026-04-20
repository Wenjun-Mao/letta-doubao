from __future__ import annotations

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
    _TASK_SHAPES = {"auto", "agent_studio", "compact"}

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
        self.task_shape_default = self._resolve_task_shape(os.getenv("AGENT_PLATFORM_COMMENTING_TASK_SHAPE", "auto"))
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
        return "auto"

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
    def _build_chat_shaped_user_payload(*, system_prompt: str, user_input: str) -> str:
        """Build a chat-style task framing that better mirrors Agent Studio behavior.

        This keeps reasoning enabled while making final-response intent explicit.
        """
        return (
            "<base_instructions>\n"
            "You are a memory-augmented conversational persona and must reply to the user directly.\n"
            "You may reason privately first, then output the final user-facing reply.\n"
            "Always provide a non-empty final reply in Simplified Chinese.\n"
            "</base_instructions>\n\n"
            "<output_formatting_rules>\n"
            "1. Output plain dialogue only.\n"
            "2. No bullet list, no section headers, no meta text.\n"
            "3. Keep it concise and publishable for a public comment thread.\n"
            "</output_formatting_rules>\n\n"
            "[任务系统提示]\n"
            f"{str(system_prompt or '').strip()}\n\n"
            "[任务输入]\n"
            f"{str(user_input or '').strip()}"
        )

    @staticmethod
    def _build_direct_output_user_payload(*, system_prompt: str, user_input: str) -> str:
        """Build a final-attempt payload that strongly prioritizes direct user output."""
        return (
            "请直接输出一条可发布的中文评论，不要展示分析过程，不要输出步骤。\n"
            "输出必须是 1-2 句自然中文。\n\n"
            "[任务系统提示]\n"
            f"{str(system_prompt or '').strip()}\n\n"
            "[任务输入]\n"
            f"{str(user_input or '').strip()}"
        )

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
        user_input: str,
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

        primary_payload = {
            "model": resolved_model,
            "messages": [
                {"role": "system", "content": str(system_prompt or "")},
                {"role": "user", "content": str(user_input or "")},
            ],
            "temperature": 0.6,
            "max_tokens": resolved_max_tokens,
        }
        fallback_payload = {
            "model": resolved_model,
            "messages": [
                {
                    "role": "system",
                    "content": "You can reason privately, but must always return a non-empty final response.",
                },
                {
                    "role": "user",
                    "content": self._build_chat_shaped_user_payload(
                        system_prompt=system_prompt,
                        user_input=user_input,
                    ),
                },
            ],
            "temperature": 0.6,
            "max_tokens": resolved_max_tokens,
        }
        direct_output_payload = {
            "model": resolved_model,
            "messages": [
                {
                    "role": "system",
                    "content": "你可以在内部思考，但最终必须直接输出可发布评论，且输出不能为空。",
                },
                {
                    "role": "user",
                    "content": self._build_direct_output_user_payload(
                        system_prompt=system_prompt,
                        user_input=user_input,
                    ),
                },
            ],
            "temperature": 0.6,
            "max_tokens": resolved_max_tokens,
        }

        if resolved_max_tokens == 0:
            primary_payload.pop("max_tokens", None)
            fallback_payload.pop("max_tokens", None)
            direct_output_payload.pop("max_tokens", None)

        compact_attempts = [
            ("compact", primary_payload),
            ("agent_studio", fallback_payload),
            ("direct_output", direct_output_payload),
        ]
        agent_studio_attempts = [
            ("agent_studio", fallback_payload),
            ("compact", primary_payload),
            ("direct_output", direct_output_payload),
        ]

        if resolved_task_shape == "compact":
            payload_attempts = compact_attempts
        elif resolved_task_shape == "agent_studio":
            payload_attempts = agent_studio_attempts
        else:
            # Auto mode favors Agent Studio-like shape first due better final-response reliability.
            payload_attempts = agent_studio_attempts

        last_error = "Comment provider returned empty content"
        last_finish_reason = ""
        for attempt_name, payload in payload_attempts:
            data = self._post_chat_completions(payload, timeout_seconds=resolved_timeout_seconds)
            choices = data.get("choices", [])
            if not isinstance(choices, list) or not choices:
                last_error = "Comment provider returned no choices"
                continue

            message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
            finish_reason = str(choices[0].get("finish_reason", "") or "").strip().lower() if isinstance(choices[0], dict) else ""
            content = self._normalize_content(message.get("content", ""))
            if content:
                cleaned_content = self._sanitize_comment(content)
                if self._is_publishable_comment(cleaned_content):
                    return {
                        "content": cleaned_content,
                        "content_source": "assistant_content",
                        "selected_attempt": attempt_name,
                        "finish_reason": finish_reason,
                        "usage": data.get("usage", {}) if isinstance(data.get("usage", {}), dict) else {},
                        "received_at": datetime.now(timezone.utc).isoformat(),
                        "raw_request": payload,
                        "raw_reply": data,
                        "max_tokens": resolved_max_tokens,
                        "timeout_seconds": resolved_timeout_seconds,
                        "task_shape": resolved_task_shape,
                    }

            reasoning = self._normalize_content(message.get("reasoning_content", ""))
            recovered = self._extract_comment_from_reasoning(reasoning)
            last_finish_reason = finish_reason
            if recovered and attempt_name in {"compact", "agent_studio", "direct_output"}:
                cleaned_recovered = self._sanitize_comment(recovered)
                if self._is_publishable_comment(cleaned_recovered):
                    return {
                        "content": cleaned_recovered,
                        "content_source": "reasoning_tail_extraction",
                        "selected_attempt": attempt_name,
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
                last_error = f"Comment provider finished without final content (finish_reason={finish_reason})"
            else:
                last_error = "Comment provider returned empty content"

        if last_finish_reason and "finish_reason=" not in last_error:
            last_error = f"{last_error} (last_finish_reason={last_finish_reason})"
        raise ValueError(f"{last_error}; task_shape={resolved_task_shape}; max_tokens={resolved_max_tokens}")
