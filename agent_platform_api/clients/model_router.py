from __future__ import annotations

import time
from typing import Any

import httpx
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from agent_platform_api.settings import get_settings


_RETRYABLE_ROUTER_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.RemoteProtocolError,
    httpx.WriteError,
)


class ModelRouterClient:
    def __init__(self, *, settings_factory=get_settings):
        self._settings_factory = settings_factory
        self._payload: dict[str, Any] | None = None
        self._expires_at = 0.0

    def invalidate(self) -> None:
        self._payload = None
        self._expires_at = 0.0

    def enabled(self) -> bool:
        settings = self._settings_factory()
        return bool(settings.model_router_v1_base_url())

    def v1_base_url(self) -> str:
        return self._settings_factory().model_router_v1_base_url()

    def api_key(self) -> str:
        return self._settings_factory().resolve_model_router_api_key()

    def catalog(self, *, force_refresh: bool = False) -> dict[str, Any]:
        settings = self._settings_factory()
        if not settings.model_router_v1_base_url():
            raise RuntimeError("AGENT_PLATFORM_MODEL_ROUTER_BASE_URL is not configured")
        if not force_refresh and self._payload is not None and time.monotonic() < self._expires_at:
            return self._payload

        payload = self._fetch_catalog(force_refresh=force_refresh)
        self._payload = payload
        self._expires_at = time.monotonic() + settings.options_cache_ttl_seconds
        return payload

    def _fetch_catalog(self, *, force_refresh: bool) -> dict[str, Any]:
        settings = self._settings_factory()
        url = f"{settings.model_router_v1_base_url()}/router/model-catalog"
        if force_refresh:
            url = f"{url}?refresh=true"
        headers: dict[str, str] = {}
        api_key = settings.resolve_model_router_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        retrying = Retrying(
            stop=stop_after_attempt(2),
            wait=wait_exponential(multiplier=1, min=1, max=4),
            retry=retry_if_exception_type(_RETRYABLE_ROUTER_EXCEPTIONS),
            reraise=True,
        )
        for attempt in retrying:
            with attempt:
                with httpx.Client(timeout=settings.model_discovery_timeout_seconds) as session:
                    response = session.get(url, headers=headers)
                if response.status_code >= 400:
                    raise RuntimeError(f"Model router catalog request failed ({response.status_code}): {response.text}")
                payload = response.json()
                if not isinstance(payload, dict):
                    raise RuntimeError("Model router catalog returned invalid payload")
                return payload
        raise RuntimeError("Model router catalog retry execution did not produce a result")

