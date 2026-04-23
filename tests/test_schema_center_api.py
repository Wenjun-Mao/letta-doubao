from __future__ import annotations

import asyncio

from agent_platform_api.routers import schema_center
from utils.label_schema_registry import LabelSchemaRegistry, default_label_span_schema


def test_schema_center_routes_manage_label_schemas(monkeypatch, tmp_path) -> None:
    registry = LabelSchemaRegistry(tmp_path)
    monkeypatch.setattr(schema_center, "ensure_platform_api_enabled", lambda: None)
    monkeypatch.setattr(schema_center, "label_schema_registry", registry)
    monkeypatch.setattr(schema_center, "invalidate_options_cache", lambda: None)

    created = asyncio.run(
        schema_center.api_schema_center_create_label_schema(
            schema_center.LabelSchemaWriteRequest(
                key="label_test_schema",
                label="Test Schema",
                description="For tests.",
                schema=default_label_span_schema(),
            )
        )
    )
    assert created["key"] == "label_test_schema"

    listed = asyncio.run(schema_center.api_schema_center_list_label_schemas())
    assert listed["total"] == 1
    assert listed["items"][0]["schema"]["required"] == ["spans"]

    updated = asyncio.run(
        schema_center.api_schema_center_update_label_schema(
            "label_test_schema",
            schema_center.LabelSchemaPatchRequest(description="Updated."),
        )
    )
    assert updated["description"] == "Updated."

    archived = asyncio.run(schema_center.api_schema_center_archive_label_schema("label_test_schema"))
    assert archived["archived"] is True
    restored = asyncio.run(schema_center.api_schema_center_restore_label_schema("label_test_schema"))
    assert restored["archived"] is False
