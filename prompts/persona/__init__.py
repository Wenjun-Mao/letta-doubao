"""Persona exports for legacy imports.

The PERSONAS mapping is discovered from files in this directory, so Prompt Center
persona creation does not require manual edits here.
"""

from __future__ import annotations

import ast
from pathlib import Path

from .human_template import HUMAN_TEMPLATE


def _parse_persona_text(path: Path) -> str | None:
    try:
        module = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return None

    for node in module.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            if (
                node.targets[0].id == "PERSONA_TEXT"
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                return node.value.value
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if (
                node.target.id == "PERSONA_TEXT"
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                return node.value.value
    return None


def _discover_personas() -> dict[str, str]:
    personas: dict[str, str] = {}
    persona_dir = Path(__file__).resolve().parent

    for path in sorted(persona_dir.rglob("*.py")):
        if path.name == "__init__.py" or path.name.startswith("_"):
            continue
        rel = path.relative_to(persona_dir)
        if rel.parts and rel.parts[0] == "archive":
            continue
        persona_text = _parse_persona_text(path)
        if persona_text:
            personas[path.stem] = persona_text

    return personas


PERSONAS = _discover_personas()

__all__ = ["PERSONAS", "HUMAN_TEMPLATE"]
