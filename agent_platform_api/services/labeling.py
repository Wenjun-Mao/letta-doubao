from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from agent_platform_api.settings import get_settings
from agent_platform_api.services.labeling_helpers import (
    build_best_effort_label_system_prompt,
    build_label_user_payload,
    build_repair_prompt,
    label_response_format,
    normalize_label_content,
    parse_json_object,
    resolve_label_output_schema,
    validate_label_result,
)
from agent_platform_api.services.labeling_provider_client import LabelingProviderClient, resolve_provider_model


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
DEFAULT_LABELING_TEMPERATURE = 0.0
DEFAULT_LABELING_TOP_P = 1.0


class LabelingService:
    """Stateless structured labeling through an OpenAI-compatible chat completions API."""

    _OUTPUT_MODES = {"strict_json_schema", "json_schema", "best_effort_prompt_json"}

    def __init__(self, *, settings_factory=get_settings):
        self._settings_factory = settings_factory
        self._provider_client = LabelingProviderClient()

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

    @staticmethod
    def _clamp_temperature(value: float | None) -> float:
        return DEFAULT_LABELING_TEMPERATURE if value is None else max(0.0, min(2.0, float(value)))

    @staticmethod
    def _clamp_top_p(value: float | None) -> float:
        return DEFAULT_LABELING_TOP_P if value is None else max(0.01, min(1.0, float(value)))

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
            "temperature": self._clamp_temperature(settings.labeling_temperature),
            "top_p": self._clamp_top_p(settings.labeling_top_p),
        }

    def _post_chat_completions(
        self,
        payload: dict[str, Any],
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        return self._provider_client.post_chat_completions(
            payload,
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )

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
        temperature: float,
        top_p: float,
    ) -> dict[str, Any]:
        if output_mode in {"strict_json_schema", "json_schema"}:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": str(system_prompt or "").strip()},
                    {"role": "user", "content": build_label_user_payload(article_input)},
                ],
                "temperature": temperature,
                "top_p": top_p,
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
                "temperature": temperature,
                "top_p": top_p,
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
        temperature: float,
        top_p: float,
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
            temperature=temperature,
            top_p=top_p,
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
        output_schema: dict[str, Any],
    ) -> tuple[dict[str, list[str]] | None, str, list[str], str | None]:
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

            normalized, errors = validate_label_result(parsed, article_input, output_schema)
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
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> dict[str, Any]:
        resolved_base_url = str(base_url or "").strip()
        if not resolved_base_url:
            raise ValueError("base_url is required")

        resolved_model = resolve_provider_model(str(model or ""))
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
        resolved_temperature = (
            float(runtime_defaults["temperature"])
            if temperature is None
            else self._clamp_temperature(temperature)
        )
        resolved_top_p = float(runtime_defaults["top_p"]) if top_p is None else self._clamp_top_p(top_p)
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
                    temperature=resolved_temperature,
                    top_p=resolved_top_p,
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
                output_schema=output_schema,
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
                    "temperature": resolved_temperature,
                    "top_p": resolved_top_p,
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
                            temperature=resolved_temperature,
                            top_p=resolved_top_p,
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
