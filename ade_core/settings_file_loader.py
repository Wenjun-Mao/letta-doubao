from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def resolve_config_path(path_value: str, *, project_root: Path) -> Path:
    path = Path(str(path_value or "").strip())
    if path.is_absolute():
        return path
    return project_root / path


def load_json_config_list(path_value: str, *, project_root: Path) -> list[dict[str, Any]]:
    path = resolve_config_path(path_value, project_root=project_root)
    if not path.is_file():
        return []

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Config file '{path}' must contain a JSON array")

    items: list[dict[str, Any]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"Config file '{path}' item {index} must be an object")
        items.append(item)
    return items

