from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from agent_platform_api.registries.prompt_persona_store.defaults import (
    GENERATED_MODULE_DOC,
    default_meta_for_kind,
)
from agent_platform_api.registries.prompt_persona_store.paths import PromptPersonaPaths
from agent_platform_api.registries.prompt_persona_store.types import (
    META_DESCRIPTION,
    META_LABEL,
    OUTPUT_SCHEMA_VAR,
    PERSONA_VAR,
    PROMPT_VAR,
    RegistryError,
    TemplateKind,
)


def content_var_for_kind(kind: TemplateKind) -> str:
    return PROMPT_VAR if kind == "prompt" else PERSONA_VAR


def parse_template_file(
    *,
    kind: TemplateKind,
    path: Path,
    archived: bool,
    paths: PromptPersonaPaths,
) -> dict[str, Any]:
    content_var = content_var_for_kind(kind)
    text = path.read_text(encoding="utf-8", errors="replace")

    try:
        module = ast.parse(text)
    except SyntaxError as exc:
        raise RegistryError(f"Invalid Python syntax in {path}: {exc}") from exc

    assignments: dict[str, str] = {}
    for node in module.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            key_name = node.targets[0].id
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                assignments[key_name] = node.value.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            key_name = node.target.id
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                assignments[key_name] = node.value.value

    if content_var not in assignments:
        raise RegistryError(f"{path} does not define required variable '{content_var}'")

    key = path.stem
    scenario = paths.infer_scenario_from_path(kind=kind, path=path, archived=archived)
    defaults = default_meta_for_kind(kind, key)
    module_doc = ast.get_docstring(module) or ""
    module_doc_preview = module_doc.strip().splitlines()[0].strip() if module_doc.strip() else ""

    label = str(assignments.get(META_LABEL, defaults["label"]))
    description = str(assignments.get(META_DESCRIPTION, defaults["description"]))
    if not description and module_doc_preview and module_doc_preview != GENERATED_MODULE_DOC:
        description = module_doc_preview

    content = str(assignments.get(content_var, ""))
    output_schema = None
    if kind == "prompt":
        output_schema = str(assignments.get(OUTPUT_SCHEMA_VAR, "") or "").strip() or None
    stat = path.stat()
    return {
        "kind": kind,
        "scenario": scenario,
        "key": key,
        "label": label,
        "description": description,
        "content": content,
        "preview": first_non_empty_line(content)[:180],
        "length": len(content),
        "archived": archived,
        "source_path": path.relative_to(paths.project_root).as_posix(),
        "updated_at": str(stat.st_mtime),
        "output_schema": output_schema,
    }


def first_non_empty_line(text: str) -> str:
    for line in str(text or "").splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned
    return ""


def render_source(
    *,
    kind: TemplateKind,
    content: str,
    label: str | None,
    description: str | None,
) -> str:
    content_var = content_var_for_kind(kind)
    resolved_label = str(label or "").strip()
    resolved_description = str(description or "").strip()

    lines = [
        '"""',
        GENERATED_MODULE_DOC,
        '"""',
        "",
    ]
    if resolved_label:
        lines.append(f"{META_LABEL} = {json.dumps(resolved_label, ensure_ascii=False)}")
    if resolved_description:
        lines.append(f"{META_DESCRIPTION} = {json.dumps(resolved_description, ensure_ascii=False)}")
    lines.extend(
        [
            f"{content_var} = {json.dumps(str(content), ensure_ascii=False)}",
            "",
        ]
    )
    return "\n".join(lines)
