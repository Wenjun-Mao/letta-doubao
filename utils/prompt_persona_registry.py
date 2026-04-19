from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any, Literal

TemplateKind = Literal["prompt", "persona"]
ScenarioKind = Literal["chat", "comment"]

_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
_META_LABEL = "LABEL"
_META_DESCRIPTION = "DESCRIPTION"
_PROMPT_VAR = "PROMPT"
_PERSONA_VAR = "PERSONA_TEXT"
_KNOWN_SCENARIOS: tuple[ScenarioKind, ...] = ("chat", "comment")

_DEFAULT_PROMPT_META: dict[str, dict[str, str]] = {
    "chat_v20260418": {
        "label": "Chat V20260418",
        "description": "Chat scenario prompt baseline for memory-augmented user conversations.",
    },
    "comment_v20260418": {
        "label": "Comment V20260418",
        "description": "Comment scenario prompt baseline for stateless news and thread responses.",
    },
}

_DEFAULT_PERSONA_META: dict[str, dict[str, str]] = {
    "chat_linxiaotang": {
        "label": "Chat Lin Xiao Tang",
        "description": "Default chat persona profile for warm conversational replies.",
    },
    "comment_linxiaotang": {
        "label": "Comment Lin Xiao Tang",
        "description": "Default commenting persona profile for concise public discussion.",
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

    def list_templates(
        self,
        kind: TemplateKind,
        include_archived: bool = False,
        scenario: ScenarioKind | None = None,
    ) -> list[dict[str, Any]]:
        resolved_scenario = self._normalize_scenario(scenario, allow_none=True)
        records = self._list_from_dir(kind=kind, archived=False, scenario=resolved_scenario)
        if include_archived:
            records.extend(self._list_from_dir(kind=kind, archived=True, scenario=resolved_scenario))
        records.sort(
            key=lambda item: (
                bool(item.get("archived")),
                str(item.get("scenario", "")),
                str(item.get("key", "")),
            )
        )
        return records

    def get_template(
        self,
        kind: TemplateKind,
        key: str,
        *,
        archived: bool = False,
        scenario: ScenarioKind | None = None,
    ) -> dict[str, Any] | None:
        normalized = self._normalize_key(key)
        resolved_scenario = self._normalize_scenario(scenario, allow_none=True)
        file_path = self._find_template_path(
            kind=kind,
            key=normalized,
            archived=archived,
            scenario=resolved_scenario,
        )
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
        scenario: ScenarioKind = "chat",
    ) -> dict[str, Any]:
        normalized = self._normalize_key(key)
        resolved_scenario = self._normalize_scenario(scenario)
        self._validate_key_scenario(normalized, resolved_scenario)

        if self._find_template_path(kind=kind, key=normalized, archived=False, scenario=None).exists():
            raise RegistryError(f"{kind} '{normalized}' already exists")
        if self._find_template_path(kind=kind, key=normalized, archived=True, scenario=None).exists():
            raise RegistryError(f"{kind} '{normalized}' already exists in archive; restore it instead")

        source = self._render_source(
            kind=kind,
            key=normalized,
            content=content,
            label=label.strip(),
            description=description.strip(),
        )

        output_path = self._file_path_for_create(
            kind=kind,
            key=normalized,
            scenario=resolved_scenario,
            archived=False,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
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
        existing_path = self._find_template_path(kind=kind, key=normalized, archived=False, scenario=None)
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
        existing_path.write_text(source, encoding="utf-8")
        return self._parse_template_file(kind=kind, path=existing_path, archived=False)

    def archive_template(self, kind: TemplateKind, key: str, scenario: ScenarioKind | None = None) -> dict[str, Any]:
        normalized = self._normalize_key(key)
        resolved_scenario = self._normalize_scenario(scenario, allow_none=True)
        active_path = self._find_template_path(
            kind=kind,
            key=normalized,
            archived=False,
            scenario=resolved_scenario,
        )
        active_dir, archived_dir = self._dirs_for_kind(kind)
        archived_path = archived_dir / active_path.relative_to(active_dir)
        if not active_path.exists():
            raise RegistryError(f"{kind} '{normalized}' not found")
        if archived_path.exists():
            raise RegistryError(f"Archive collision for {kind} '{normalized}'")

        archived_path.parent.mkdir(parents=True, exist_ok=True)
        active_path.replace(archived_path)
        return self._parse_template_file(kind=kind, path=archived_path, archived=True)

    def restore_template(self, kind: TemplateKind, key: str, scenario: ScenarioKind | None = None) -> dict[str, Any]:
        normalized = self._normalize_key(key)
        resolved_scenario = self._normalize_scenario(scenario, allow_none=True)
        archived_path = self._find_template_path(
            kind=kind,
            key=normalized,
            archived=True,
            scenario=resolved_scenario,
        )
        active_dir, archived_dir = self._dirs_for_kind(kind)
        active_path = active_dir / archived_path.relative_to(archived_dir)
        if not archived_path.exists():
            raise RegistryError(f"Archived {kind} '{normalized}' not found")
        if active_path.exists():
            raise RegistryError(f"{kind} '{normalized}' already exists")

        active_path.parent.mkdir(parents=True, exist_ok=True)
        archived_path.replace(active_path)
        return self._parse_template_file(kind=kind, path=active_path, archived=False)

    def purge_template(self, kind: TemplateKind, key: str, scenario: ScenarioKind | None = None) -> None:
        normalized = self._normalize_key(key)
        resolved_scenario = self._normalize_scenario(scenario, allow_none=True)
        archived_path = self._find_template_path(
            kind=kind,
            key=normalized,
            archived=True,
            scenario=resolved_scenario,
        )
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

    def _normalize_scenario(self, scenario: str | None, allow_none: bool = False) -> ScenarioKind | None:
        if scenario is None:
            return None if allow_none else "chat"
        normalized = str(scenario or "").strip().lower()
        if not normalized:
            return None if allow_none else "chat"
        if normalized not in _KNOWN_SCENARIOS:
            raise RegistryError(f"Unsupported scenario: {scenario}")
        return normalized

    def _validate_key_scenario(self, key: str, scenario: ScenarioKind) -> None:
        required_prefix = f"{scenario}_"
        if not key.startswith(required_prefix):
            raise RegistryError(
                f"Key '{key}' must start with '{required_prefix}' for scenario '{scenario}'."
            )

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

    def _file_path_for_create(self, kind: TemplateKind, key: str, scenario: ScenarioKind, archived: bool) -> Path:
        active_dir, archived_dir = self._dirs_for_kind(kind)
        base = archived_dir if archived else active_dir
        return base / scenario / f"{key}.py"

    def _find_template_path(
        self,
        *,
        kind: TemplateKind,
        key: str,
        archived: bool,
        scenario: ScenarioKind | None,
    ) -> Path:
        active_dir, archived_dir = self._dirs_for_kind(kind)
        base_dir = archived_dir if archived else active_dir
        if not base_dir.exists():
            return base_dir / f"{key}.py"

        matches: list[Path] = []
        for file_path in sorted(base_dir.rglob("*.py")):
            if file_path.name == "__init__.py" or file_path.name.startswith("_"):
                continue
            rel = file_path.relative_to(base_dir)
            if not archived and rel.parts and rel.parts[0] == "archive":
                continue
            if file_path.stem != key:
                continue
            inferred_scenario = self._infer_scenario_from_path(file_path, base_dir)
            if scenario and inferred_scenario != scenario:
                continue
            matches.append(file_path)

        if len(matches) > 1:
            raise RegistryError(
                f"Key collision for {kind} '{key}' across scenarios. Use explicit scenario filter."
            )
        if matches:
            return matches[0]

        if scenario:
            return base_dir / scenario / f"{key}.py"
        return base_dir / f"{key}.py"

    def _infer_scenario_from_path(self, path: Path, base_dir: Path) -> ScenarioKind:
        rel = path.relative_to(base_dir)
        if rel.parts:
            first = str(rel.parts[0]).strip().lower()
            if first in _KNOWN_SCENARIOS:
                return first

        key = path.stem
        if key.startswith("comment_"):
            return "comment"
        return "chat"

    def _list_from_dir(
        self,
        kind: TemplateKind,
        archived: bool,
        scenario: ScenarioKind | None,
    ) -> list[dict[str, Any]]:
        active_dir, archived_dir = self._dirs_for_kind(kind)
        base_dir = archived_dir if archived else active_dir
        if not base_dir.exists():
            return []

        records: list[dict[str, Any]] = []
        for file_path in sorted(base_dir.rglob("*.py")):
            if file_path.name == "__init__.py" or file_path.name.startswith("_"):
                continue
            rel = file_path.relative_to(base_dir)
            if not archived and rel.parts and rel.parts[0] == "archive":
                continue
            try:
                parsed = self._parse_template_file(kind=kind, path=file_path, archived=archived)
            except RegistryError as exc:
                # Skip helper modules that are not template files (missing PROMPT/PERSONA_TEXT constant).
                if "does not define required variable" in str(exc):
                    continue
                raise
            if scenario and str(parsed.get("scenario", "")) != scenario:
                continue
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
        active_dir, archived_dir = self._dirs_for_kind(kind)
        base_dir = archived_dir if archived else active_dir
        scenario = self._infer_scenario_from_path(path, base_dir)
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
            "scenario": scenario,
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
