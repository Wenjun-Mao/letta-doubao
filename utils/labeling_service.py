from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from agent_platform_api.settings import get_settings
from utils.labeling_helpers import (
    build_best_effort_label_system_prompt,
    build_label_user_payload,
    build_repair_prompt,
    label_response_format,
    normalize_label_content,
    parse_json_object,
    resolve_label_output_schema,
    validate_label_result,
)


class _RetryableLabelingError(RuntimeError):
    """Raised for provider responses that should be retried."""


class LabelingValidationError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        validation_errors: list[str],
        raw_request: dict[str, Any] | None = None,
        raw_reply: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.validation_errors = list(validation_errors)
        self.raw_request = dict(raw_request or {})
        self.raw_reply = dict(raw_reply or {})


DEFAULT_LABELING_REPAIR_RETRY_COUNT = 1
MAX_LABELING_REPAIR_RETRY_COUNT = 3
_RETRYABLE_LABELING_EXCEPTIONS = (
    _RetryableLabelingError,
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.RemoteProtocolError,
    httpx.WriteError,
)
_VERSION_PATH_RE = re.compile(r"/v\d+(?:\.\d+)?$", re.IGNORECASE)


class LabelingService:
    """Stateless structured labeling through an OpenAI-compatible chat completions API."""

    _MODEL_HANDLE_PREFIXES = (
        "lmstudio_openai/",
        "openai-proxy/",
        "openai/",
        "anthropic/",
    )
    _OUTPUT_MODES = {"strict_json_schema", "json_schema", "best_effort_prompt_json"}

    def __init__(self, *, settings_factory=get_settings):
        self._settings_factory = settings_factory

    @staticmethod
    def _clamp_max_tokens(value: int) -> int:
        if int(value) <= 0:
            return 0
        return max(64, min(8192, int(value)))

    @staticmethod
    def _clamp_timeout_seconds(value: float) -> float:
        return max(5.0, min(600.0, float(value)))

    @staticmethod
    def _clamp_repair_retry_count(value: int | None) -> int:
        if value is None:
            return DEFAULT_LABELING_REPAIR_RETRY_COUNT
        return max(0, min(MAX_LABELING_REPAIR_RETRY_COUNT, int(value)))

    @classmethod
    def _resolve_output_mode(cls, value: str | None) -> str:
        resolved = str(value or "").strip().lower()
        if not resolved:
            return "best_effort_prompt_json"
        if resolved in cls._OUTPUT_MODES:
            return resolved
        raise ValueError(f"Unsupported output_mode: {resolved}")

    @staticmethod
    def _normalize_response_format_name(value: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "").strip())
        normalized = normalized.strip("_")
        return normalized[:64] or "label_output"

    def runtime_defaults(self) -> dict[str, Any]:
        settings = self._settings_factory()
        return {
            "max_tokens": self._clamp_max_tokens(settings.labeling_max_tokens),
            "timeout_seconds": self._clamp_timeout_seconds(settings.labeling_timeout_seconds),
            "repair_retry_count": self._clamp_repair_retry_count(settings.labeling_repair_retry_count),
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
                return resolved_model[len(prefix) :].strip()
        return resolved_model

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
            response = session.post(self._chat_completions_url(base_url), json=payload, headers=headers)

        if response.status_code >= 500 or response.status_code == 429:
            raise _RetryableLabelingError(
                f"Label provider temporary failure ({response.status_code}): {response.text}"
            )
        if response.status_code >= 400:
            raise ValueError(f"Label provider request failed ({response.status_code}): {response.text}")

        try:
            data = response.json()
        except Exception:
            data = self._parse_sse_chat_completion_response(response.text)
            if data is None:
                raise ValueError(f"Label provider returned non-JSON response: {response.text}")

        if not isinstance(data, dict):
            raise ValueError("Label provider returned invalid payload")
        return data

    def _post_chat_completions(
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

    def _build_payload(
        self,
        *,
        model: str,
        system_prompt: str,
        article_input: str,
        output_schema: dict[str, Any],
        output_schema_name: str,
        output_mode: str,
        max_tokens: int,
    ) -> dict[str, Any]:
        if output_mode in {"strict_json_schema", "json_schema"}:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": str(system_prompt or "").strip()},
                    {"role": "user", "content": build_label_user_payload(article_input)},
                ],
                "temperature": 0,
                "max_tokens": max_tokens,
                "response_format": label_response_format(output_schema, name=output_schema_name),
            }
        else:
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": build_best_effort_label_system_prompt(
                            system_prompt=system_prompt,
                            schema=output_schema,
                        ),
                    },
                    {"role": "user", "content": build_label_user_payload(article_input)},
                ],
                "temperature": 0,
                "max_tokens": max_tokens,
            }

        if max_tokens == 0:
            payload.pop("max_tokens", None)
        return payload

    def _build_repair_payload(
        self,
        *,
        model: str,
        system_prompt: str,
        article_input: str,
        output_schema: dict[str, Any],
        output_schema_name: str,
        output_mode: str,
        max_tokens: int,
        invalid_output: str,
        validation_errors: list[str],
    ) -> dict[str, Any]:
        payload = self._build_payload(
            model=model,
            system_prompt=system_prompt,
            article_input=article_input,
            output_schema=output_schema,
            output_schema_name=output_schema_name,
            output_mode=output_mode,
            max_tokens=max_tokens,
        )
        payload["messages"] = [
            payload["messages"][0],
            {
                "role": "user",
                "content": build_repair_prompt(
                    article_input=article_input,
                    invalid_output=invalid_output,
                    validation_errors=validation_errors,
                ),
            },
        ]
        return payload

    def _extract_validated_result(
        self,
        *,
        data: dict[str, Any],
        article_input: str,
    ) -> tuple[dict[str, Any] | None, str, list[str], str | None]:
        choices = data.get("choices", [])
        if not isinstance(choices, list) or not choices:
            return None, "", ["Response payload did not include any choices."], None

        choice = choices[0] if isinstance(choices[0], dict) else {}
        message = choice.get("message", {}) if isinstance(choice, dict) else {}
        finish_reason = str(choice.get("finish_reason", "") or "").strip().lower() if isinstance(choice, dict) else ""

        content_candidate = normalize_label_content(message.get("content", ""))
        reasoning_candidate = normalize_label_content(message.get("reasoning_content", ""))
        candidates = [content_candidate] if content_candidate else [reasoning_candidate]
        validation_errors: list[str] = []
        invalid_output = ""
        for candidate in candidates:
            if not candidate:
                continue
            invalid_output = invalid_output or candidate
            try:
                parsed = parse_json_object(candidate)
            except ValueError as exc:
                validation_errors.append(str(exc))
                continue

            normalized, errors = validate_label_result(parsed, article_input)
            if normalized is not None:
                return normalized, candidate, [], finish_reason or None
            validation_errors.extend(errors)

        if finish_reason and finish_reason != "stop":
            validation_errors.append(f"Provider finished with finish_reason={finish_reason}.")
        return None, invalid_output, validation_errors or ["Provider returned empty content."], finish_reason or None

    def generate_labels(
        self,
        *,
        base_url: str,
        api_key: str = "",
        model: str,
        system_prompt: str,
        article_input: str,
        output_mode: str,
        output_schema_raw: str | None = None,
        output_schema_name: str = "label_output",
        max_tokens: int | None = None,
        timeout_seconds: float | None = None,
        repair_retry_count: int | None = None,
    ) -> dict[str, Any]:
        resolved_base_url = str(base_url or "").strip()
        if not resolved_base_url:
            raise ValueError("base_url is required")

        resolved_model = self._resolve_provider_model(str(model or ""))
        if not resolved_model:
            raise ValueError("model is required")

        article = str(article_input or "").strip()
        if not article:
            raise ValueError("input is required")

        output_schema = resolve_label_output_schema(output_schema_raw)
        resolved_output_schema_name = self._normalize_response_format_name(output_schema_name)
        runtime_defaults = self.runtime_defaults()
        resolved_max_tokens = runtime_defaults["max_tokens"] if max_tokens is None else self._clamp_max_tokens(max_tokens)
        resolved_timeout_seconds = (
            runtime_defaults["timeout_seconds"]
            if timeout_seconds is None
            else self._clamp_timeout_seconds(timeout_seconds)
        )
        resolved_repair_retry_count = (
            runtime_defaults["repair_retry_count"]
            if repair_retry_count is None
            else self._clamp_repair_retry_count(repair_retry_count)
        )
        resolved_output_mode = self._resolve_output_mode(output_mode)

        attempts: list[tuple[str, dict[str, Any]]] = [
            (
                "primary",
                self._build_payload(
                    model=resolved_model,
                    system_prompt=system_prompt,
                    article_input=article,
                    output_schema=output_schema,
                    output_schema_name=resolved_output_schema_name,
                    output_mode=resolved_output_mode,
                    max_tokens=resolved_max_tokens,
                ),
            )
        ]

        last_payload: dict[str, Any] = {}
        last_data: dict[str, Any] = {}
        last_errors: list[str] = []
        last_invalid_output = ""
        last_finish_reason: str | None = None

        while attempts:
            attempt_name, payload = attempts.pop(0)
            data = self._post_chat_completions(
                payload,
                base_url=resolved_base_url,
                api_key=str(api_key or "").strip(),
                timeout_seconds=resolved_timeout_seconds,
            )
            result, invalid_output, validation_errors, finish_reason = self._extract_validated_result(
                data=data,
                article_input=article,
            )
            last_payload = payload
            last_data = data
            last_errors = validation_errors
            last_invalid_output = invalid_output
            last_finish_reason = finish_reason

            if result is not None:
                return {
                    "result": result,
                    "output_mode": resolved_output_mode,
                    "selected_attempt": attempt_name,
                    "finish_reason": finish_reason,
                    "usage": data.get("usage", {}) if isinstance(data.get("usage", {}), dict) else {},
                    "received_at": datetime.now(timezone.utc).isoformat(),
                    "raw_request": payload,
                    "raw_reply": data,
                    "validation_errors": [],
                    "max_tokens": resolved_max_tokens,
                    "timeout_seconds": resolved_timeout_seconds,
                    "repair_retry_count": resolved_repair_retry_count,
                }

            if attempt_name == "primary" and resolved_repair_retry_count > 0:
                attempts.append(
                    (
                        "repair",
                        self._build_repair_payload(
                            model=resolved_model,
                            system_prompt=system_prompt,
                            article_input=article,
                            output_schema=output_schema,
                            output_schema_name=resolved_output_schema_name,
                            output_mode=resolved_output_mode,
                            max_tokens=resolved_max_tokens,
                            invalid_output=last_invalid_output,
                            validation_errors=last_errors,
                        ),
                    )
                )
                resolved_repair_retry_count -= 1

        if last_finish_reason and last_finish_reason != "stop" and not any(
            error.startswith("Provider finished with finish_reason=") for error in last_errors
        ):
            last_errors.append(f"Provider finished with finish_reason={last_finish_reason}.")
        raise LabelingValidationError(
            "Label provider returned invalid structured output.",
            validation_errors=last_errors,
            raw_request=last_payload,
            raw_reply=last_data,
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
