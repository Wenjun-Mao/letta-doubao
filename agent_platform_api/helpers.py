from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from agent_platform_api.models.common import ScenarioType
from agent_platform_api.runtime import (
    REVISION_LOG_DIR,
    REVISION_LOG_FILE,
    SCENARIO_DEFAULTS,
    client,
    prompt_persona_registry,
)

try:
    SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
except Exception:
    SHANGHAI_TZ = timezone(timedelta(hours=8), name="CST")

DATETIME_QUERY_TOKENS = (
    "today",
    "date",
    "time",
    "current date",
    "current time",
    "what day",
    "what time",
    "今天",
    "日期",
    "几月",
    "几号",
    "几日",
    "星期",
    "周几",
    "礼拜几",
    "现在几点",
    "当前时间",
)


def normalize_scenario(value: str | None, *, default: ScenarioType = "chat") -> ScenarioType:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return default
    if normalized == "chat":
        return "chat"
    if normalized == "comment":
        return "comment"
    raise HTTPException(status_code=400, detail="scenario must be either 'chat' or 'comment'")


def active_prompt_records(scenario: ScenarioType | None = None) -> list[dict[str, Any]]:
    records = [
        record
        for record in prompt_persona_registry.list_templates(
            "prompt",
            include_archived=False,
            scenario=scenario,
        )
        if not bool(record.get("archived", False))
    ]
    if scenario:
        records = [
            record
            for record in records
            if str(record.get("key", "") or "").startswith(f"{scenario}_")
        ]
    return records


def active_persona_records(scenario: ScenarioType | None = None) -> list[dict[str, Any]]:
    records = [
        record
        for record in prompt_persona_registry.list_templates(
            "persona",
            include_archived=False,
            scenario=scenario,
        )
        if not bool(record.get("archived", False))
    ]
    if scenario:
        records = [
            record
            for record in records
            if str(record.get("key", "") or "").startswith(f"{scenario}_")
        ]
    return records


def prompt_content_map(scenario: ScenarioType | None = None) -> dict[str, str]:
    return {
        str(record.get("key", "")): str(record.get("content", "") or "")
        for record in active_prompt_records(scenario)
        if str(record.get("key", "")).strip()
    }


def persona_content_map(scenario: ScenarioType | None = None) -> dict[str, str]:
    return {
        str(record.get("key", "")): str(record.get("content", "") or "")
        for record in active_persona_records(scenario)
        if str(record.get("key", "")).strip()
    }


def prompt_option_entries(scenario: ScenarioType | None = None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for record in active_prompt_records(scenario):
        entries.append(
            {
                "key": str(record.get("key", "") or ""),
                "label": str(record.get("label", "") or ""),
                "description": str(record.get("description", "") or ""),
                "scenario": str(record.get("scenario", "") or "") or None,
            }
        )
    return entries


def persona_option_entries(scenario: ScenarioType | None = None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for record in active_persona_records(scenario):
        entries.append(
            {
                "key": str(record.get("key", "") or ""),
                "label": str(record.get("label", "") or ""),
                "description": str(record.get("description", "") or ""),
                "scenario": str(record.get("scenario", "") or "") or None,
            }
        )
    return entries


def resolve_default_prompt_key(prompt_options: list[dict[str, Any]], scenario: ScenarioType) -> str:
    preferred = SCENARIO_DEFAULTS[scenario]["prompt_key"]
    if any(str(option.get("key", "")) == preferred for option in prompt_options):
        return preferred
    return str(prompt_options[0].get("key", "") if prompt_options else "")


def resolve_default_persona_key(persona_options: list[dict[str, Any]], scenario: ScenarioType) -> str:
    preferred = SCENARIO_DEFAULTS[scenario]["persona_key"]
    if any(str(option.get("key", "")) == preferred for option in persona_options):
        return preferred
    return str(persona_options[0].get("key", "") if persona_options else "")


def safe_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except Exception:
        return str(value)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return safe_json(json.loads(stripped))
            except Exception:
                return value
        return value
    if isinstance(value, list):
        text_parts = [getattr(item, "text", None) for item in value]
        valid_parts = [part for part in text_parts if isinstance(part, str) and part]
        if valid_parts:
            return " ".join(valid_parts)
        return safe_json(value)
    if isinstance(value, (dict, tuple)):
        return safe_json(value)
    return str(value)


def to_jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return to_jsonable(model_dump(mode="json"))
        except TypeError:
            return to_jsonable(model_dump())
        except Exception:
            pass

    to_dict = getattr(value, "dict", None)
    if callable(to_dict):
        try:
            return to_jsonable(to_dict())
        except Exception:
            pass

    return normalize_text(value)


def serialize_message(msg: Any) -> dict[str, Any]:
    message_type = getattr(msg, "message_type", "unknown")
    role = getattr(msg, "role", message_type)

    content: Any = getattr(msg, "content", None)
    if message_type == "reasoning_message":
        content = getattr(msg, "reasoning", content)
    if message_type == "tool_return_message":
        content = getattr(msg, "tool_return", content)

    tool_name = None
    tool_arguments = None
    tool_call = getattr(msg, "tool_call", None)
    if tool_call is not None:
        tool_name = getattr(tool_call, "name", None)
        tool_arguments = normalize_text(getattr(tool_call, "arguments", None))

    timestamp = getattr(msg, "created_at", None) or getattr(msg, "date", None)
    return {
        "id": str(getattr(msg, "id", "")),
        "created_at": str(timestamp or ""),
        "message_type": message_type,
        "role": role,
        "status": str(getattr(msg, "status", "")),
        "name": tool_name,
        "tool_arguments": tool_arguments,
        "content": normalize_text(content),
    }


def derive_last_interaction_at(agent_id: str, last_updated_at: str = "") -> str:
    if last_updated_at:
        return last_updated_at
    try:
        messages = list(client.agents.messages.list(agent_id=agent_id))
    except Exception:
        return ""

    latest = ""
    for msg in messages:
        message_type = str(getattr(msg, "message_type", ""))
        if message_type == "system_message":
            continue
        created_at = str(getattr(msg, "created_at", None) or getattr(msg, "date", None) or "")
        if created_at and created_at > latest:
            latest = created_at
    return latest


def is_datetime_query(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(token in lowered for token in DATETIME_QUERY_TOKENS)


def runtime_datetime_system_hint() -> str:
    now = datetime.now(SHANGHAI_TZ)
    iso_time = now.strftime("%Y-%m-%d %H:%M:%S %Z%z")
    return (
        "Runtime datetime context for this turn. "
        "Timezone: Asia/Shanghai. "
        f"Current datetime: {iso_time}. "
        "If the user asks about current date or time, answer directly using this value. "
        "Do not say you cannot access a calendar."
    )


def first_non_empty_line(text: str) -> str:
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned
    return ""


def trim_preview(value: str, max_len: int = 180) -> str:
    line = first_non_empty_line(value)
    if len(line) <= max_len:
        return line
    return f"{line[:max_len]}..."


def append_prompt_persona_revision(
    *,
    agent_id: str,
    field: str,
    before: str,
    after: str,
    source: str,
) -> None:
    if before == after:
        return

    record = {
        "revision_id": str(uuid4()),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "agent_id": agent_id,
        "field": field,
        "source": source,
        "before": before,
        "after": after,
        "before_preview": trim_preview(before),
        "after_preview": trim_preview(after),
        "before_length": len(before),
        "after_length": len(after),
        "delta_length": len(after) - len(before),
    }

    try:
        REVISION_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with REVISION_LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        return


def read_prompt_persona_revisions(
    *,
    agent_id: str | None,
    field: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    if not REVISION_LOG_FILE.exists():
        return []

    items: list[dict[str, Any]] = []
    try:
        for raw_line in REVISION_LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue

            if agent_id and str(payload.get("agent_id", "") or "") != agent_id:
                continue
            if field and str(payload.get("field", "") or "") != field:
                continue

            items.append(payload)
    except Exception:
        return []

    if len(items) > limit:
        items = items[-limit:]
    items.reverse()
    return items

