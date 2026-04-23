from __future__ import annotations

import asyncio
from types import SimpleNamespace

import agent_platform_api.runtime as runtime
from agent_platform_api.routers import core, platform_meta
from utils.model_catalog import CatalogEntry, CatalogModelRecord, CatalogSnapshot, CatalogSourceRecord


def _snapshot_fixture() -> tuple[CatalogSnapshot, list[CatalogEntry]]:
    snapshot = CatalogSnapshot(
        generated_at=123.0,
        sources=(
            CatalogSourceRecord(
                id="local_llama_server",
                label="Local llama-server",
                kind="openai-compatible",
                base_url="http://127.0.0.1:8081/v1",
                enabled_for=("comment", "label"),
                letta_handle_prefix="",
                status="healthy",
                detail="ok",
                models=(
                    CatalogModelRecord(provider_model_id="gemma4", model_type="llm"),
                ),
                adapter="llama_cpp_server",
                raw_model_count=1,
                filtered_model_count=1,
            ),
            CatalogSourceRecord(
                id="local_lmstudio",
                label="Local LM Studio",
                kind="openai-compatible",
                base_url="http://127.0.0.1:1234/v1",
                enabled_for=("chat", "comment", "label"),
                letta_handle_prefix="lmstudio_openai",
                status="healthy",
                detail="ok",
                models=(CatalogModelRecord(provider_model_id="local-model", model_type="llm"),),
                raw_model_count=1,
                filtered_model_count=1,
            ),
            CatalogSourceRecord(
                id="ark",
                label="Volcengine Ark",
                kind="openai-compatible",
                base_url="https://ark.example/v3",
                enabled_for=("chat", "comment"),
                letta_handle_prefix="openai-proxy",
                status="healthy",
                detail="Allowlist applied: 1 of 3 catalog entries remain selectable.",
                models=(CatalogModelRecord(provider_model_id="doubao-seed-1-8-251228", model_type="llm"),),
                adapter="ark_openai",
                allowlist_applied=True,
                allowlist_checked_at="2026-04-22T12:00:00+00:00",
                raw_model_count=3,
                filtered_model_count=1,
            ),
        ),
    )
    entries = [
        CatalogEntry(
            source_id="local_llama_server",
            source_label="Local llama-server",
            source_kind="openai-compatible",
            base_url="http://127.0.0.1:8081/v1",
            enabled_for=("comment", "label"),
            provider_model_id="gemma4",
            model_type="llm",
            model_key="local_llama_server::gemma4",
            letta_handle=None,
            source_adapter="llama_cpp_server",
        ),
        CatalogEntry(
            source_id="local_lmstudio",
            source_label="Local LM Studio",
            source_kind="openai-compatible",
            base_url="http://127.0.0.1:1234/v1",
            enabled_for=("chat", "comment", "label"),
            provider_model_id="local-model",
            model_type="llm",
            model_key="local_lmstudio::local-model",
            letta_handle="lmstudio_openai/local-model",
        ),
        CatalogEntry(
            source_id="ark",
            source_label="Volcengine Ark",
            source_kind="openai-compatible",
            base_url="https://ark.example/v3",
            enabled_for=("chat", "comment"),
            provider_model_id="doubao-seed-1-8-251228",
            model_type="llm",
            model_key="ark::doubao-seed-1-8-251228",
            letta_handle="openai-proxy/doubao-seed-1-8-251228",
            source_adapter="ark_openai",
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
        "_label_allowlist_for_source",
        lambda source_id: (
            SimpleNamespace(applied=True, usable_models=frozenset({"doubao-seed-1-8-251228"}))
            if source_id == "ark"
            else None
        ),
    )
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
    assert {item["source_id"] for item in chat_payload["models"]} == {"ark", "local_lmstudio"}

    comment_payload = asyncio.run(core.api_get_options(refresh=True, scenario="comment"))
    assert comment_payload["defaults"]["model"] == ""
    assert [item["key"] for item in comment_payload["models"]] == [
        "local_llama_server::gemma4",
        "local_lmstudio::local-model",
        "ark::doubao-seed-1-8-251228",
    ]
    assert comment_payload["models"][0]["provider_model_id"] == "gemma4"

    label_payload = asyncio.run(core.api_get_options(refresh=True, scenario="label"))
    assert label_payload["defaults"]["persona_key"] == ""
    assert label_payload["defaults"]["schema_key"] == "label_span_annotations_v1"
    assert label_payload["schemas"][0]["key"] == "label_span_annotations_v1"
    assert label_payload["labeling"].repair_retry_count >= 0
    assert [item["key"] for item in label_payload["models"]] == [
        "local_llama_server::gemma4",
        "local_lmstudio::local-model",
    ]
    assert label_payload["models"][0]["structured_output_mode"] == "json_schema"


def test_model_catalog_api_reports_source_health_and_enriched_items(monkeypatch) -> None:
    snapshot, entries = _snapshot_fixture()
    monkeypatch.setattr(platform_meta, "ensure_platform_api_enabled", lambda: None)
    monkeypatch.setattr(runtime.model_catalog_service, "snapshot", lambda force_refresh=False: snapshot)
    monkeypatch.setattr(runtime.model_catalog_service, "flatten", lambda payload: entries)
    monkeypatch.setattr(
        runtime,
        "_label_allowlist_for_source",
        lambda source_id: (
            SimpleNamespace(applied=True, usable_models=frozenset({"doubao-seed-1-8-251228"}))
            if source_id == "ark"
            else None
        ),
    )
    monkeypatch.setattr(
        runtime,
        "_resolve_letta_catalog_handles",
        lambda: ({"lmstudio_openai/local-model", "openai-proxy/doubao-seed-1-8-251228"}, {"letta/letta-free"}),
    )

    payload = asyncio.run(platform_meta.api_platform_model_catalog(refresh=True))
    local_model = next(item for item in payload["items"] if item["provider_model_id"] == "local-model")
    ark_source = next(source for source in payload["sources"] if source["id"] == "ark")

    assert payload["generated_at"] == 123.0
    assert [source["status"] for source in payload["sources"]] == ["healthy", "healthy", "healthy"]
    assert ark_source["allowlist_applied"] is True
    assert ark_source["raw_model_count"] == 3
    assert ark_source["filtered_model_count"] == 1
    assert local_model["agent_studio_available"] is True
    assert local_model["comment_lab_available"] is True
    assert local_model["label_lab_available"] is True
    llama_model = next(item for item in payload["items"] if item["provider_model_id"] == "gemma4")
    ark_model = next(item for item in payload["items"] if item["source_id"] == "ark")
    assert llama_model["source_adapter"] == "llama_cpp_server"
    assert llama_model["structured_output_mode"] == "json_schema"
    assert llama_model["label_lab_available"] is True
    assert ark_model["label_lab_available"] is False
