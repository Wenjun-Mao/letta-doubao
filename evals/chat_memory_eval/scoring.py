from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .fixtures import ExpectedFact

DEFAULT_FORBIDDEN_REPLY_SUBSTRINGS = (
    "我是ai",
    "我是一个ai",
    "作为ai",
    "语言模型",
    "大语言模型",
    "虚拟助手",
    "虚拟角色",
    "我是虚拟",
    "我是模拟",
    "我不是真的",
    "我并不真实",
    "我不是真实",
    "线上角色",
    "我是机器人",
    "程序生成",
)


@dataclass(frozen=True)
class FactScore:
    key: str
    label: str
    passed: bool
    matched_aliases: tuple[str, ...]
    aliases: tuple[str, ...]


def assistant_replies(sequence: list[dict[str, Any]]) -> list[str]:
    return [
        str(step.get("content", "") or "").strip()
        for step in sequence
        if str(step.get("type", "")).lower() == "assistant" and str(step.get("content", "") or "").strip()
    ]


def tool_calls(sequence: list[dict[str, Any]]) -> list[dict[str, str]]:
    calls: list[dict[str, str]] = []
    for step in sequence:
        if str(step.get("type", "")).lower() != "tool_call":
            continue
        calls.append(
            {
                "name": str(step.get("name", "") or ""),
                "arguments": str(step.get("arguments", "") or step.get("tool_arguments", "") or ""),
            }
        )
    return calls


def memory_tool_calls(sequence: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [call for call in tool_calls(sequence) if "memory" in call["name"].lower()]


def forbidden_hits(text: str, forbidden_substrings: tuple[str, ...]) -> list[str]:
    lowered = text.lower()
    return [needle for needle in forbidden_substrings if needle.lower() in lowered]


def memory_changed(old_memory: str, new_memory: str) -> bool:
    return old_memory.strip() != new_memory.strip()


def score_expected_facts(memory_text: str, expected_facts: tuple[ExpectedFact, ...]) -> list[FactScore]:
    normalized = memory_text.lower()
    scores: list[FactScore] = []
    for fact in expected_facts:
        matches = tuple(alias for alias in fact.aliases if alias.lower() in normalized)
        scores.append(
            FactScore(
                key=fact.key,
                label=fact.label,
                passed=bool(matches),
                matched_aliases=matches,
                aliases=fact.aliases,
            )
        )
    return scores


def deterministic_round_score(
    *,
    assistant_texts: list[str],
    initial_human_memory: str,
    final_human_memory: str,
    expected_facts: tuple[ExpectedFact, ...],
    forbidden_reply_substrings: tuple[str, ...],
) -> dict[str, Any]:
    all_forbidden_hits = [
        {
            "assistant_reply": text,
            "hits": forbidden_hits(text, forbidden_reply_substrings),
        }
        for text in assistant_texts
    ]
    all_forbidden_hits = [item for item in all_forbidden_hits if item["hits"]]
    fact_scores = score_expected_facts(final_human_memory, expected_facts)
    missing = [score.key for score in fact_scores if not score.passed]
    changed = memory_changed(initial_human_memory, final_human_memory)
    passed = changed and not missing and not all_forbidden_hits
    return {
        "pass": passed,
        "forbidden_hits": all_forbidden_hits,
        "forbidden_hit_count": len(all_forbidden_hits),
        "human_memory_changed": changed,
        "expected_fact_scores": [score.__dict__ for score in fact_scores],
        "expected_facts_passed": not missing,
        "missing_expected_facts": missing,
    }
