from __future__ import annotations

from typing import Any


def dedupe_options(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for option in options:
        key = str(option.get("key", "") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(option)
    return out
