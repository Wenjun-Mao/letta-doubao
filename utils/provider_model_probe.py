from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from agent_platform_api.settings import ModelSourceConfig
from utils.labeling_helpers import (
    LABEL_PROBE_ARTICLE,
    build_label_probe_system_prompt,
    build_label_user_payload,
    default_label_output_schema,
    label_probe_success,
    label_response_format,
    normalize_label_content,
    parse_json_object,
)
from utils.model_catalog import CatalogModelRecord, ModelCatalogService


ProbeResultStatus = Literal[
    "ok",
    "skipped_non_llm",
    "bad_request",
    "auth_error",
    "not_found",
    "rate_limited",
    "server_error",
    "timeout",
    "invalid_json",
    "invalid_payload",
    "network_error",
]
_RETRYABLE_PROBE_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.RemoteProtocolError,
    httpx.WriteError,
)


class ProbeCatalogAuthError(RuntimeError):
    def __init__(self, status_code: int, body: str = ""):
        self.status_code = int(status_code)
        self.body = str(body or "")
        super().__init__(f"Authentication failed ({self.status_code})")


class RetryableProbeError(RuntimeError):
    def __init__(self, status_code: int, body: str = ""):
        self.status_code = int(status_code)
        self.body = str(body or "")
        super().__init__(f"Temporary provider failure ({self.status_code})")


@dataclass(frozen=True)
class ProbedModelResult:
    provider_model_id: str
    model_type: str
    status: ProbeResultStatus
    usable: bool
    http_status: int | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_model_id": self.provider_model_id,
            "model_type": self.model_type,
            "status": self.status,
            "usable": self.usable,
            "http_status": self.http_status,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class SourceProbeReport:
    source_id: str
    checked_at: str
    probe_mode: str
    raw_model_count: int
    usable_models: tuple[str, ...]
    results: tuple[ProbedModelResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "checked_at": self.checked_at,
            "probe_mode": self.probe_mode,
            "raw_model_count": self.raw_model_count,
            "usable_models": list(self.usable_models),
            "results": [result.to_dict() for result in self.results],
        }


def probe_source_chat_models(
    source: ModelSourceConfig,
    *,
    timeout_seconds: float,
) -> SourceProbeReport:
    records = fetch_source_catalog_records(source, timeout_seconds=timeout_seconds)
    results: list[ProbedModelResult] = []

    for record in records:
        if record.model_type != "llm":
            results.append(
                ProbedModelResult(
                    provider_model_id=record.provider_model_id,
                    model_type=record.model_type,
                    status="skipped_non_llm",
                    usable=False,
                    detail="Only llm entries are probed for chat usability.",
                )
            )
            continue
        results.append(
            probe_chat_model(
                source,
                record,
                timeout_seconds=timeout_seconds,
            )
        )

    usable_models = tuple(result.provider_model_id for result in results if result.usable)
    return SourceProbeReport(
        source_id=source.id,
        checked_at=datetime.now(timezone.utc).isoformat(),
        probe_mode="chat-probe",
        raw_model_count=len(records),
        usable_models=usable_models,
        results=tuple(results),
    )


def probe_source_label_models(
    source: ModelSourceConfig,
    *,
    timeout_seconds: float,
) -> SourceProbeReport:
    records = fetch_source_catalog_records(source, timeout_seconds=timeout_seconds)
    results: list[ProbedModelResult] = []

    for record in records:
        if record.model_type != "llm":
            results.append(
                ProbedModelResult(
                    provider_model_id=record.provider_model_id,
                    model_type=record.model_type,
                    status="skipped_non_llm",
                    usable=False,
                    detail="Only llm entries are probed for label structured output.",
                )
            )
            continue
        results.append(
            probe_label_model(
                source,
                record,
                timeout_seconds=timeout_seconds,
            )
        )

    usable_models = tuple(result.provider_model_id for result in results if result.usable)
    return SourceProbeReport(
        source_id=source.id,
        checked_at=datetime.now(timezone.utc).isoformat(),
        probe_mode="label-structured",
        raw_model_count=len(records),
        usable_models=usable_models,
        results=tuple(results),
    )


def fetch_source_catalog_records(
    source: ModelSourceConfig,
    *,
    timeout_seconds: float,
) -> list[CatalogModelRecord]:
    payload = _fetch_models_payload(source, timeout_seconds=timeout_seconds)
    return ModelCatalogService._extract_model_records(payload)


def probe_chat_model(
    source: ModelSourceConfig,
    record: CatalogModelRecord,
    *,
    timeout_seconds: float,
) -> ProbedModelResult:
    try:
        payload = _post_chat_probe_with_retries(
            source,
            model_id=record.provider_model_id,
            timeout_seconds=timeout_seconds,
        )
    except ProbeCatalogAuthError as exc:
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="auth_error",
            usable=False,
            http_status=exc.status_code,
            detail=exc.body,
        )
    except RetryableProbeError as exc:
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="server_error" if exc.status_code >= 500 else "rate_limited",
            usable=False,
            http_status=exc.status_code,
            detail=exc.body,
        )
    except httpx.TimeoutException as exc:
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="timeout",
            usable=False,
            detail=str(exc),
        )
    except httpx.HTTPError as exc:
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="network_error",
            usable=False,
            detail=str(exc),
        )

    return classify_chat_probe_payload(record, payload)


def probe_label_model(
    source: ModelSourceConfig,
    record: CatalogModelRecord,
    *,
    timeout_seconds: float,
) -> ProbedModelResult:
    try:
        payload = _post_label_probe_with_retries(
            source,
            model_id=record.provider_model_id,
            timeout_seconds=timeout_seconds,
        )
    except ProbeCatalogAuthError as exc:
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="auth_error",
            usable=False,
            http_status=exc.status_code,
            detail=exc.body,
        )
    except RetryableProbeError as exc:
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="server_error" if exc.status_code >= 500 else "rate_limited",
            usable=False,
            http_status=exc.status_code,
            detail=exc.body,
        )
    except httpx.TimeoutException as exc:
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="timeout",
            usable=False,
            detail=str(exc),
        )
    except httpx.HTTPError as exc:
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="network_error",
            usable=False,
            detail=str(exc),
        )

    return classify_label_probe_payload(record, payload)


def _fetch_models_payload(
    source: ModelSourceConfig,
    *,
    timeout_seconds: float,
) -> Any:
    retrying = Retrying(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type((RetryableProbeError, *_RETRYABLE_PROBE_EXCEPTIONS)),
        reraise=True,
    )
    for attempt in retrying:
        with attempt:
            return _fetch_models_payload_once(source, timeout_seconds=timeout_seconds)
    raise RuntimeError("Provider catalog probe did not produce a result")


def _fetch_models_payload_once(
    source: ModelSourceConfig,
    *,
    timeout_seconds: float,
) -> Any:
    headers = _headers_for_source(source)
    with httpx.Client(timeout=timeout_seconds) as session:
        response = session.get(source.models_endpoint(), headers=headers)

    if response.status_code in {401, 403}:
        raise ProbeCatalogAuthError(response.status_code, _short_text(response.text))
    if response.status_code in {429, 500, 502, 503, 504}:
        raise RetryableProbeError(response.status_code, _short_text(response.text))
    if response.status_code >= 400:
        raise RuntimeError(f"Provider catalog request failed ({response.status_code}): {response.text}")

    try:
        return response.json()
    except Exception as exc:  # pragma: no cover - defensive
        raise RuntimeError("Provider catalog returned non-JSON payload") from exc


def _post_chat_probe_with_retries(
    source: ModelSourceConfig,
    *,
    model_id: str,
    timeout_seconds: float,
) -> Any:
    retrying = Retrying(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type((RetryableProbeError, *_RETRYABLE_PROBE_EXCEPTIONS)),
        reraise=True,
    )
    for attempt in retrying:
        with attempt:
            return _post_chat_probe_once(source, model_id=model_id, timeout_seconds=timeout_seconds)
    raise RuntimeError("Provider chat probe did not produce a result")


def _post_chat_probe_once(
    source: ModelSourceConfig,
    *,
    model_id: str,
    timeout_seconds: float,
) -> Any:
    headers = _headers_for_source(source, include_json_content_type=True)
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
        "stream": False,
        "max_tokens": 8,
        "temperature": 0,
    }

    with httpx.Client(timeout=timeout_seconds) as session:
        response = session.post(source.chat_completions_url(), headers=headers, json=payload)

    if response.status_code == 200:
        try:
            return response.json()
        except Exception:
            return {"invalid_json": True, "detail": _short_text(response.text)}
    if response.status_code == 400:
        return {
            "provider_model_id": model_id,
            "status": "bad_request",
            "http_status": 400,
            "detail": _short_text(response.text),
        }
    if response.status_code in {401, 403}:
        raise ProbeCatalogAuthError(response.status_code, _short_text(response.text))
    if response.status_code == 404:
        return {
            "provider_model_id": model_id,
            "status": "not_found",
            "http_status": 404,
            "detail": _short_text(response.text),
        }
    if response.status_code == 429:
        raise RetryableProbeError(response.status_code, _short_text(response.text))
    if response.status_code >= 500:
        raise RetryableProbeError(response.status_code, _short_text(response.text))

    return {
        "provider_model_id": model_id,
        "status": "network_error",
        "http_status": response.status_code,
        "detail": _short_text(response.text),
    }


def _post_label_probe_with_retries(
    source: ModelSourceConfig,
    *,
    model_id: str,
    timeout_seconds: float,
) -> Any:
    retrying = Retrying(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type((RetryableProbeError, *_RETRYABLE_PROBE_EXCEPTIONS)),
        reraise=True,
    )
    for attempt in retrying:
        with attempt:
            return _post_label_probe_once(source, model_id=model_id, timeout_seconds=timeout_seconds)
    raise RuntimeError("Provider label probe did not produce a result")


def _post_label_probe_once(
    source: ModelSourceConfig,
    *,
    model_id: str,
    timeout_seconds: float,
) -> Any:
    headers = _headers_for_source(source, include_json_content_type=True)
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": build_label_probe_system_prompt()},
            {"role": "user", "content": build_label_user_payload(LABEL_PROBE_ARTICLE)},
        ],
        "stream": False,
        "max_tokens": 256,
        "temperature": 0,
        "response_format": label_response_format(default_label_output_schema(), name="label_probe_output"),
    }

    with httpx.Client(timeout=timeout_seconds) as session:
        response = session.post(source.chat_completions_url(), headers=headers, json=payload)

    if response.status_code == 200:
        try:
            return response.json()
        except Exception:
            return {"invalid_json": True, "detail": _short_text(response.text)}
    if response.status_code == 400:
        return {
            "provider_model_id": model_id,
            "status": "bad_request",
            "http_status": 400,
            "detail": _short_text(response.text),
        }
    if response.status_code in {401, 403}:
        raise ProbeCatalogAuthError(response.status_code, _short_text(response.text))
    if response.status_code == 404:
        return {
            "provider_model_id": model_id,
            "status": "not_found",
            "http_status": 404,
            "detail": _short_text(response.text),
        }
    if response.status_code == 429:
        raise RetryableProbeError(response.status_code, _short_text(response.text))
    if response.status_code >= 500:
        raise RetryableProbeError(response.status_code, _short_text(response.text))

    return {
        "provider_model_id": model_id,
        "status": "network_error",
        "http_status": response.status_code,
        "detail": _short_text(response.text),
    }


def _headers_for_source(
    source: ModelSourceConfig,
    *,
    include_json_content_type: bool = False,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    if include_json_content_type:
        headers["Content-Type"] = "application/json"
    api_key = source.resolve_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def classify_chat_probe_payload(
    record: CatalogModelRecord,
    payload: Any,
) -> ProbedModelResult:
    if isinstance(payload, dict) and payload.get("status") == "bad_request":
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="bad_request",
            usable=False,
            http_status=400,
            detail=str(payload.get("detail", "") or ""),
        )
    if isinstance(payload, dict) and payload.get("status") == "not_found":
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="not_found",
            usable=False,
            http_status=404,
            detail=str(payload.get("detail", "") or ""),
        )
    if isinstance(payload, dict) and payload.get("invalid_json"):
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="invalid_json",
            usable=False,
            http_status=200,
            detail=str(payload.get("detail", "") or ""),
        )
    if isinstance(payload, dict) and payload.get("status") == "network_error":
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="network_error",
            usable=False,
            http_status=int(payload.get("http_status", 0) or 0) or None,
            detail=str(payload.get("detail", "") or ""),
        )

    if not isinstance(payload, dict):
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="invalid_payload",
            usable=False,
            detail="Response payload must be an object.",
        )

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="invalid_payload",
            usable=False,
            http_status=200,
            detail="Response payload did not include any choices.",
        )

    return ProbedModelResult(
        provider_model_id=record.provider_model_id,
        model_type=record.model_type,
        status="ok",
        usable=True,
        http_status=200,
        detail="ok",
    )


def classify_label_probe_payload(
    record: CatalogModelRecord,
    payload: Any,
) -> ProbedModelResult:
    if isinstance(payload, dict) and payload.get("status") == "bad_request":
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="bad_request",
            usable=False,
            http_status=400,
            detail=str(payload.get("detail", "") or ""),
        )
    if isinstance(payload, dict) and payload.get("status") == "not_found":
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="not_found",
            usable=False,
            http_status=404,
            detail=str(payload.get("detail", "") or ""),
        )
    if isinstance(payload, dict) and payload.get("invalid_json"):
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="invalid_json",
            usable=False,
            http_status=200,
            detail=str(payload.get("detail", "") or ""),
        )
    if isinstance(payload, dict) and payload.get("status") == "network_error":
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="network_error",
            usable=False,
            http_status=int(payload.get("http_status", 0) or 0) or None,
            detail=str(payload.get("detail", "") or ""),
        )

    if not isinstance(payload, dict):
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="invalid_payload",
            usable=False,
            detail="Response payload must be an object.",
        )

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ProbedModelResult(
            provider_model_id=record.provider_model_id,
            model_type=record.model_type,
            status="invalid_payload",
            usable=False,
            http_status=200,
            detail="Response payload did not include any choices.",
        )

    choice = choices[0] if isinstance(choices[0], dict) else {}
    message = choice.get("message", {}) if isinstance(choice, dict) else {}
    candidates = [
        normalize_label_content(message.get("content", "")),
        normalize_label_content(message.get("reasoning_content", "")),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = parse_json_object(candidate)
        except ValueError:
            continue
        if label_probe_success(parsed):
            return ProbedModelResult(
                provider_model_id=record.provider_model_id,
                model_type=record.model_type,
                status="ok",
                usable=True,
                http_status=200,
                detail="ok",
            )

    return ProbedModelResult(
        provider_model_id=record.provider_model_id,
        model_type=record.model_type,
        status="invalid_payload",
        usable=False,
        http_status=200,
        detail="Structured output probe did not return the expected JSON span result.",
    )


def _short_text(value: str, *, limit: int = 240) -> str:
    text = str(value or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."
