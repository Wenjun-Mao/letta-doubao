from __future__ import annotations

from typing import Any

import httpx
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential


class ApiRequestError(RuntimeError):
    pass


class TransientApiError(ApiRequestError):
    pass


class AgentPlatformApiClient:
    def __init__(self, *, base_url: str, timeout_seconds: float, retry_count: int):
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._retry_count = retry_count

    def __enter__(self) -> AgentPlatformApiClient:
        self._client = httpx.Client(base_url=self._base_url, timeout=self._timeout_seconds)
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self._client.close()

    def options(self) -> dict[str, Any]:
        return self._request_json("GET", "/api/v1/options", params={"scenario": "chat", "refresh": "true"})

    def create_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json("POST", "/api/v1/agents", json=payload)

    def chat(self, *, agent_id: str, message: str, timeout_seconds: float, retry_count: int) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/api/v1/chat",
            json={
                "agent_id": agent_id,
                "message": message,
                "timeout_seconds": timeout_seconds,
                "retry_count": retry_count,
            },
        )

    def persistent_state(self, agent_id: str) -> dict[str, Any]:
        return self._request_json("GET", f"/api/v1/agents/{agent_id}/persistent_state", params={"limit": "500"})

    def archive_agent(self, agent_id: str) -> dict[str, Any]:
        return self._request_json("POST", f"/api/v1/platform/agents/{agent_id}/archive")

    def purge_agent(self, agent_id: str) -> dict[str, Any]:
        return self._request_json("DELETE", f"/api/v1/platform/agents/{agent_id}/purge")

    def _request_json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        retrying = Retrying(
            stop=stop_after_attempt(max(1, self._retry_count + 1)),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError, TransientApiError)),
            reraise=True,
        )
        for attempt in retrying:
            with attempt:
                response = self._client.request(method, path, **kwargs)
                if response.status_code >= 500:
                    raise TransientApiError(f"{method} {path} failed with {response.status_code}: {response.text}")
                if response.status_code >= 400:
                    raise ApiRequestError(f"{method} {path} failed with {response.status_code}: {response.text}")
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ApiRequestError(f"{method} {path} returned a non-object JSON payload")
                return payload
        raise ApiRequestError(f"{method} {path} retry execution did not produce a result")

