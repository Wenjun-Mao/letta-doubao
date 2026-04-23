from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from agent_platform_api.settings import AgentPlatformSettings, ModelSourceConfig, get_settings
from utils.model_allowlist import load_configured_source_allowlist


CatalogSourceStatus = Literal["healthy", "auth_error", "unreachable", "empty"]
CatalogModelType = Literal["llm", "embedding", "unknown"]
_RETRYABLE_DISCOVERY_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.RemoteProtocolError,
    httpx.WriteError,
)
_WINDOWS_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")


class CatalogAuthError(RuntimeError):
    def __init__(self, status_code: int, body: str = ""):
        self.status_code = int(status_code)
        self.body = str(body or "")
        super().__init__(f"Authentication failed ({self.status_code})")


class RetryableCatalogError(RuntimeError):
    """Raised when a provider catalog request should be retried."""


@dataclass(frozen=True)
class CatalogModelRecord:
    provider_model_id: str
    model_type: CatalogModelType


@dataclass(frozen=True)
class CatalogSourceRecord:
    id: str
    label: str
    kind: str
    base_url: str
    enabled_for: tuple[str, ...]
    letta_handle_prefix: str
    status: CatalogSourceStatus
    detail: str
    models: tuple[CatalogModelRecord, ...]
    adapter: str = "generic_openai"
    allowlist_applied: bool | None = None
    allowlist_checked_at: str | None = None
    raw_model_count: int = 0
    filtered_model_count: int = 0


@dataclass(frozen=True)
class CatalogSnapshot:
    generated_at: float
    sources: tuple[CatalogSourceRecord, ...]


@dataclass(frozen=True)
class CatalogEntry:
    source_id: str
    source_label: str
    source_kind: str
    base_url: str
    enabled_for: tuple[str, ...]
    provider_model_id: str
    model_type: CatalogModelType
    model_key: str
    letta_handle: str | None
    source_adapter: str = "generic_openai"


def build_model_key(source_id: str, provider_model_id: str) -> str:
    return f"{str(source_id or '').strip()}::{str(provider_model_id or '').strip()}"


class ModelCatalogService:
    def __init__(self, *, settings_factory=get_settings):
        self._settings_factory = settings_factory
        self._snapshot: CatalogSnapshot | None = None
        self._expires_at = 0.0

    def invalidate(self) -> None:
        self._snapshot = None
        self._expires_at = 0.0

    def snapshot(self, *, force_refresh: bool = False) -> CatalogSnapshot:
        settings = self._settings_factory()
        if (
            not force_refresh
            and self._snapshot is not None
            and time.monotonic() < self._expires_at
        ):
            return self._snapshot

        generated_at = time.time()
        sources = tuple(
            self._discover_source(source, settings=settings)
            for source in settings.model_sources
            if source.enabled
        )
        snapshot = CatalogSnapshot(generated_at=generated_at, sources=sources)
        self._snapshot = snapshot
        self._expires_at = time.monotonic() + settings.options_cache_ttl_seconds
        return snapshot

    def flatten(self, snapshot: CatalogSnapshot) -> list[CatalogEntry]:
        items: list[CatalogEntry] = []
        for source in snapshot.sources:
            if source.status != "healthy":
                continue
            source_config = ModelSourceConfig(
                id=source.id,
                label=source.label,
                base_url=source.base_url,
                kind=source.kind,
                enabled_for=list(source.enabled_for),
                letta_handle_prefix=source.letta_handle_prefix,
                api_key_env="",
                api_key_secret="",
            )
            for model in source.models:
                items.append(
                    CatalogEntry(
                        source_id=source.id,
                        source_label=source.label,
                        source_kind=source.kind,
                        base_url=source.base_url,
                        enabled_for=source.enabled_for,
                        provider_model_id=model.provider_model_id,
                        model_type=model.model_type,
                        model_key=build_model_key(source.id, model.provider_model_id),
                        letta_handle=source_config.derive_letta_handle(model.provider_model_id),
                        source_adapter=source.adapter,
                    )
                )
        return items

    def _discover_source(
        self,
        source: ModelSourceConfig,
        *,
        settings: AgentPlatformSettings,
    ) -> CatalogSourceRecord:
        try:
            payload = self._fetch_models_payload(source, settings=settings)
            records = tuple(self._extract_model_records(payload))
            if not records:
                fallback_records = tuple(
                    self._probe_active_model_records_from_chat_completion(source, settings=settings)
                )
                if fallback_records:
                    filtered_records, allowlist_applied, allowlist_checked_at, raw_model_count, detail = (
                        self._apply_source_allowlist(source, fallback_records, raw_model_count=0)
                    )
                    return CatalogSourceRecord(
                        id=source.id,
                        label=source.label,
                        kind=source.kind,
                        base_url=source.normalized_base_url(),
                        enabled_for=tuple(source.enabled_for),
                        letta_handle_prefix=source.letta_handle_prefix,
                        status="healthy",
                        detail=(
                            "Provider catalog empty; active model probed via chat completions fallback."
                            if detail == "ok"
                            else f"Provider catalog empty; fallback model probed. {detail}"
                        ),
                        models=filtered_records,
                        adapter=source.adapter,
                        allowlist_applied=allowlist_applied,
                        allowlist_checked_at=allowlist_checked_at,
                        raw_model_count=raw_model_count,
                        filtered_model_count=len(filtered_records),
                    )
                return CatalogSourceRecord(
                    id=source.id,
                    label=source.label,
                    kind=source.kind,
                    base_url=source.normalized_base_url(),
                    enabled_for=tuple(source.enabled_for),
                    letta_handle_prefix=source.letta_handle_prefix,
                    status="empty",
                    detail="No models returned from provider catalog.",
                    models=(),
                    adapter=source.adapter,
                    raw_model_count=0,
                    filtered_model_count=0,
                )
            filtered_records, allowlist_applied, allowlist_checked_at, raw_model_count, detail = (
                self._apply_source_allowlist(source, records)
            )
            return CatalogSourceRecord(
                id=source.id,
                label=source.label,
                kind=source.kind,
                base_url=source.normalized_base_url(),
                enabled_for=tuple(source.enabled_for),
                letta_handle_prefix=source.letta_handle_prefix,
                status="healthy",
                detail=detail,
                models=filtered_records,
                adapter=source.adapter,
                allowlist_applied=allowlist_applied,
                allowlist_checked_at=allowlist_checked_at,
                raw_model_count=raw_model_count,
                filtered_model_count=len(filtered_records),
            )
        except CatalogAuthError as exc:
            return CatalogSourceRecord(
                id=source.id,
                label=source.label,
                kind=source.kind,
                base_url=source.normalized_base_url(),
                enabled_for=tuple(source.enabled_for),
                letta_handle_prefix=source.letta_handle_prefix,
                status="auth_error",
                detail=f"Authentication failed ({exc.status_code}).",
                models=(),
                adapter=source.adapter,
                raw_model_count=0,
                filtered_model_count=0,
            )
        except Exception as exc:
            return CatalogSourceRecord(
                id=source.id,
                label=source.label,
                kind=source.kind,
                base_url=source.normalized_base_url(),
                enabled_for=tuple(source.enabled_for),
                letta_handle_prefix=source.letta_handle_prefix,
                status="unreachable",
                detail=str(exc),
                models=(),
                adapter=source.adapter,
                raw_model_count=0,
                filtered_model_count=0,
            )

    def _apply_source_allowlist(
        self,
        source: ModelSourceConfig,
        records: tuple[CatalogModelRecord, ...],
        *,
        raw_model_count: int | None = None,
    ) -> tuple[tuple[CatalogModelRecord, ...], bool | None, str | None, int, str]:
        resolved_raw_model_count = len(records) if raw_model_count is None else int(raw_model_count)
        allowlist = load_configured_source_allowlist(source.id)
        if allowlist is None:
            return records, None, None, resolved_raw_model_count, "ok"

        if not allowlist.applied:
            return (
                (),
                False,
                allowlist.checked_at,
                resolved_raw_model_count,
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
            resolved_raw_model_count,
            (
                "ok"
                if resolved_raw_model_count == len(filtered_records)
                else (
                    f"Allowlist applied: {len(filtered_records)} of "
                    f"{resolved_raw_model_count} catalog entries remain selectable."
                )
            ),
        )

    def _probe_active_model_records_from_chat_completion(
        self,
        source: ModelSourceConfig,
        *,
        settings: AgentPlatformSettings,
    ) -> list[CatalogModelRecord]:
        retrying = Retrying(
            stop=stop_after_attempt(2),
            wait=wait_exponential(multiplier=1, min=1, max=4),
            retry=retry_if_exception_type((RetryableCatalogError, *_RETRYABLE_DISCOVERY_EXCEPTIONS)),
            reraise=True,
        )
        for attempt in retrying:
            with attempt:
                return self._probe_active_model_records_from_chat_completion_once(
                    source,
                    settings=settings,
                )
        return []

    def _probe_active_model_records_from_chat_completion_once(
        self,
        source: ModelSourceConfig,
        *,
        settings: AgentPlatformSettings,
    ) -> list[CatalogModelRecord]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        api_key = source.resolve_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": False,
        }

        with httpx.Client(timeout=settings.model_discovery_timeout_seconds) as session:
            response = session.post(source.chat_completions_url(), headers=headers, json=payload)

        if response.status_code in {401, 403}:
            raise CatalogAuthError(response.status_code, response.text)
        if response.status_code in {429, 500, 502, 503, 504}:
            raise RetryableCatalogError(f"Temporary provider failure ({response.status_code})")
        if response.status_code >= 400:
            return []

        try:
            payload = response.json()
        except Exception as exc:
            raise RuntimeError("Provider chat-completions fallback returned non-JSON payload") from exc

        model_id = ""
        if isinstance(payload, dict):
            model_id = str(payload.get("model") or "").strip()

        normalized_model_id = self._normalize_probed_model_id(model_id)
        if not normalized_model_id:
            return []
        return [CatalogModelRecord(provider_model_id=normalized_model_id, model_type="llm")]

    def _fetch_models_payload(
        self,
        source: ModelSourceConfig,
        *,
        settings: AgentPlatformSettings,
    ) -> Any:
        retrying = Retrying(
            stop=stop_after_attempt(2),
            wait=wait_exponential(multiplier=1, min=1, max=4),
            retry=retry_if_exception_type((RetryableCatalogError, *_RETRYABLE_DISCOVERY_EXCEPTIONS)),
            reraise=True,
        )
        for attempt in retrying:
            with attempt:
                return self._fetch_models_payload_once(source, settings=settings)
        raise RuntimeError("Model catalog discovery did not produce a result")

    def _fetch_models_payload_once(
        self,
        source: ModelSourceConfig,
        *,
        settings: AgentPlatformSettings,
    ) -> Any:
        headers: dict[str, str] = {}
        api_key = source.resolve_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        with httpx.Client(timeout=settings.model_discovery_timeout_seconds) as session:
            response = session.get(source.models_endpoint(), headers=headers)

        if response.status_code in {401, 403}:
            raise CatalogAuthError(response.status_code, response.text)
        if response.status_code in {429, 500, 502, 503, 504}:
            raise RetryableCatalogError(f"Temporary provider failure ({response.status_code})")
        if response.status_code >= 400:
            raise RuntimeError(f"Provider catalog request failed ({response.status_code}): {response.text}")

        try:
            return response.json()
        except Exception as exc:
            raise RuntimeError("Provider catalog returned non-JSON payload") from exc

    @staticmethod
    def _extract_model_records(payload: Any) -> list[CatalogModelRecord]:
        if isinstance(payload, dict):
            raw_items = payload.get("data")
            if not isinstance(raw_items, list):
                raw_items = payload.get("models")
            if not isinstance(raw_items, list):
                raw_items = []
        elif isinstance(payload, list):
            raw_items = payload
        else:
            raw_items = []

        records: list[CatalogModelRecord] = []
        seen: set[str] = set()
        for item in raw_items:
            model_id = ""
            model_type: CatalogModelType = "unknown"
            if isinstance(item, dict):
                model_id = str(item.get("id") or item.get("model") or item.get("name") or "").strip()
                model_type = ModelCatalogService._detect_model_type(item, model_id)
            elif isinstance(item, str):
                model_id = str(item).strip()
                model_type = ModelCatalogService._detect_model_type({}, model_id)

            model_id = ModelCatalogService._normalize_probed_model_id(model_id)
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            records.append(CatalogModelRecord(provider_model_id=model_id, model_type=model_type))
        return records

    @staticmethod
    def _detect_model_type(item: dict[str, Any], model_id: str) -> CatalogModelType:
        signals = [
            str(item.get("type", "") or ""),
            str(item.get("model_type", "") or ""),
            str(item.get("object", "") or ""),
            str(item.get("mode", "") or ""),
            str(model_id or ""),
        ]
        normalized = " ".join(signal.lower() for signal in signals if signal)
        if "embedding" in normalized or "embed" in normalized:
            return "embedding"
        if model_id:
            return "llm"
        return "unknown"

    @staticmethod
    def _normalize_probed_model_id(model_id: str) -> str:
        raw_model_id = str(model_id or "").strip()
        if not raw_model_id:
            return ""
        if not ModelCatalogService._looks_like_filesystem_path(raw_model_id):
            return raw_model_id

        basename = raw_model_id.replace("\\", "/").rsplit("/", 1)[-1].strip()
        lowered = basename.lower()
        if lowered.endswith(".gguf"):
            basename = basename[:-5]
            lowered = basename.lower()
        if lowered.endswith("-gguf"):
            basename = basename[:-5]
        return basename.strip().lower()

    @staticmethod
    def _looks_like_filesystem_path(value: str) -> bool:
        candidate = str(value or "").strip()
        if not candidate:
            return False
        if "\\" in candidate:
            return True
        return bool(_WINDOWS_PATH_RE.match(candidate))
