from __future__ import annotations

from typing import Any

from agent_platform_api.dependencies import label_schema_registry
from agent_platform_api.registries.label_schema import DEFAULT_LABEL_SCHEMA_KEY


def active_label_schema_records() -> list[dict[str, Any]]:
    return [
        record
        for record in label_schema_registry.list_schemas(include_archived=False)
        if not bool(record.get("archived", False))
    ]


def label_schema_option_entries() -> list[dict[str, Any]]:
    return [
        {
            "key": str(record.get("key", "") or ""),
            "label": str(record.get("label", "") or ""),
            "description": str(record.get("description", "") or ""),
            "scenario": "label",
            "available": True,
        }
        for record in active_label_schema_records()
        if str(record.get("key", "") or "").strip()
    ]


def label_schema_record_map() -> dict[str, dict[str, Any]]:
    return {
        str(record.get("key", "") or ""): record
        for record in active_label_schema_records()
        if str(record.get("key", "") or "").strip()
    }


def resolve_default_label_schema_key(schema_options: list[dict[str, Any]]) -> str:
    if any(str(option.get("key", "")) == DEFAULT_LABEL_SCHEMA_KEY for option in schema_options):
        return DEFAULT_LABEL_SCHEMA_KEY
    return str(schema_options[0].get("key", "") if schema_options else "")
