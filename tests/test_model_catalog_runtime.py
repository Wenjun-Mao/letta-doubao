from __future__ import annotations

from types import SimpleNamespace

import pytest

import agent_platform_api.runtime as runtime
from agent_platform_api.settings import ModelSourceConfig
from utils.model_catalog import CatalogAuthError, CatalogModelRecord, ModelCatalogService


def _settings_with_sources(*sources: ModelSourceConfig) -> SimpleNamespace:
    return SimpleNamespace(
        model_sources=list(sources),
        options_cache_ttl_seconds=30,
        model_discovery_timeout_seconds=5.0,
    )


def test_model_catalog_service_unions_healthy_sources_and_preserves_source_scoped_keys(monkeypatch) -> None:
    local = ModelSourceConfig(
        id="local",
        label="Local",
        base_url="http://127.0.0.1:1234/v1",
        kind="openai-compatible",
        enabled_for=["chat", "comment"],
        letta_handle_prefix="lmstudio_openai",
        api_key_env="",
        api_key_secret="",
    )
    ark = ModelSourceConfig(
        id="ark",
        label="Ark",
        base_url="https://ark.example/v3",
        kind="openai-compatible",
        enabled_for=["comment"],
        letta_handle_prefix="openai-proxy",
        api_key_env="OPENAI_API_KEY",
        api_key_secret="ark-api-key",
    )
    blocked = ModelSourceConfig(
        id="blocked",
        label="Blocked",
        base_url="https://blocked.example/v1",
        kind="openai-compatible",
        enabled_for=["comment"],
        letta_handle_prefix="",
        api_key_env="",
        api_key_secret="",
    )
    service = ModelCatalogService(settings_factory=lambda: _settings_with_sources(local, ark, blocked))

    def fake_fetch(source: ModelSourceConfig, *, settings) -> dict[str, object]:
        if source.id == "local":
            return {"data": [{"id": "shared-model"}, {"id": "local-model"}]}
        if source.id == "ark":
            return {"data": [{"id": "shared-model"}, {"id": "ark-only"}]}
        raise CatalogAuthError(401)

    monkeypatch.setattr(service, "_fetch_models_payload", fake_fetch)

    snapshot = service.snapshot(force_refresh=True)
    assert [source.status for source in snapshot.sources] == ["healthy", "healthy", "auth_error"]

    entries = service.flatten(snapshot)
    keys = {entry.model_key for entry in entries}
    assert "local::shared-model" in keys
    assert "ark::shared-model" in keys
    assert not any(entry.source_id == "blocked" for entry in entries)


def test_resolve_comment_model_selection_requires_model_key_when_legacy_name_is_ambiguous(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime,
        "_enriched_catalog_items",
        lambda force_refresh=False: [
            {
                "model_key": "local::shared-model",
                "source_id": "local",
                "source_label": "Local",
                "source_kind": "openai-compatible",
                "base_url": "http://127.0.0.1:1234/v1",
                "enabled_for": ["comment"],
                "provider_model_id": "shared-model",
                "model_type": "llm",
                "letta_handle": "lmstudio_openai/shared-model",
                "agent_studio_available": False,
                "comment_lab_available": True,
            },
            {
                "model_key": "ark::shared-model",
                "source_id": "ark",
                "source_label": "Ark",
                "source_kind": "openai-compatible",
                "base_url": "https://ark.example/v3",
                "enabled_for": ["comment"],
                "provider_model_id": "shared-model",
                "model_type": "llm",
                "letta_handle": "openai-proxy/shared-model",
                "agent_studio_available": False,
                "comment_lab_available": True,
            },
        ],
    )
    monkeypatch.setattr(
        runtime,
        "get_settings",
        lambda: SimpleNamespace(
            model_sources=[
                SimpleNamespace(id="local", resolve_api_key=lambda: ""),
                SimpleNamespace(id="ark", resolve_api_key=lambda: ""),
            ]
        ),
    )

    with pytest.raises(ValueError, match="Ambiguous model selector"):
        runtime.resolve_comment_model_selection(legacy_model="shared-model")


def test_model_catalog_service_probes_active_model_when_catalog_is_empty(monkeypatch) -> None:
    local = ModelSourceConfig(
        id="local",
        label="Local",
        base_url="http://127.0.0.1:1234/v1",
        kind="openai-compatible",
        enabled_for=["chat", "comment"],
        letta_handle_prefix="lmstudio_openai",
        api_key_env="UNSLOTH_API_KEY",
        api_key_secret="unsloth-api-key",
    )
    service = ModelCatalogService(settings_factory=lambda: _settings_with_sources(local))

    monkeypatch.setattr(service, "_fetch_models_payload", lambda source, *, settings: {"data": []})
    monkeypatch.setattr(
        service,
        "_probe_active_model_records_from_chat_completion",
        lambda source, *, settings: [CatalogModelRecord(provider_model_id="gemma-4-31b-it", model_type="llm")],
    )

    snapshot = service.snapshot(force_refresh=True)

    assert snapshot.sources[0].status == "healthy"
    assert snapshot.sources[0].models == (
        CatalogModelRecord(provider_model_id="gemma-4-31b-it", model_type="llm"),
    )
    assert "fallback" in snapshot.sources[0].detail.lower()


def test_normalize_probed_model_id_reduces_windows_model_path() -> None:
    assert (
        ModelCatalogService._normalize_probed_model_id(
            r"F:\LM Studio\models\unsloth\gemma-4-31B-it-GGUF"
        )
        == "gemma-4-31b-it"
    )


def test_extract_model_records_normalizes_windows_path_ids() -> None:
    records = ModelCatalogService._extract_model_records(
        {"data": [{"id": r"F:\LM Studio\models\unsloth\gemma-4-31B-it-GGUF"}]}
    )

    assert records == [CatalogModelRecord(provider_model_id="gemma-4-31b-it", model_type="llm")]
