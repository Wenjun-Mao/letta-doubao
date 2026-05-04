from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from model_router.catalog import (
    RoutedModel,
    RouterCatalogService,
    normalize_router_model_id,
    parse_router_model_id,
)
from model_router.settings import RouterSourceConfig, get_settings


app = FastAPI(
    title="ADE Model Router",
    version="0.1.0",
    description="First-party OpenAI-compatible router for ADE model sources.",
)
catalog_service = RouterCatalogService()
_RETRYABLE_FORWARD_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.RemoteProtocolError,
    httpx.WriteError,
)


def _require_router_auth(authorization: str | None) -> None:
    expected_key = get_settings().resolve_api_key()
    if not expected_key:
        return
    scheme, _, token = str(authorization or "").partition(" ")
    if scheme.lower() != "bearer" or token.strip() != expected_key:
        raise HTTPException(status_code=401, detail="Invalid model-router API key")


def _source_dict(source) -> dict[str, Any]:
    return {
        "id": source.id,
        "label": source.label,
        "kind": source.kind,
        "adapter": source.adapter,
        "base_url": source.base_url,
        "module_visibility": list(source.module_visibility),
        "status": source.status,
        "detail": source.detail,
        "allowlist_applied": source.allowlist_applied,
        "allowlist_checked_at": source.allowlist_checked_at,
        "raw_model_count": source.raw_model_count,
        "filtered_model_count": source.filtered_model_count,
        "models": [
            {
                "provider_model_id": model.provider_model_id,
                "model_type": model.model_type,
            }
            for model in source.models
        ],
    }


def _catalog_payload(*, force_refresh: bool = False) -> dict[str, Any]:
    snapshot = catalog_service.snapshot(force_refresh=force_refresh)
    return {
        "generated_at": snapshot.generated_at,
        "sources": [_source_dict(source) for source in snapshot.sources],
        "items": [model.as_dict() for model in catalog_service.flatten(snapshot)],
    }


def _openai_model_item(model: RoutedModel) -> dict[str, Any]:
    return {
        "id": model.router_model_id,
        "object": "model",
        "created": 0,
        "owned_by": "model_router",
        "source_id": model.source_id,
        "source_label": model.source_label,
    }


def _router_error(status_code: int, code: str, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "type": "model_router_error",
                "code": code,
                "message": message,
                **extra,
            }
        },
    )


@app.get("/v1/health")
@app.get("/v1/health/")
def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "configured_sources": len(settings.sources),
        "enabled_sources": len([source for source in settings.sources if source.enabled]),
    }


@app.get("/v1/models")
@app.get("/v1/models/")
def list_models(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _require_router_auth(authorization)
    snapshot = catalog_service.snapshot()
    models = [
        _openai_model_item(model)
        for model in catalog_service.flatten(snapshot)
        if model.agent_studio_available
    ]
    return {"object": "list", "data": models}


@app.get("/v1/router/model-catalog")
@app.get("/v1/router/model-catalog/")
def router_model_catalog(
    refresh: bool = False,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return _catalog_payload(force_refresh=refresh)


@app.get("/v1/router/sources")
@app.get("/v1/router/sources/")
def router_sources(
    refresh: bool = False,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    snapshot = catalog_service.snapshot(force_refresh=refresh)
    return {
        "generated_at": snapshot.generated_at,
        "sources": [_source_dict(source) for source in snapshot.sources],
    }


@app.post("/v1/chat/completions")
@app.post("/v1/chat/completions/")
async def chat_completions(
    request: Request,
    authorization: str | None = Header(default=None),
):
    _require_router_auth(authorization)
    try:
        payload = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")

    requested_model = str(payload.get("model", "") or "").strip()
    if not requested_model:
        raise HTTPException(status_code=400, detail="model is required")

    routed_model = catalog_service.find_routed_model(requested_model)
    if routed_model is None:
        return _unknown_model_error(requested_model)
    source = catalog_service.source_config(routed_model.source_id)
    if source is None or not source.enabled:
        return _router_error(
            404,
            "source_disabled",
            f"Model source '{routed_model.source_id}' is disabled or missing.",
            model=normalize_router_model_id(requested_model),
            source_id=routed_model.source_id,
        )

    upstream_payload = dict(payload)
    upstream_payload["model"] = routed_model.provider_model_id
    upstream_payload = _normalize_openai_payload(upstream_payload)
    upstream_payload = _apply_sampling_defaults(routed_model, source, upstream_payload)
    if bool(upstream_payload.get("stream", False)):
        return _stream_chat_completion(source, upstream_payload)
    return _post_chat_completion(source, upstream_payload)


def _normalize_openai_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize ADE convenience values before they reach upstream providers."""
    next_payload = dict(payload)
    max_tokens = next_payload.get("max_tokens")
    if isinstance(max_tokens, int | float) and not isinstance(max_tokens, bool) and max_tokens <= 0:
        next_payload.pop("max_tokens", None)
    return next_payload


def _apply_sampling_defaults(
    routed_model: RoutedModel,
    source: RouterSourceConfig,
    payload: dict[str, Any],
) -> dict[str, Any]:
    defaults = routed_model.sampling_defaults or {}
    next_payload = dict(payload)
    for field in ("temperature", "top_p"):
        if _payload_missing(next_payload, field) and defaults.get(field) is not None:
            next_payload[field] = defaults[field]
    if _supports_top_k(routed_model, source) and _payload_missing(next_payload, "top_k") and defaults.get("top_k") is not None:
        next_payload["top_k"] = defaults["top_k"]
    return next_payload


def _payload_missing(payload: dict[str, Any], field: str) -> bool:
    return field not in payload or payload.get(field) is None


def _supports_top_k(routed_model: RoutedModel, source: RouterSourceConfig) -> bool:
    return routed_model.supports_top_k or source.adapter in {"llama_cpp_server", "vllm_openai"}


def _unknown_model_error(requested_model: str) -> JSONResponse:
    normalized = normalize_router_model_id(requested_model)
    source_id = ""
    source_status = None
    try:
        source_id, _ = parse_router_model_id(normalized)
        source_status = catalog_service.source_status(source_id)
    except ValueError:
        pass
    extra: dict[str, Any] = {"model": normalized}
    if source_id:
        extra["source_id"] = source_id
    if source_status is not None:
        extra["source_status"] = source_status.status
        extra["source_detail"] = source_status.detail
    return _router_error(
        404,
        "unknown_or_unavailable_model",
        f"Model '{normalized}' is not currently available through the router.",
        **extra,
    )


def _upstream_headers(source: RouterSourceConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = source.resolve_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _post_chat_completion(source: RouterSourceConfig, payload: dict[str, Any]) -> Response:
    settings = get_settings()
    retrying = Retrying(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(_RETRYABLE_FORWARD_EXCEPTIONS),
        reraise=True,
    )
    try:
        response = None
        for attempt in retrying:
            with attempt:
                with httpx.Client(timeout=settings.request_timeout_seconds) as session:
                    response = session.post(
                        source.chat_completions_url(),
                        json=payload,
                        headers=_upstream_headers(source),
                    )
        if response is None:
            raise RuntimeError("Upstream request did not produce a response")
    except Exception as exc:
        return _router_error(
            502,
            "upstream_unreachable",
            f"Source '{source.id}' could not be reached: {exc}",
            source_id=source.id,
        )
    return _response_from_upstream(response, source_id=source.id)


def _stream_chat_completion(source: RouterSourceConfig, payload: dict[str, Any]) -> StreamingResponse:
    settings = get_settings()
    client = httpx.Client(timeout=settings.request_timeout_seconds)
    stream_context = client.stream(
        "POST",
        source.chat_completions_url(),
        json=payload,
        headers=_upstream_headers(source),
    )
    try:
        response = stream_context.__enter__()
    except Exception as exc:
        client.close()
        return _router_error(502, "upstream_unreachable", f"Source '{source.id}' could not be reached: {exc}")  # type: ignore[return-value]

    def iter_bytes() -> Iterator[bytes]:
        try:
            for chunk in response.iter_bytes():
                yield chunk
        finally:
            stream_context.__exit__(None, None, None)
            client.close()

    media_type = response.headers.get("content-type") or "text/event-stream"
    return StreamingResponse(iter_bytes(), status_code=response.status_code, media_type=media_type)


def _response_from_upstream(response: httpx.Response, *, source_id: str) -> Response:
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type.lower():
        try:
            return JSONResponse(status_code=response.status_code, content=response.json())
        except json.JSONDecodeError:
            pass
    return Response(
        status_code=response.status_code,
        content=response.content,
        media_type=content_type or None,
        headers={"X-Model-Router-Source": source_id},
    )
