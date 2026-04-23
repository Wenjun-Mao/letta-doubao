from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from agent_platform_api.settings import ModelSourceConfig
from utils.provider_model_probe import ProbedModelResult, SourceProbeReport


def _load_script_module():
    project_root = Path(__file__).resolve().parents[1]
    script_path = project_root / "scripts" / "probe_provider_models.py"
    spec = importlib.util.spec_from_file_location("probe_provider_models", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_probe_provider_models_script_writes_report(monkeypatch, tmp_path) -> None:
    module = _load_script_module()
    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: SimpleNamespace(
            model_sources=[
                ModelSourceConfig(
                    id="ark",
                    label="Ark",
                    base_url="https://ark.example/v3",
                    kind="openai-compatible",
                    enabled_for=["chat", "comment"],
                    letta_handle_prefix="openai-proxy",
                )
            ],
            model_discovery_timeout_seconds=5.0,
        ),
    )
    monkeypatch.setattr(
        module,
        "probe_source_chat_models",
        lambda source, *, timeout_seconds: SourceProbeReport(
            source_id="ark",
            checked_at="2026-04-22T12:00:00+00:00",
            probe_mode="chat-probe",
            raw_model_count=2,
            usable_models=("doubao-seed-1-8-251228",),
            results=(
                ProbedModelResult(
                    provider_model_id="doubao-seed-1-8-251228",
                    model_type="llm",
                    status="ok",
                    usable=True,
                    http_status=200,
                    detail="ok",
                ),
            ),
        ),
    )

    output_path = tmp_path / "ark_chat_probe_report.json"
    rc = module.main(
        [
            "--source-id",
            "ark",
            "--mode",
            "chat-probe",
            "--write",
            "--output",
            str(output_path),
        ]
    )

    assert rc == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["source_id"] == "ark"
    assert payload["usable_models"] == ["doubao-seed-1-8-251228"]


def test_probe_provider_models_script_supports_label_structured_mode(monkeypatch, tmp_path) -> None:
    module = _load_script_module()
    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: SimpleNamespace(
            model_sources=[
                ModelSourceConfig(
                    id="ark",
                    label="Ark",
                    base_url="https://ark.example/v3",
                    kind="openai-compatible",
                    enabled_for=["chat", "comment", "label"],
                    letta_handle_prefix="openai-proxy",
                )
            ],
            model_discovery_timeout_seconds=5.0,
        ),
    )
    monkeypatch.setattr(
        module,
        "probe_source_label_models",
        lambda source, *, timeout_seconds: SourceProbeReport(
            source_id="ark",
            checked_at="2026-04-22T12:00:00+00:00",
            probe_mode="label-structured",
            raw_model_count=1,
            usable_models=("doubao-seed-1-8-251228",),
            results=(
                ProbedModelResult(
                    provider_model_id="doubao-seed-1-8-251228",
                    model_type="llm",
                    status="ok",
                    usable=True,
                    http_status=200,
                    detail="ok",
                ),
            ),
        ),
    )

    output_path = tmp_path / "ark_label_structured_probe_report.json"
    rc = module.main(
        [
            "--source-id",
            "ark",
            "--mode",
            "label-structured",
            "--write",
            "--output",
            str(output_path),
        ]
    )

    assert rc == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["probe_mode"] == "label-structured"
    assert payload["usable_models"] == ["doubao-seed-1-8-251228"]
