from __future__ import annotations

from types import SimpleNamespace

from model_router.catalog import (
    RouterCatalogService,
    RouterModelRecord,
    build_router_model_id,
    normalize_router_model_id,
    parse_router_model_id,
)
from model_router.settings import RouterSourceConfig
from ade_core.model_allowlist import SourceAllowlistLoadResult
import model_router.catalog as router_catalog_module


def _settings_with_sources(*sources: RouterSourceConfig) -> SimpleNamespace:
    return SimpleNamespace(
        sources=list(sources),
        cache_ttl_seconds=30,
        discovery_timeout_seconds=5.0,
    )


def test_router_catalog_unions_healthy_sources_and_visibility(monkeypatch) -> None:
    llama = RouterSourceConfig(
        id="local_llama_server",
        label="Local llama-server",
        base_url="http://127.0.0.1:8081/v1",
        adapter="llama_cpp_server",
        enabled_for=["agent_studio", "comment_lab", "label_lab"],
    )
    ark = RouterSourceConfig(
        id="ark",
        label="Ark",
        base_url="https://ark.example/api/v3",
        adapter="ark_openai",
        enabled_for=["agent_studio", "comment_lab"],
    )
    service = RouterCatalogService(settings_factory=lambda: _settings_with_sources(llama, ark))
    monkeypatch.setattr(router_catalog_module, "load_configured_source_allowlist", lambda source_id: None)

    def fake_fetch(source: RouterSourceConfig, *, settings) -> dict[str, object]:
        if source.id == "local_llama_server":
            return {"data": [{"id": "gemma4"}]}
        return {"data": [{"id": "doubao-seed-1-8-251228"}]}

    monkeypatch.setattr(service, "_fetch_models_payload", fake_fetch)

    snapshot = service.snapshot(force_refresh=True)
    models = service.flatten(snapshot)

    assert [source.status for source in snapshot.sources] == ["healthy", "healthy"]
    assert [model.router_model_id for model in models] == [
        "local_llama_server::gemma4",
        "ark::doubao-seed-1-8-251228",
    ]
    assert models[0].letta_handle == "openai-proxy/local_llama_server::gemma4"
    assert models[0].label_lab_available is True
    assert models[0].structured_output_mode == "json_schema"
    assert models[1].label_lab_available is False


def test_router_catalog_filters_ark_through_chat_allowlist(monkeypatch) -> None:
    ark = RouterSourceConfig(
        id="ark",
        label="Ark",
        base_url="https://ark.example/api/v3",
        adapter="ark_openai",
        enabled_for=["agent_studio", "comment_lab"],
    )
    service = RouterCatalogService(settings_factory=lambda: _settings_with_sources(ark))
    monkeypatch.setattr(
        router_catalog_module,
        "load_configured_source_allowlist",
        lambda source_id: SourceAllowlistLoadResult(
            source_id="ark",
            path=SimpleNamespace(),
            applied=True,
            checked_at="2026-04-22T12:00:00+00:00",
            probe_mode="chat-probe",
            raw_model_count=3,
            usable_models=frozenset({"doubao-seed-1-8-251228"}),
            detail="ok",
        ),
    )
    monkeypatch.setattr(
        service,
        "_fetch_models_payload",
        lambda source, *, settings: {
            "data": [
                {"id": "doubao-seed-1-8-251228"},
                {"id": "deepseek-v3-250324"},
                {"id": "doubao-embedding-text-240715"},
            ]
        },
    )

    snapshot = service.snapshot(force_refresh=True)
    ark_source = snapshot.sources[0]
    models = service.flatten(snapshot)

    assert ark_source.allowlist_applied is True
    assert ark_source.raw_model_count == 3
    assert ark_source.filtered_model_count == 1
    assert [model.router_model_id for model in models] == ["ark::doubao-seed-1-8-251228"]


def test_router_model_id_helpers() -> None:
    assert build_router_model_id("local", "gemma4") == "local::gemma4"
    assert normalize_router_model_id("openai-proxy/local::gemma4") == "local::gemma4"
    assert parse_router_model_id("openai-proxy/local::gemma4") == ("local", "gemma4")


def test_extract_model_records_normalizes_gguf_paths() -> None:
    records = RouterCatalogService._extract_model_records(
        {"data": [{"id": r"F:\LM Studio\models\gemma-4-26B-it-Q4_K_M.gguf"}]}
    )

    assert records == [
        RouterModelRecord(provider_model_id="gemma-4-26B-it-Q4_K_M", model_type="llm")
    ]
