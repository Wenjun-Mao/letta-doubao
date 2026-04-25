from __future__ import annotations

import pytest

from agent_platform_api.registries.label_schema import (
    DEFAULT_LABEL_SCHEMA_KEY,
    LabelSchemaRegistry,
    LabelSchemaRegistryError,
    default_label_extraction_schema,
)


def test_label_schema_registry_crud_archive_restore_purge(tmp_path) -> None:
    registry = LabelSchemaRegistry(tmp_path)
    record = registry.create_schema(
        key=DEFAULT_LABEL_SCHEMA_KEY,
        label="Entity Groups",
        description="Grouped entity extraction.",
        schema=default_label_extraction_schema(),
    )

    assert record["key"] == DEFAULT_LABEL_SCHEMA_KEY
    assert record["schema"]["properties"]["people"]["type"] == "array"
    assert record["schema"]["properties"]["people"]["maxItems"] == 64
    assert registry.list_schemas()[0]["label"] == "Entity Groups"

    updated = registry.update_schema(
        key=DEFAULT_LABEL_SCHEMA_KEY,
        description="Updated.",
        schema=default_label_extraction_schema(),
    )
    assert updated["description"] == "Updated."

    archived = registry.archive_schema(DEFAULT_LABEL_SCHEMA_KEY)
    assert archived["archived"] is True
    assert registry.list_schemas() == []
    assert registry.list_schemas(include_archived=True)[0]["key"] == DEFAULT_LABEL_SCHEMA_KEY

    restored = registry.restore_schema(DEFAULT_LABEL_SCHEMA_KEY)
    assert restored["archived"] is False
    registry.archive_schema(DEFAULT_LABEL_SCHEMA_KEY)
    registry.purge_schema(DEFAULT_LABEL_SCHEMA_KEY)
    assert registry.list_schemas(include_archived=True) == []


def test_label_schema_registry_rejects_non_grouped_array_schema(tmp_path) -> None:
    registry = LabelSchemaRegistry(tmp_path)

    with pytest.raises(LabelSchemaRegistryError, match="group 'people' items must be string schemas"):
        registry.create_schema(
            key="bad_schema",
            schema={
                "type": "object",
                "properties": {
                    "people": {
                        "type": "array",
                        "items": {"type": "object"},
                    }
                },
                "required": ["people"],
                "additionalProperties": False,
            },
        )
