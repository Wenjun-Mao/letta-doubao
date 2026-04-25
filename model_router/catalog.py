from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from model_router.settings import (
    ModelRouterSettings,
    RouterModelType,
    RouterSourceConfig,
    RouterSourceStatus,
    get_settings,
)
from ade_core.model_allowlist import load_configured_source_allowlist


_RETRYABLE_DISCOVERY_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.RemoteProtocolError,
    httpx.WriteError,
)
_KNOWN_HANDLE_PREFIXES = ("lmstudio_openai/", "openai-proxy/", "openai/", "anthropic/")
_WINDOWS_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")


class RouterAuthError(RuntimeError):
    def __init__(self, status_code: int, body: str = ""):
        self.status_code = int(status_code)
        self.body = str(body or "")
        super().__init__(f"Authentication failed ({self.status_code})")


class RetryableRouterDiscoveryError(RuntimeError):
    """Raised when a source discovery request should be retried."""


@dataclass(frozen=True)
class RouterModelRecord:
    provider_model_id: str
    model_type: RouterModelType


@dataclass(frozen=True)
class RouterSourceSnapshot:
    id: str
    label: str
    kind: str
    adapter: str
    base_url: str
    module_visibility: tuple[str, ...]
    status: RouterSourceStatus
    detail: str
    models: tuple[RouterModelRecord, ...]
    allowlist_applied: bool | None = None
    allowlist_checked_at: str | None = None
    raw_model_count: int = 0
    filtered_model_count: int = 0


@dataclass(frozen=True)
class RouterCatalogSnapshot:
    generated_at: float
    sources: tuple[RouterSourceSnapshot, ...]


@dataclass(frozen=True)
class RoutedModel:
    router_model_id: str
    source_id: str
    source_label: str
    source_kind: str
    source_adapter: str
    source_base_url: str
    module_visibility: tuple[str, ...]
    provider_model_id: str
    model_type: RouterModelType
    letta_handle: str | None
    agent_studio_available: bool
    comment_lab_available: bool
    label_lab_available: bool
    structured_output_mode: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "router_model_id": self.router_model_id,
            "model_key": self.router_model_id,
            "source_id": self.source_id,
            "source_label": self.source_label,
            "source_kind": self.source_kind,
            "source_adapter": self.source_adapter,
            "source_base_url": self.source_base_url,
            "module_visibility": list(self.module_visibility),
            "provider_model_id": self.provider_model_id,
            "model_type": self.model_type,
            "letta_handle": self.letta_handle,
            "agent_studio_available": self.agent_studio_available,
            "comment_lab_available": self.comment_lab_available,
            "label_lab_available": self.label_lab_available,
            "structured_output_mode": self.structured_output_mode,
        }


def build_router_model_id(source_id: str, provider_model_id: str) -> str:
    return f"{str(source_id or '').strip()}::{str(provider_model_id or '').strip()}"


def normalize_router_model_id(value: str) -> str:
    resolved = str(value or "").strip()
    lowered = resolved.lower()
    for prefix in _KNOWN_HANDLE_PREFIXES:
        if lowered.startswith(prefix):
            return resolved[len(prefix) :].strip()
    return resolved


def parse_router_model_id(value: str) -> tuple[str, str]:
    model_id = normalize_router_model_id(value)
    if "::" not in model_id:
        raise ValueError("Router model id must use '<source_id>::<provider_model_id>'")
    source_id, provider_model_id = model_id.split("::", 1)
    source_id = source_id.strip()
    provider_model_id = provider_model_id.strip()
    if not source_id or not provider_model_id:
        raise ValueError("Router model id must include source id and provider model id")
    return source_id, provider_model_id


class RouterCatalogService:
    def __init__(self, *, settings_factory=get_settings):
        self._settings_factory = settings_factory
        self._snapshot: RouterCatalogSnapshot | None = None
        self._expires_at = 0.0

    def invalidate(self) -> None:
        self._snapshot = None
        self._expires_at = 0.0

    def snapshot(self, *, force_refresh: bool = False) -> RouterCatalogSnapshot:
        settings = self._settings_factory()
        if not force_refresh and self._snapshot is not None and time.monotonic() < self._expires_at:
            return self._snapshot

        generated_at = time.time()
        sources = tuple(
            self._discover_source(source, settings=settings)
            for source in settings.sources
            if source.enabled
        )
        snapshot = RouterCatalogSnapshot(generated_at=generated_at, sources=sources)
        self._snapshot = snapshot
        self._expires_at = time.monotonic() + settings.cache_ttl_seconds
        return snapshot

    def flatten(self, snapshot: RouterCatalogSnapshot) -> list[RoutedModel]:
        models: list[RoutedModel] = []
        for source in snapshot.sources:
            if source.status != "healthy":
                continue
            for model in source.models:
                if not model.provider_model_id:
                    continue
                is_llm = model.model_type == "llm"
                router_model_id = build_router_model_id(source.id, model.provider_model_id)
                agent_studio_available = is_llm and "agent_studio" in source.module_visibility
                label_lab_available = is_llm and "label_lab" in source.module_visibility
                structured_output_mode = (
                    self._structured_output_mode(source) if label_lab_available else None
                )
                models.append(
                    RoutedModel(
                        router_model_id=router_model_id,
                        source_id=source.id,
                        source_label=source.label,
                        source_kind=source.kind,
                        source_adapter=source.adapter,
                        source_base_url=source.base_url,
                        module_visibility=source.module_visibility,
                        provider_model_id=model.provider_model_id,
                        model_type=model.model_type,
                        letta_handle=(
                            f"openai-proxy/{router_model_id}" if agent_studio_available else None
                        ),
                        agent_studio_available=agent_studio_available,
                        comment_lab_available=is_llm and "comment_lab" in source.module_visibility,
                        label_lab_available=label_lab_available,
                        structured_output_mode=structured_output_mode,
                    )
                )
        return models

    def find_routed_model(
        self,
        router_model_id: str,
        *,
        force_refresh: bool = False,
    ) -> RoutedModel | None:
        normalized = normalize_router_model_id(router_model_id)
        snapshot = self.snapshot(force_refresh=force_refresh)
        return next((model for model in self.flatten(snapshot) if model.router_model_id == normalized), None)

    def source_config(self, source_id: str) -> RouterSourceConfig | None:
        settings = self._settings_factory()
        return next((source for source in settings.sources if source.id == source_id), None)

    def source_status(self, source_id: str) -> RouterSourceSnapshot | None:
        snapshot = self.snapshot()
        return next((source for source in snapshot.sources if source.id == source_id), None)

    def _discover_source(
        self,
        source: RouterSourceConfig,
        *,
        settings: ModelRouterSettings,
    ) -> RouterSourceSnapshot:
        try:
            payload = self._fetch_models_payload(source, settings=settings)
            records = tuple(self._extract_model_records(payload))
            filtered_records, allowlist_applied, allowlist_checked_at, raw_model_count, detail = (
                self._apply_source_allowlist(source, records)
            )
            if not records:
                return self._source_snapshot(
                    source,
                    status="empty",
                    detail="No models returned from provider catalog.",
                    models=(),
                    raw_model_count=0,
                    filtered_model_count=0,
                )
            return self._source_snapshot(
                source,
                status="healthy",
                detail=detail,
                models=filtered_records,
                allowlist_applied=allowlist_applied,
                allowlist_checked_at=allowlist_checked_at,
                raw_model_count=raw_model_count,
                filtered_model_count=len(filtered_records),
            )
        except RouterAuthError as exc:
            return self._source_snapshot(
                source,
                status="auth_error",
                detail=f"Authentication failed ({exc.status_code}).",
                models=(),
            )
        except Exception as exc:
            return self._source_snapshot(
                source,
                status="unreachable",
                detail=str(exc),
                models=(),
            )

    def _source_snapshot(
        self,
        source: RouterSourceConfig,
        *,
        status: RouterSourceStatus,
        detail: str,
        models: tuple[RouterModelRecord, ...],
        allowlist_applied: bool | None = None,
        allowlist_checked_at: str | None = None,
        raw_model_count: int = 0,
        filtered_model_count: int = 0,
    ) -> RouterSourceSnapshot:
        return RouterSourceSnapshot(
            id=source.id,
            label=source.label,
            kind=source.kind,
            adapter=source.adapter,
            base_url=source.normalized_base_url(),
            module_visibility=source.visible_modules(),
            status=status,
            detail=detail,
            models=models,
            allowlist_applied=allowlist_applied,
            allowlist_checked_at=allowlist_checked_at,
            raw_model_count=raw_model_count,
            filtered_model_count=filtered_model_count,
        )

    def _fetch_models_payload(
        self,
        source: RouterSourceConfig,
        *,
        settings: ModelRouterSettings,
    ) -> dict[str, Any]:
        retrying = Retrying(
            stop=stop_after_attempt(2),
            wait=wait_exponential(multiplier=1, min=1, max=4),
            retry=retry_if_exception_type((RetryableRouterDiscoveryError, *_RETRYABLE_DISCOVERY_EXCEPTIONS)),
            reraise=True,
        )
        for attempt in retrying:
            with attempt:
                return self._fetch_models_payload_once(source, settings=settings)
        raise RuntimeError("Model-router discovery retry execution did not produce a result")

    def _fetch_models_payload_once(
        self,
        source: RouterSourceConfig,
        *,
        settings: ModelRouterSettings,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {}
        api_key = source.resolve_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        with httpx.Client(timeout=settings.discovery_timeout_seconds) as session:
            response = session.get(source.models_endpoint(), headers=headers)

        if response.status_code in {401, 403}:
            raise RouterAuthError(response.status_code, response.text)
        if response.status_code >= 500 or response.status_code == 429:
            raise RetryableRouterDiscoveryError(
                f"Provider catalog temporary failure ({response.status_code}): {response.text}"
            )
        if response.status_code >= 400:
            raise RuntimeError(f"Provider catalog request failed ({response.status_code}): {response.text}")

        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Provider catalog returned invalid payload")
        return payload

    def _apply_source_allowlist(
        self,
        source: RouterSourceConfig,
        records: tuple[RouterModelRecord, ...],
    ) -> tuple[tuple[RouterModelRecord, ...], bool | None, str | None, int, str]:
        raw_model_count = len(records)
        allowlist = load_configured_source_allowlist(source.id)
        if allowlist is None:
            return records, None, None, raw_model_count, "ok"
        if not allowlist.applied:
            return (
                (),
                False,
                allowlist.checked_at,
                raw_model_count,
                f"Allowlist unavailable for source '{source.id}': {allowlist.detail}",
            )
        filtered_records = tuple(
            record
            for record in records
            if record.model_type == "llm" and record.provider_model_id in allowlist.usable_models
        )
        return (
            filtered_records,
            True,
            allowlist.checked_at,
            raw_model_count,
            (
                "ok"
                if raw_model_count == len(filtered_records)
                else f"Allowlist applied: {len(filtered_records)} of {raw_model_count} catalog entries remain selectable."
            ),
        )

    @staticmethod
    def _extract_model_records(payload: dict[str, Any]) -> list[RouterModelRecord]:
        raw_models = payload.get("data")
        if raw_models is None:
            raw_models = payload.get("models")
        if not isinstance(raw_models, list):
            return []

        records: list[RouterModelRecord] = []
        seen: set[str] = set()
        for item in raw_models:
            model_id = ""
            model_type: RouterModelType = "unknown"
            if isinstance(item, str):
                model_id = item
            elif isinstance(item, dict):
                model_id = str(
                    item.get("id")
                    or item.get("model")
                    or item.get("name")
                    or item.get("root")
                    or ""
                )
                model_type = RouterCatalogService._detect_model_type(item, model_id=model_id)
            model_id = RouterCatalogService._normalize_model_id(model_id)
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            if model_type == "unknown":
                model_type = RouterCatalogService._detect_model_type({}, model_id=model_id)
            records.append(RouterModelRecord(provider_model_id=model_id, model_type=model_type))
        return records

    @staticmethod
    def _detect_model_type(item: dict[str, Any], *, model_id: str) -> RouterModelType:
        haystack = " ".join(
            str(value or "").lower()
            for value in (
                model_id,
                item.get("type"),
                item.get("object"),
                item.get("model_type"),
                item.get("api_model_type"),
            )
        )
        if "embedding" in haystack or "embed" in haystack:
            return "embedding"
        if "chat" in haystack or "llm" in haystack or "model" in haystack:
            return "llm"
        return "llm"

    @staticmethod
    def _normalize_model_id(value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if _WINDOWS_PATH_RE.match(text) or "\\" in text:
            text = text.replace("\\", "/").rstrip("/").split("/")[-1]
        if text.lower().endswith(".gguf"):
            text = text[:-5]
        return text.strip()

    @staticmethod
    def _structured_output_mode(source: RouterSourceSnapshot) -> str:
        if source.adapter == "llama_cpp_server":
            return "json_schema"
        if source.adapter == "ark_openai" or source.id == "ark":
            return "strict_json_schema"
        return "best_effort_prompt_json"
