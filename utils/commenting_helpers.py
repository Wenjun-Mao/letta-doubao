from __future__ import annotations

import json
import re
from typing import Any


def normalize_content(value: Any) -> str:
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


def extract_comment_from_reasoning(reasoning_text: str) -> str:
    """Heuristically recover a final comment from provider reasoning when content is empty."""
    text = str(reasoning_text or "").strip()
    if not text:
        return ""

    patterns = [
        r"(?:Final\s*decision|Final\s*answer|Selected\s*Comment|最终决定|最终答案|最终评论)\s*[:：]\s*(.+)$",
        r"(?:输出|评论)\s*[:：]\s*(.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            candidate = str(match.group(1) or "").strip().strip('"\'`')
            if candidate:
                return candidate

    quoted_candidates: list[str] = []
    for pattern in (r"[\"“](.+?)[\"”]", r"[「『](.+?)[」』]"):
        for match in re.finditer(pattern, text, flags=re.DOTALL):
            candidate = str(match.group(1) or "").strip()
            if candidate and re.search(r"[\u4e00-\u9fff]", candidate):
                quoted_candidates.append(candidate)

    if quoted_candidates:
        punctuated = [c for c in quoted_candidates if c.endswith(("。", "！", "？", "!", "?", "～", "~"))]
        if punctuated:
            return punctuated[-1].strip().strip('"\'`')
        return quoted_candidates[-1].strip().strip('"\'`')

    line_candidates: list[str] = []
    for raw_line in text.splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue
        line = re.sub(r"^[\-\*\d\.\)\s]+", "", line).strip()
        if len(line) < 12 or not re.search(r"[\u4e00-\u9fff]", line):
            continue
        lowered = line.lower()
        if any(marker in lowered for marker in ("thinking process", "analyze", "draft", "option ", "step ")):
            continue
        line_candidates.append(line)

    if line_candidates:
        punctuated = [c for c in line_candidates if c.endswith(("。", "！", "？", "!", "?", "～", "~"))]
        if punctuated:
            return punctuated[-1].strip().strip('"\'`')
        return max(line_candidates, key=len).strip().strip('"\'`')

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[-1].strip().strip('"\'`')


def is_publishable_comment(value: str) -> bool:
    text = str(value or "").strip()
    if len(text) < 8:
        return False
    if "**" in text or text.startswith("#"):
        return False

    lowered = text.lower()
    obvious_reasoning_markers = (
        "thinking process",
        "analyze the request",
        "drafting",
        "final decision",
        "option 1",
        "option 2",
        "option 3",
        "步骤",
        "思考过程",
        "最终决定",
        "persona:",
        "persona：",
        "assistant:",
        "assistant：",
        "system:",
        "system：",
    )
    if any(marker in lowered for marker in obvious_reasoning_markers):
        return False
    if text.startswith(("-", "*", "1.", "2.", "3.")):
        return False

    invalid_tail = (",", "，", ":", "：", ";", "；", "、", "-", "—", "（", "(")
    if text.endswith(invalid_tail):
        return False

    valid_tail = ("。", "！", "？", "!", "?", "～", "~", "」", "』", "”", '"')
    return text.endswith(valid_tail)


def sanitize_comment(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    text = re.sub(r"[\s,，:：;；、\-—]+$", "", text).strip()
    if not text:
        return ""

    valid_tail = ("。", "！", "？", "!", "?", "～", "~", "」", "』", "”", '"')
    if not text.endswith(valid_tail):
        text = f"{text}。"
    return text


def build_compact_user_payload(*, persona_prompt: str, news_input: str) -> str:
    return (
        "你正在执行新闻评论生成任务。\n"
        "请严格使用给定persona语气写一条可直接发布的中文评论。\n\n"
        "[Persona]\n"
        f"{str(persona_prompt or '').strip()}\n\n"
        "[任务输入]\n"
        f"{str(news_input or '').strip()}"
    )


def build_all_in_system_prompt(*, system_prompt: str, persona_prompt: str) -> str:
    return (
        f"{str(system_prompt or '').strip()}\n\n"
        "[Persona]\n"
        f"{str(persona_prompt or '').strip()}"
    )


def build_structured_system_prompt(*, system_prompt: str, persona_prompt: str) -> str:
    return (
        f"{build_all_in_system_prompt(system_prompt=system_prompt, persona_prompt=persona_prompt)}\n\n"
        "输出要求：\n"
        "1. 你必须返回 JSON 对象。\n"
        "2. JSON 仅允许一个字段: comment。\n"
        "3. comment 必须是可发布的中文评论，不要附加解释。"
    )


def structured_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "comment_output",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "comment": {
                        "type": "string",
                        "minLength": 1,
                    }
                },
                "required": ["comment"],
                "additionalProperties": False,
            },
        },
    }


def extract_structured_comment(content_text: str) -> str:
    text = str(content_text or "").strip()
    if not text:
        return ""

    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    if fence_match:
        text = str(fence_match.group(1) or "").strip()

    def comment_from_json(raw: str) -> str:
        try:
            parsed = json.loads(raw)
        except Exception:
            return ""
        if isinstance(parsed, dict):
            value = parsed.get("comment")
            if isinstance(value, str):
                return value.strip()
        return ""

    direct = comment_from_json(text)
    if direct:
        return direct

    object_match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if object_match:
        nested = comment_from_json(str(object_match.group(0) or ""))
        if nested:
            return nested
    return ""
