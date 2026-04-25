from __future__ import annotations

import json
import re
from typing import Any

_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
LABEL_PROBE_ARTICLE = "Messi scored for Inter Miami against Orlando City."
LABEL_PROBE_RESULT = {
    "players": ["Messi"],
    "teams": ["Inter Miami", "Orlando City"],
}
_DEFAULT_LABEL_GROUPS = ("people", "organizations", "locations", "dates", "events")
_FOOTBALL_LABEL_GROUPS = ("players", "teams")


def build_label_output_schema(
    group_names: list[str] | tuple[str, ...],
    *,
    max_items: int = 64,
) -> dict[str, Any]:
    keys = _normalize_group_names(group_names)
    if not keys:
        raise ValueError("Label output schema must define at least one extraction group.")
    return {
        "type": "object",
        "properties": {
            key: {
                "type": "array",
                "maxItems": max_items,
                "items": {
                    "type": "string",
                    "minLength": 1,
                },
            }
            for key in keys
        },
        "required": list(keys),
        "additionalProperties": False,
    }


def default_label_output_schema() -> dict[str, Any]:
    return build_label_output_schema(_DEFAULT_LABEL_GROUPS)


def football_label_output_schema() -> dict[str, Any]:
    return build_label_output_schema(_FOOTBALL_LABEL_GROUPS)


def label_probe_output_schema() -> dict[str, Any]:
    return football_label_output_schema()


def validate_label_output_schema_contract(schema: dict[str, Any]) -> list[str]:
    if not isinstance(schema, dict):
        return ["schema must be a JSON object"]
    if schema.get("type") != "object":
        return ["label schema must be a top-level object schema"]

    properties = schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        return ["label schema must define at least one extraction group"]

    required = schema.get("required")
    if not isinstance(required, list) or not required:
        return ["label schema must require every extraction group"]
    required_names = [str(item or "").strip() for item in required if str(item or "").strip()]
    if set(required_names) != set(str(name) for name in properties):
        return ["label schema must require exactly the defined extraction groups"]

    if schema.get("additionalProperties") is not False:
        return ["label schema must set additionalProperties to false"]

    errors: list[str] = []
    for group_name, group_schema in properties.items():
        if not isinstance(group_schema, dict):
            errors.append(f"group '{group_name}' must be a schema object")
            continue
        if group_schema.get("type") != "array":
            errors.append(f"group '{group_name}' must be an array schema")
            continue
        items = group_schema.get("items")
        if not isinstance(items, dict) or items.get("type") != "string":
            errors.append(f"group '{group_name}' items must be string schemas")
            continue
    return errors


def label_schema_group_names(schema: dict[str, Any]) -> list[str]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    return [str(key) for key in properties]


def schema_preview_text(schema: dict[str, Any]) -> str:
    return json.dumps(schema, ensure_ascii=False, indent=2)


def resolve_label_output_schema(raw_schema: str | None) -> dict[str, Any]:
    text = str(raw_schema or "").strip()
    if not text:
        return default_label_output_schema()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Prompt OUTPUT_SCHEMA is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Prompt OUTPUT_SCHEMA must be a JSON object")

    errors = validate_label_output_schema_contract(parsed)
    if errors:
        raise ValueError("; ".join(errors))
    return parsed


def label_response_format(schema: dict[str, Any], *, name: str = "label_output") -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": schema,
        },
    }


def build_label_user_payload(article_input: str) -> str:
    return str(article_input or "").strip()


def build_best_effort_label_system_prompt(*, system_prompt: str, schema: dict[str, Any]) -> str:
    return (
        f"{str(system_prompt or '').strip()}\n\n"
        "Output rules:\n"
        "1. Return JSON only.\n"
        "2. Do not include markdown fences.\n"
        "3. Each field must be an array of exact substrings from the article.\n"
        "4. Trim whitespace and omit duplicate values.\n"
        "5. Do not add keys outside the schema.\n\n"
        "[JSON Schema]\n"
        f"{schema_preview_text(schema)}"
    )


def build_repair_prompt(
    *,
    article_input: str,
    invalid_output: str,
    validation_errors: list[str],
) -> str:
    joined_errors = "\n".join(f"- {item}" for item in validation_errors if str(item or "").strip()) or "- Unknown validation error"
    return (
        f"{build_label_user_payload(article_input)}\n\n"
        "[Previous Invalid Output]\n"
        f"{str(invalid_output or '').strip()}\n\n"
        "[Validation Errors]\n"
        f"{joined_errors}\n\n"
        "Return corrected JSON only. Keep the same top-level keys and use exact article substrings."
    )


def normalize_label_content(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = str(item.get("text", "") or "").strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return str(value or "").strip()


def strip_think_tags(text: str) -> str:
    return _THINK_TAG_RE.sub("", str(text or "")).strip()


def extract_first_json_object(text: str) -> str:
    cleaned = strip_think_tags(str(text or "").strip())
    if not cleaned:
        return ""

    decoder = json.JSONDecoder()
    if cleaned.startswith("{"):
        try:
            _, end = decoder.raw_decode(cleaned)
            return cleaned[:end].strip()
        except json.JSONDecodeError:
            pass

    for index, char in enumerate(cleaned):
        if char != "{":
            continue
        candidate = cleaned[index:]
        try:
            _, end = decoder.raw_decode(candidate)
        except json.JSONDecodeError:
            continue
        return candidate[:end].strip()
    return ""


def parse_json_object(text: str) -> dict[str, Any]:
    raw_object = extract_first_json_object(text)
    if not raw_object:
        raise ValueError("No JSON object could be extracted from provider output")
    parsed = json.loads(raw_object)
    if not isinstance(parsed, dict):
        raise ValueError("Provider JSON output must be an object")
    return parsed


def validate_label_result(
    payload: dict[str, Any],
    article_input: str,
    output_schema: dict[str, Any],
) -> tuple[dict[str, list[str]] | None, list[str]]:
    schema_errors = validate_label_output_schema_contract(output_schema)
    if schema_errors:
        return None, list(schema_errors)
    if not isinstance(payload, dict):
        return None, ["Provider JSON output must be an object."]

    properties = output_schema.get("properties", {})
    required_groups = [str(item) for item in output_schema.get("required", [])]
    article = str(article_input or "")
    errors: list[str] = []
    normalized_result: dict[str, list[str]] = {}

    unknown_groups = [str(key) for key in payload if key not in properties]
    if unknown_groups:
        errors.append(
            "Unknown top-level keys: " + ", ".join(sorted(unknown_groups))
        )

    missing_groups = [key for key in required_groups if key not in payload]
    if missing_groups:
        errors.append(
            "Missing required top-level keys: " + ", ".join(missing_groups)
        )

    for group_name, group_schema in properties.items():
        if group_name not in payload:
            continue
        values = payload.get(group_name)
        if not isinstance(values, list):
            errors.append(f"{group_name} must be an array of strings.")
            continue

        max_items = group_schema.get("maxItems")
        if isinstance(max_items, int) and max_items >= 0 and len(values) > max_items:
            errors.append(f"{group_name} exceeds maxItems={max_items}.")

        normalized_values: list[str] = []
        seen_values: set[str] = set()
        for index, item in enumerate(values):
            if not isinstance(item, str):
                errors.append(f"{group_name}[{index}] must be a string.")
                continue
            cleaned = item.strip()
            if not cleaned:
                errors.append(f"{group_name}[{index}] must be a non-empty string.")
                continue
            if article.find(cleaned) < 0:
                errors.append(
                    f"{group_name}[{index}] must exactly match a substring in the input article."
                )
                continue
            if cleaned in seen_values:
                continue
            seen_values.add(cleaned)
            normalized_values.append(cleaned)

        normalized_result[str(group_name)] = normalized_values

    if errors:
        return None, errors
    return normalized_result, []


def build_label_probe_system_prompt() -> str:
    return (
        "Extract football entities from the article.\n"
        "Return JSON only with these keys:\n"
        '- "players": football player names\n'
        '- "teams": football clubs or team names\n\n'
        "Each value must be an array of exact substrings from the article."
    )


def label_probe_success(result: dict[str, Any]) -> bool:
    normalized, errors = validate_label_result(result, LABEL_PROBE_ARTICLE, label_probe_output_schema())
    return not errors and normalized == LABEL_PROBE_RESULT


def _normalize_group_names(group_names: list[str] | tuple[str, ...]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in group_names:
        key = str(item or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(key)
    return normalized
