from __future__ import annotations

import asyncio

import agent_platform_api.runtime as runtime
from agent_platform_api.routers import core, platform_meta
from utils.model_catalog import CatalogEntry, CatalogModelRecord, CatalogSnapshot, CatalogSourceRecord


def _snapshot_fixture() -> tuple[CatalogSnapshot, list[CatalogEntry]]:
    snapshot = CatalogSnapshot(
        generated_at=123.0,
        sources=(
            CatalogSourceRecord(
                id="local",
                label="Local Unsloth",
                kind="openai-compatible",
                base_url="http://127.0.0.1:1234/v1",
                enabled_for=("chat", "comment"),
                letta_handle_prefix="lmstudio_openai",
                status="healthy",
                detail="ok",
                models=(
                    CatalogModelRecord(provider_model_id="doubao-seed-1-8-251228", model_type="llm"),
                    CatalogModelRecord(provider_model_id="local-model", model_type="llm"),
                    CatalogModelRecord(provider_model_id="local-embedding", model_type="embedding"),
                ),
            ),
            CatalogSourceRecord(
                id="blocked",
                label="Blocked Source",
                kind="openai-compatible",
                base_url="http://127.0.0.1:5678/v1",
                enabled_for=("comment",),
                letta_handle_prefix="lmstudio_openai",
                status="auth_error",
                detail="Authentication failed (401).",
                models=(),
            ),
        ),
    )
    entries = [
        CatalogEntry(
            source_id="local",
            source_label="Local Unsloth",
            source_kind="openai-compatible",
            base_url="http://127.0.0.1:1234/v1",
            enabled_for=("chat", "comment"),
            provider_model_id="doubao-seed-1-8-251228",
            model_type="llm",
            model_key="local::doubao-seed-1-8-251228",
            letta_handle="openai-proxy/doubao-seed-1-8-251228",
        ),
        CatalogEntry(
            source_id="local",
            source_label="Local Unsloth",
            source_kind="openai-compatible",
            base_url="http://127.0.0.1:1234/v1",
            enabled_for=("chat", "comment"),
            provider_model_id="local-model",
            model_type="llm",
            model_key="local::local-model",
            letta_handle="lmstudio_openai/local-model",
        ),
        CatalogEntry(
            source_id="local",
            source_label="Local Unsloth",
            source_kind="openai-compatible",
            base_url="http://127.0.0.1:1234/v1",
            enabled_for=("chat", "comment"),
            provider_model_id="local-embedding",
            model_type="embedding",
            model_key="local::local-embedding",
            letta_handle="lmstudio_openai/local-embedding",
        ),
    ]
    return snapshot, entries


def test_options_api_filters_chat_handles_and_keeps_comment_model_keys(monkeypatch) -> None:
    snapshot, entries = _snapshot_fixture()
    monkeypatch.setattr(core, "ensure_platform_api_enabled", lambda: None)
    monkeypatch.setattr(runtime.model_catalog_service, "snapshot", lambda force_refresh=False: snapshot)
    monkeypatch.setattr(runtime.model_catalog_service, "flatten", lambda payload: entries)
    monkeypatch.setattr(
        runtime,
        "_resolve_letta_catalog_handles",
        lambda: (
            {
                "lmstudio_openai/local-model",
                "openai-proxy/doubao-seed-1-8-251228",
            },
            {"letta/letta-free"},
        ),
    )

    chat_payload = asyncio.run(core.api_get_options(refresh=True, scenario="chat"))
    assert chat_payload["defaults"]["model"] == ""
    assert [item["key"] for item in chat_payload["models"]] == [
        "openai-proxy/doubao-seed-1-8-251228",
        "lmstudio_openai/local-model",
    ]
    assert chat_payload["models"][0]["source_id"] == "local"

    comment_payload = asyncio.run(core.api_get_options(refresh=True, scenario="comment"))
    assert comment_payload["defaults"]["model"] == ""
    assert [item["key"] for item in comment_payload["models"]] == [
        "local::doubao-seed-1-8-251228",
        "local::local-model",
    ]
    assert comment_payload["models"][0]["provider_model_id"] == "doubao-seed-1-8-251228"


def test_model_catalog_api_reports_source_health_and_enriched_items(monkeypatch) -> None:
    snapshot, entries = _snapshot_fixture()
    monkeypatch.setattr(platform_meta, "ensure_platform_api_enabled", lambda: None)
    monkeypatch.setattr(runtime.model_catalog_service, "snapshot", lambda force_refresh=False: snapshot)
    monkeypatch.setattr(runtime.model_catalog_service, "flatten", lambda payload: entries)
    monkeypatch.setattr(runtime, "_resolve_letta_catalog_handles", lambda: ({"lmstudio_openai/local-model"}, {"letta/letta-free"}))

    payload = asyncio.run(platform_meta.api_platform_model_catalog(refresh=True))
    local_model = next(item for item in payload["items"] if item["provider_model_id"] == "local-model")

    assert payload["generated_at"] == 123.0
    assert [source["status"] for source in payload["sources"]] == ["healthy", "auth_error"]
    assert local_model["agent_studio_available"] is True
    assert local_model["comment_lab_available"] is True
