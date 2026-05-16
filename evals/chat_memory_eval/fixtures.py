from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class FixtureError(ValueError):
    pass


@dataclass(frozen=True)
class ExpectedFact:
    key: str
    label: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class ConversationFixture:
    key: str
    description: str
    turns: tuple[str, ...]
    expected_facts: tuple[ExpectedFact, ...]
    forbidden_reply_substrings: tuple[str, ...]


def fixture_path(fixtures_dir: Path, fixture_key: str) -> Path:
    return fixtures_dir / f"{fixture_key}.json"


def load_fixture(fixtures_dir: Path, fixture_key: str) -> ConversationFixture:
    path = fixture_path(fixtures_dir, fixture_key)
    if not path.is_file():
        raise FixtureError(f"Fixture not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise FixtureError(f"Fixture must be a JSON object: {path}")

    turns = _string_tuple(payload.get("turns"))
    if not turns:
        raise FixtureError(f"Fixture has no turns: {path}")

    expected_facts = tuple(_expected_fact(item) for item in _list(payload.get("expected_facts")))
    if not expected_facts:
        raise FixtureError(f"Fixture has no expected_facts: {path}")

    return ConversationFixture(
        key=str(payload.get("key") or fixture_key).strip(),
        description=str(payload.get("description") or "").strip(),
        turns=turns,
        expected_facts=expected_facts,
        forbidden_reply_substrings=_string_tuple(payload.get("forbidden_reply_substrings")),
    )


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_tuple(value: object) -> tuple[str, ...]:
    return tuple(str(item).strip() for item in _list(value) if str(item).strip())


def _expected_fact(value: object) -> ExpectedFact:
    if not isinstance(value, dict):
        raise FixtureError("expected_facts entries must be objects")
    key = str(value.get("key") or "").strip()
    label = str(value.get("label") or key).strip()
    aliases = _string_tuple(value.get("aliases"))
    if not key:
        raise FixtureError("expected fact key is required")
    if not aliases:
        raise FixtureError(f"expected fact '{key}' must include aliases")
    return ExpectedFact(key=key, label=label, aliases=aliases)

