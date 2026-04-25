from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ALLOWLIST_PATHS = {
    ("ark", "chat-probe"): PROJECT_ROOT / "agent_platform_api" / "catalog_data" / "ark_chat_probe_report.json",
    (
        "ark",
        "label-structured",
    ): PROJECT_ROOT / "agent_platform_api" / "catalog_data" / "ark_label_structured_probe_report.json",
}


@dataclass(frozen=True)
class SourceAllowlistLoadResult:
    source_id: str
    path: Path
    applied: bool
    checked_at: str | None
    probe_mode: str | None
    raw_model_count: int
    usable_models: frozenset[str]
    detail: str


def resolve_source_allowlist_path(source_id: str, *, probe_mode: str = "chat-probe") -> Path | None:
    resolved_source_id = str(source_id or "").strip()
    resolved_probe_mode = str(probe_mode or "").strip()
    return _ALLOWLIST_PATHS.get((resolved_source_id, resolved_probe_mode)) or _ALLOWLIST_PATHS.get(resolved_source_id)


def load_configured_source_allowlist(
    source_id: str,
    *,
    probe_mode: str = "chat-probe",
) -> SourceAllowlistLoadResult | None:
    resolved_source_id = str(source_id or "").strip()
    resolved_probe_mode = str(probe_mode or "").strip() or "chat-probe"
    allowlist_path = resolve_source_allowlist_path(resolved_source_id, probe_mode=resolved_probe_mode)
    if allowlist_path is None:
        return None

    if not allowlist_path.is_file():
        return SourceAllowlistLoadResult(
            source_id=resolved_source_id,
            path=allowlist_path,
            applied=False,
            checked_at=None,
            probe_mode=None,
            raw_model_count=0,
            usable_models=frozenset(),
            detail=f"Allowlist report missing at {allowlist_path}.",
        )

    try:
        payload = json.loads(allowlist_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return SourceAllowlistLoadResult(
            source_id=resolved_source_id,
            path=allowlist_path,
            applied=False,
            checked_at=None,
            probe_mode=None,
            raw_model_count=0,
            usable_models=frozenset(),
            detail=f"Allowlist report could not be read: {exc}",
        )

    try:
        return _parse_allowlist_payload(
            payload,
            source_id=resolved_source_id,
            path=allowlist_path,
            probe_mode=resolved_probe_mode,
        )
    except ValueError as exc:
        return SourceAllowlistLoadResult(
            source_id=resolved_source_id,
            path=allowlist_path,
            applied=False,
            checked_at=None,
            probe_mode=None,
            raw_model_count=0,
            usable_models=frozenset(),
            detail=f"Allowlist report is invalid: {exc}",
        )


def _parse_allowlist_payload(
    payload: Any,
    *,
    source_id: str,
    path: Path,
    probe_mode: str,
) -> SourceAllowlistLoadResult:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")

    payload_source_id = str(payload.get("source_id", "") or "").strip()
    if payload_source_id != source_id:
        raise ValueError(f"expected source_id '{source_id}' but found '{payload_source_id}'")

    checked_at = _optional_text(payload.get("checked_at"))
    payload_probe_mode = _optional_text(payload.get("probe_mode"))
    if payload_probe_mode != probe_mode:
        raise ValueError(f"expected probe_mode '{probe_mode}' but found '{payload_probe_mode}'")

    raw_model_count = payload.get("raw_model_count", 0)
    if not isinstance(raw_model_count, int) or raw_model_count < 0:
        raise ValueError("raw_model_count must be a non-negative integer")

    usable_models_value = payload.get("usable_models", [])
    if not isinstance(usable_models_value, list):
        raise ValueError("usable_models must be a list")

    normalized_usable_models: list[str] = []
    seen: set[str] = set()
    for item in usable_models_value:
        model_id = str(item or "").strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        normalized_usable_models.append(model_id)

    return SourceAllowlistLoadResult(
        source_id=source_id,
        path=path,
        applied=True,
        checked_at=checked_at,
        probe_mode=payload_probe_mode,
        raw_model_count=raw_model_count,
        usable_models=frozenset(normalized_usable_models),
        detail="ok",
    )


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
