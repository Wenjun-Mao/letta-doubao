from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from agent_platform_api.llm.provider_model_probe import (
    ProbeCatalogAuthError,
    RetryableProbeError,
    SourceProbeReport,
    classify_chat_probe_payload,
    probe_chat_model,
    probe_source_chat_models,
)
import agent_platform_api.llm.provider_model_probe as provider_model_probe
from model_router.catalog import RouterModelRecord
from model_router.settings import RouterSourceConfig


def _source() -> RouterSourceConfig:
    return RouterSourceConfig(
        id="ark",
        label="Ark",
        base_url="https://ark.example/v3",
        kind="openai-compatible",
        enabled_for=["chat", "comment"],
        letta_handle_prefix="openai-proxy",
    )


def test_classify_chat_probe_payload_accepts_success() -> None:
    result = classify_chat_probe_payload(
        RouterModelRecord(provider_model_id="doubao-seed-1-8-251228", model_type="llm"),
        {"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
    )

    assert result.status == "ok"
    assert result.usable is True


@pytest.mark.parametrize(
    ("payload", "expected_status"),
    [
        ({"status": "bad_request", "detail": "bad request"}, "bad_request"),
        ({"status": "not_found", "detail": "not found"}, "not_found"),
        ({"invalid_json": True, "detail": "oops"}, "invalid_json"),
        ({}, "invalid_payload"),
    ],
)
def test_classify_chat_probe_payload_maps_non_success_cases(payload, expected_status: str) -> None:
    result = classify_chat_probe_payload(
        RouterModelRecord(provider_model_id="model-a", model_type="llm"),
        payload,
    )

    assert result.status == expected_status
    assert result.usable is False


@pytest.mark.parametrize(
    ("exc", "expected_status"),
    [
        (ProbeCatalogAuthError(401, "unauthorized"), "auth_error"),
        (ProbeCatalogAuthError(403, "forbidden"), "auth_error"),
        (RetryableProbeError(500, "server error"), "server_error"),
        (httpx.TimeoutException("timeout"), "timeout"),
    ],
)
def test_probe_chat_model_maps_retry_and_timeout_errors(monkeypatch, exc: Exception, expected_status: str) -> None:
    monkeypatch.setattr(
        provider_model_probe,
        "_post_chat_probe_with_retries",
        lambda source, *, model_id, timeout_seconds: (_ for _ in ()).throw(exc),
    )

    result = probe_chat_model(
        _source(),
        RouterModelRecord(provider_model_id="model-a", model_type="llm"),
        timeout_seconds=5.0,
    )

    assert result.status == expected_status
    assert result.usable is False


def test_probe_source_chat_models_skips_non_llm_entries(monkeypatch) -> None:
    monkeypatch.setattr(
        provider_model_probe,
        "fetch_source_catalog_records",
        lambda source, *, timeout_seconds: [
            RouterModelRecord(provider_model_id="doubao-seed-1-8-251228", model_type="llm"),
            RouterModelRecord(provider_model_id="doubao-embedding-text-240715", model_type="embedding"),
        ],
    )
    monkeypatch.setattr(
        provider_model_probe,
        "probe_chat_model",
        lambda source, record, *, timeout_seconds: classify_chat_probe_payload(
            record,
            {"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        ),
    )

    report = probe_source_chat_models(_source(), timeout_seconds=5.0)

    assert isinstance(report, SourceProbeReport)
    assert report.raw_model_count == 2
    assert report.usable_models == ("doubao-seed-1-8-251228",)
    assert report.results[1].status == "skipped_non_llm"
