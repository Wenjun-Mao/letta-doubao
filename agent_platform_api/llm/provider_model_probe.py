from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from agent_platform_api.llm.provider_probe_classifiers import (
    classify_chat_probe_payload,
    classify_label_probe_payload,
)
from agent_platform_api.llm.provider_probe_types import (
    ProbeCatalogAuthError,
    ProbedModelResult,
    RetryableProbeError,
    SourceProbeReport,
)
from agent_platform_api.services.labeling_helpers import (
    LABEL_PROBE_ARTICLE,
    build_label_probe_system_prompt,
    build_label_user_payload,
    label_probe_output_schema,
    label_response_format,
)
from model_router.catalog import RouterCatalogService, RouterModelRecord
from model_router.settings import RouterSourceConfig


_RETRYABLE_PROBE_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.RemoteProtocolError,
    httpx.WriteError,
)


def probe_source_chat_models(
    source: RouterSourceConfig,
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
    source: RouterSourceConfig,
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
    source: RouterSourceConfig,
    *,
    timeout_seconds: float,
) -> list[RouterModelRecord]:
    payload = _fetch_models_payload(source, timeout_seconds=timeout_seconds)
    return RouterCatalogService._extract_model_records(payload)


def probe_chat_model(
    source: RouterSourceConfig,
    record: RouterModelRecord,
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
    source: RouterSourceConfig,
    record: RouterModelRecord,
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
    source: RouterSourceConfig,
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
    source: RouterSourceConfig,
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
    source: RouterSourceConfig,
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
    source: RouterSourceConfig,
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
    source: RouterSourceConfig,
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
    source: RouterSourceConfig,
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
        "response_format": label_response_format(label_probe_output_schema(), name="label_probe_output"),
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
    source: RouterSourceConfig,
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


def _short_text(value: str, *, limit: int = 240) -> str:
    text = str(value or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."
