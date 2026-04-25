from __future__ import annotations

import json

import ade_core.model_allowlist as model_allowlist


def test_load_configured_source_allowlist_parses_valid_report(monkeypatch, tmp_path) -> None:
    report_path = tmp_path / "ark_chat_probe_report.json"
    report_path.write_text(
        json.dumps(
            {
                "source_id": "ark",
                "checked_at": "2026-04-22T12:00:00+00:00",
                "probe_mode": "chat-probe",
                "raw_model_count": 115,
                "usable_models": ["doubao-seed-1-8-251228", "glm-4-7-251222"],
                "results": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(model_allowlist, "_ALLOWLIST_PATHS", {"ark": report_path})

    result = model_allowlist.load_configured_source_allowlist("ark")

    assert result is not None
    assert result.applied is True
    assert result.checked_at == "2026-04-22T12:00:00+00:00"
    assert result.raw_model_count == 115
    assert result.usable_models == frozenset({"doubao-seed-1-8-251228", "glm-4-7-251222"})


def test_load_configured_source_allowlist_fails_closed_for_invalid_payload(monkeypatch, tmp_path) -> None:
    report_path = tmp_path / "ark_chat_probe_report.json"
    report_path.write_text(json.dumps({"source_id": "wrong"}), encoding="utf-8")
    monkeypatch.setattr(model_allowlist, "_ALLOWLIST_PATHS", {"ark": report_path})

    result = model_allowlist.load_configured_source_allowlist("ark")

    assert result is not None
    assert result.applied is False
    assert result.usable_models == frozenset()
    assert "invalid" in result.detail.lower()
