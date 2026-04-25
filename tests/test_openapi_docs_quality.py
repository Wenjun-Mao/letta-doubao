from __future__ import annotations

from typing import Any

from agent_platform_api.main import app


def _openapi() -> dict[str, Any]:
    return app.openapi()


def _operations(schema: dict[str, Any]) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    for path_item in schema.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "patch", "put", "delete"}:
                continue
            if isinstance(operation, dict):
                operations.append(operation)
    return operations


def test_openapi_operations_are_tagged_and_have_human_summaries() -> None:
    schema = _openapi()
    untagged: list[str] = []
    rough_summaries: list[str] = []

    for operation in _operations(schema):
        operation_id = str(operation.get("operationId", ""))
        tags = operation.get("tags")
        if not tags:
            untagged.append(operation_id)
        summary = str(operation.get("summary", ""))
        if summary.startswith("Api "):
            rough_summaries.append(f"{operation_id}: {summary}")

    assert untagged == []
    assert rough_summaries == []


def test_commenting_generate_example_documents_model_key_not_legacy_model() -> None:
    schema = _openapi()
    operation = schema["paths"]["/api/v1/commenting/generate"]["post"]
    examples = operation["requestBody"]["content"]["application/json"]["examples"]
    values = [example["value"] for example in examples.values()]

    assert values
    assert all(value.get("model_key") == "local_llama_server::gemma4" for value in values)
    assert all("model" not in value for value in values)
    assert all(value.get("timeout_seconds", 0) >= 30 for value in values)


def test_labeling_generate_example_documents_model_key_and_schema_key() -> None:
    schema = _openapi()
    operation = schema["paths"]["/api/v1/labeling/generate"]["post"]
    examples = operation["requestBody"]["content"]["application/json"]["examples"]
    values = [example["value"] for example in examples.values()]

    assert values
    assert all(value.get("model_key") == "local_llama_server::gemma4" for value in values)
    assert all(value.get("schema_key") for value in values)
    assert all(value.get("timeout_seconds", 0) >= 30 for value in values)


def test_commenting_generate_schema_marks_legacy_model_deprecated() -> None:
    schema = _openapi()
    request_schema = schema["components"]["schemas"]["CommentingGenerateRequest"]
    model_property = request_schema["properties"]["model"]

    assert model_property["deprecated"] is True
    assert "model_key" in request_schema["properties"]
    assert request_schema["examples"][0]["model_key"] == "local_llama_server::gemma4"
    assert "model" not in request_schema["examples"][0]
