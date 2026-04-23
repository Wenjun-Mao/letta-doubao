from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_LABEL_KEYS = {"spans"}
_SPAN_KEYS = {"label", "text", "start", "end"}
LABEL_PROBE_ARTICLE = "Messi scored for Inter Miami against Orlando City."
LABEL_PROBE_RESULT = {
    "spans": [
        {"label": "PLAYER", "text": "Messi", "start": 0, "end": 5},
        {"label": "TEAM", "text": "Inter Miami", "start": 17, "end": 28},
        {"label": "TEAM", "text": "Orlando City", "start": 37, "end": 49},
    ]
}


class LabelSpanPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    text: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class LabelResultPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spans: list[LabelSpanPayload] = Field(default_factory=list)


def default_label_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "spans": {
                "type": "array",
                "maxItems": 64,
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "minLength": 1},
                        "text": {"type": "string", "minLength": 1},
                        "start": {"type": "integer", "minimum": 0},
                        "end": {"type": "integer", "minimum": 0},
                    },
                    "required": ["label", "text", "start", "end"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["spans"],
        "additionalProperties": False,
    }


def label_response_format(schema: dict[str, Any], *, name: str = "label_output") -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": schema,
        },
    }


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
    return parsed


def schema_preview_text(schema: dict[str, Any]) -> str:
    return json.dumps(schema, ensure_ascii=False, indent=2)


def build_label_user_payload(article_input: str) -> str:
    return str(article_input or "").strip()


def build_best_effort_label_system_prompt(*, system_prompt: str, schema: dict[str, Any]) -> str:
    return (
        f"{str(system_prompt or '').strip()}\n\n"
        "Output rules:\n"
        "1. Return JSON only.\n"
        "2. Do not include markdown fences.\n"
        "3. Use exact substrings from the article.\n"
        "4. start/end must be Unicode character offsets with end-exclusive indexing.\n"
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
        "Return corrected JSON only."
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


def validate_label_result(payload: dict[str, Any], article_input: str) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        parsed_payload = LabelResultPayload.model_validate(payload)
    except ValidationError as exc:
        return None, [f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()]

    article = str(article_input or "")
    errors: list[str] = []
    normalized_spans: list[dict[str, Any]] = []
    for index, span in enumerate(parsed_payload.spans):
        prefix = f"spans[{index}]"
        start = span.start
        end = span.end
        if start >= end or end > len(article) or article[start:end] != span.text:
            corrected_offsets = _unique_text_offsets(article, span.text)
            if corrected_offsets is None:
                if start >= end:
                    errors.append(f"{prefix} must satisfy 0 <= start < end.")
                elif end > len(article):
                    errors.append(f"{prefix}.end exceeds article length.")
                else:
                    errors.append(f"{prefix}.text must exactly match input[start:end].")
                continue
            start, end = corrected_offsets

        normalized_spans.append(
            {
                "label": span.label.strip(),
                "text": span.text,
                "start": start,
                "end": end,
            }
        )

    normalized_spans.sort(key=lambda item: (item["start"], item["end"], item["label"], item["text"]))
    for index in range(1, len(normalized_spans)):
        previous = normalized_spans[index - 1]
        current = normalized_spans[index]
        if previous["end"] > current["start"]:
            errors.append(
                "Spans must not overlap or nest. "
                f"Conflict between {previous['text']} and {current['text']}."
            )
            break

    if errors:
        return None, errors
    return {"spans": normalized_spans}, []


def _unique_text_offsets(article: str, text: str) -> tuple[int, int] | None:
    needle = str(text or "")
    if not needle:
        return None
    first = article.find(needle)
    if first < 0:
        return None
    if article.find(needle, first + 1) >= 0:
        return None
    return first, first + len(needle)


def build_label_probe_system_prompt() -> str:
    return (
        "Extract spans from the article using these labels only:\n"
        "- PLAYER: football player names\n"
        "- TEAM: football club or team names\n\n"
        "Return exact substrings with end-exclusive Unicode character offsets."
    )


def label_probe_success(result: dict[str, Any]) -> bool:
    normalized, errors = validate_label_result(result, LABEL_PROBE_ARTICLE)
    return not errors and normalized == LABEL_PROBE_RESULT
