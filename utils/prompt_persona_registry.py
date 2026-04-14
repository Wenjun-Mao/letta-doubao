from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any, Literal

TemplateKind = Literal["prompt", "persona"]

_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
_META_LABEL = "LABEL"
_META_DESCRIPTION = "DESCRIPTION"
_PROMPT_VAR = "PROMPT"
_PERSONA_VAR = "PERSONA_TEXT"

_DEFAULT_PROMPT_META: dict[str, dict[str, str]] = {
    "custom_v2": {
        "label": "Custom V2 Chat (Default)",
        "description": "Recommended baseline for robust persona adherence and tool-flow behavior.",
    },
    "custom_v1": {
        "label": "Custom V1 (Alternate)",
        "description": "Alternate baseline kept for A/B testing and regression comparison.",
    },
}

_DEFAULT_PERSONA_META: dict[str, dict[str, str]] = {
    "linxiaotang": {
        "label": "Lin Xiao Tang",
        "description": "Default warm and gentle persona profile.",
    }
}


class RegistryError(ValueError):
    """Raised when prompt/persona registry operations fail."""


class PromptPersonaRegistry:
    """File-backed registry for system prompts and persona templates."""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        self.prompt_dir = self.project_root / "prompts" / "system_prompts"
        self.prompt_archive_dir = self.prompt_dir / "archive"
        self.persona_dir = self.project_root / "prompts" / "persona"
        self.persona_archive_dir = self.persona_dir / "archive"

        self.prompt_dir.mkdir(parents=True, exist_ok=True)
        self.persona_dir.mkdir(parents=True, exist_ok=True)
        self.prompt_archive_dir.mkdir(parents=True, exist_ok=True)
        self.persona_archive_dir.mkdir(parents=True, exist_ok=True)

    def list_templates(self, kind: TemplateKind, include_archived: bool = False) -> list[dict[str, Any]]:
        records = self._list_from_dir(kind=kind, archived=False)
        if include_archived:
            records.extend(self._list_from_dir(kind=kind, archived=True))
        records.sort(key=lambda item: (bool(item.get("archived")), str(item.get("key", ""))))
        return records

    def get_template(self, kind: TemplateKind, key: str, *, archived: bool = False) -> dict[str, Any] | None:
        normalized = self._normalize_key(key)
        file_path = self._file_path(kind=kind, key=normalized, archived=archived)
        if not file_path.exists():
            return None
        return self._parse_template_file(kind=kind, path=file_path, archived=archived)

    def create_template(
        self,
        kind: TemplateKind,
        *,
        key: str,
        content: str,
        label: str = "",
        description: str = "",
    ) -> dict[str, Any]:
        normalized = self._normalize_key(key)
        if self._file_path(kind=kind, key=normalized, archived=False).exists():
            raise RegistryError(f"{kind} '{normalized}' already exists")
        if self._file_path(kind=kind, key=normalized, archived=True).exists():
            raise RegistryError(f"{kind} '{normalized}' already exists in archive; restore it instead")

        source = self._render_source(
            kind=kind,
            key=normalized,
            content=content,
            label=label.strip(),
            description=description.strip(),
        )

        output_path = self._file_path(kind=kind, key=normalized, archived=False)
        output_path.write_text(source, encoding="utf-8")
        return self._parse_template_file(kind=kind, path=output_path, archived=False)

    def update_template(
        self,
        kind: TemplateKind,
        *,
        key: str,
        content: str | None = None,
        label: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        normalized = self._normalize_key(key)
        existing = self.get_template(kind=kind, key=normalized, archived=False)
        if not existing:
            raise RegistryError(f"{kind} '{normalized}' not found")

        next_content = str(existing.get("content", "") if content is None else content)
        next_label = str(existing.get("label", "") if label is None else label).strip()
        next_description = str(existing.get("description", "") if description is None else description).strip()

        source = self._render_source(
            kind=kind,
            key=normalized,
            content=next_content,
            label=next_label,
            description=next_description,
        )
        output_path = self._file_path(kind=kind, key=normalized, archived=False)
        output_path.write_text(source, encoding="utf-8")
        return self._parse_template_file(kind=kind, path=output_path, archived=False)

    def archive_template(self, kind: TemplateKind, key: str) -> dict[str, Any]:
        normalized = self._normalize_key(key)
        active_path = self._file_path(kind=kind, key=normalized, archived=False)
        archived_path = self._file_path(kind=kind, key=normalized, archived=True)
        if not active_path.exists():
            raise RegistryError(f"{kind} '{normalized}' not found")
        if archived_path.exists():
            raise RegistryError(f"Archive collision for {kind} '{normalized}'")

        archived_path.parent.mkdir(parents=True, exist_ok=True)
        active_path.replace(archived_path)
        return self._parse_template_file(kind=kind, path=archived_path, archived=True)

    def restore_template(self, kind: TemplateKind, key: str) -> dict[str, Any]:
        normalized = self._normalize_key(key)
        active_path = self._file_path(kind=kind, key=normalized, archived=False)
        archived_path = self._file_path(kind=kind, key=normalized, archived=True)
        if not archived_path.exists():
            raise RegistryError(f"Archived {kind} '{normalized}' not found")
        if active_path.exists():
            raise RegistryError(f"{kind} '{normalized}' already exists")

        active_path.parent.mkdir(parents=True, exist_ok=True)
        archived_path.replace(active_path)
        return self._parse_template_file(kind=kind, path=active_path, archived=False)

    def purge_template(self, kind: TemplateKind, key: str) -> None:
        normalized = self._normalize_key(key)
        archived_path = self._file_path(kind=kind, key=normalized, archived=True)
        if not archived_path.exists():
            raise RegistryError(f"Archived {kind} '{normalized}' not found")
        archived_path.unlink()

    def _normalize_key(self, key: str) -> str:
        normalized = str(key or "").strip().lower()
        if not _KEY_PATTERN.fullmatch(normalized):
            raise RegistryError(
                "Invalid key. Use 2-64 chars with lowercase letters, numbers, underscores, or hyphens; must start with a letter."
            )
        return normalized

    def _dirs_for_kind(self, kind: TemplateKind) -> tuple[Path, Path]:
        if kind == "prompt":
            return self.prompt_dir, self.prompt_archive_dir
        if kind == "persona":
            return self.persona_dir, self.persona_archive_dir
        raise RegistryError(f"Unsupported template kind: {kind}")

    def _content_var_for_kind(self, kind: TemplateKind) -> str:
        return _PROMPT_VAR if kind == "prompt" else _PERSONA_VAR

    def _default_meta_for_kind(self, kind: TemplateKind, key: str) -> dict[str, str]:
        defaults = _DEFAULT_PROMPT_META if kind == "prompt" else _DEFAULT_PERSONA_META
        if key in defaults:
            return dict(defaults[key])
        pretty = key.replace("-", " ").replace("_", " ").title()
        return {
            "label": pretty,
            "description": f"{pretty} template managed in workspace files.",
        }

    def _file_path(self, kind: TemplateKind, key: str, archived: bool) -> Path:
        active_dir, archived_dir = self._dirs_for_kind(kind)
        base = archived_dir if archived else active_dir
        return base / f"{key}.py"

    def _list_from_dir(self, kind: TemplateKind, archived: bool) -> list[dict[str, Any]]:
        active_dir, archived_dir = self._dirs_for_kind(kind)
        base_dir = archived_dir if archived else active_dir
        if not base_dir.exists():
            return []

        records: list[dict[str, Any]] = []
        for file_path in sorted(base_dir.glob("*.py")):
            if file_path.name == "__init__.py" or file_path.name.startswith("_"):
                continue
            try:
                parsed = self._parse_template_file(kind=kind, path=file_path, archived=archived)
            except RegistryError as exc:
                # Skip helper modules that are not template files (missing PROMPT/PERSONA_TEXT constant).
                if "does not define required variable" in str(exc):
                    continue
                raise
            if parsed:
                records.append(parsed)
        return records

    def _parse_template_file(self, kind: TemplateKind, path: Path, archived: bool) -> dict[str, Any]:
        content_var = self._content_var_for_kind(kind)
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
        defaults = self._default_meta_for_kind(kind, key)
        module_doc = ast.get_docstring(module) or ""
        module_doc_preview = module_doc.strip().splitlines()[0].strip() if module_doc.strip() else ""

        label = str(assignments.get(_META_LABEL, defaults["label"]))
        description = str(assignments.get(_META_DESCRIPTION, defaults["description"]))
        if not description and module_doc_preview:
            description = module_doc_preview

        content = str(assignments.get(content_var, ""))
        stat = path.stat()
        return {
            "kind": kind,
            "key": key,
            "label": label,
            "description": description,
            "content": content,
            "preview": self._first_non_empty_line(content)[:180],
            "length": len(content),
            "archived": archived,
            "source_path": path.relative_to(self.project_root).as_posix(),
            "updated_at": str(stat.st_mtime),
        }

    @staticmethod
    def _first_non_empty_line(text: str) -> str:
        for line in str(text or "").splitlines():
            cleaned = line.strip()
            if cleaned:
                return cleaned
        return ""

    def _render_source(
        self,
        *,
        kind: TemplateKind,
        key: str,
        content: str,
        label: str,
        description: str,
    ) -> str:
        defaults = self._default_meta_for_kind(kind, key)
        resolved_label = label or defaults["label"]
        resolved_description = description or defaults["description"]
        content_var = self._content_var_for_kind(kind)
        header = "Auto-generated by ADE Prompt Center."

        lines = [
            '"""',
            header,
            '"""',
            "",
            f"{_META_LABEL} = {json.dumps(resolved_label, ensure_ascii=False)}",
            f"{_META_DESCRIPTION} = {json.dumps(resolved_description, ensure_ascii=False)}",
            f"{content_var} = {json.dumps(str(content), ensure_ascii=False)}",
            "",
        ]
        return "\n".join(lines)
