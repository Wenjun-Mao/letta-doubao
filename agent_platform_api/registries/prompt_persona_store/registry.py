from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_platform_api.registries.prompt_persona_store.codec import parse_template_file, render_source
from agent_platform_api.registries.prompt_persona_store.paths import PromptPersonaPaths
from agent_platform_api.registries.prompt_persona_store.types import (
    KEY_PATTERN,
    KNOWN_SCENARIOS,
    RegistryError,
    ScenarioKind,
    TemplateKind,
)


class PromptPersonaRegistry:
    """File-backed registry for system prompts and persona templates."""

    def __init__(self, project_root: Path):
        self.paths = PromptPersonaPaths.from_project_root(project_root)
        self.project_root = self.paths.project_root
        self.prompt_dir = self.paths.prompt_dir
        self.prompt_archive_dir = self.paths.prompt_archive_dir
        self.persona_dir = self.paths.persona_dir
        self.persona_archive_dir = self.paths.persona_archive_dir
        self.paths.ensure_dirs()

    def list_templates(
        self,
        kind: TemplateKind,
        include_archived: bool = False,
        scenario: ScenarioKind | None = None,
    ) -> list[dict[str, Any]]:
        resolved_scenario = self._normalize_scenario(scenario, allow_none=True)
        if self._is_unsupported_persona_scenario(kind, resolved_scenario):
            return []
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
        if self._is_unsupported_persona_scenario(kind, resolved_scenario):
            return None
        file_path = self.paths.find_template_path(
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
        label: str | None = None,
        description: str | None = None,
        scenario: ScenarioKind | None = None,
    ) -> dict[str, Any]:
        normalized = self._normalize_key(key)
        resolved_scenario = self._normalize_scenario(scenario, allow_none=True) or self._infer_scenario_from_key(normalized)
        self._ensure_supported_persona_scenario(kind, resolved_scenario)
        self._validate_key_scenario(normalized, resolved_scenario)

        if self.paths.find_template_path(kind=kind, key=normalized, archived=False, scenario=None).exists():
            raise RegistryError(f"{kind} '{normalized}' already exists")
        if self.paths.find_template_path(kind=kind, key=normalized, archived=True, scenario=None).exists():
            raise RegistryError(f"{kind} '{normalized}' already exists in archive; restore it instead")

        source = render_source(
            kind=kind,
            content=content,
            label=str(label or "").strip() or None,
            description=str(description or "").strip() or None,
        )

        output_path = self.paths.file_path_for_create(
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
        scenario: ScenarioKind | None = None,
    ) -> dict[str, Any]:
        normalized = self._normalize_key(key)
        resolved_scenario = self._normalize_scenario(scenario, allow_none=True)
        self._ensure_supported_persona_scenario(kind, resolved_scenario)
        existing_path = self.paths.find_template_path(
            kind=kind,
            key=normalized,
            archived=False,
            scenario=resolved_scenario,
        )
        existing = self.get_template(
            kind=kind,
            key=normalized,
            archived=False,
            scenario=resolved_scenario,
        )
        if not existing:
            raise RegistryError(f"{kind} '{normalized}' not found")

        next_content = str(existing.get("content", "") if content is None else content)
        next_label = str(existing.get("label", "") if label is None else label).strip()
        next_description = str(existing.get("description", "") if description is None else description).strip()

        source = render_source(
            kind=kind,
            content=next_content,
            label=next_label,
            description=next_description,
        )
        existing_path.write_text(source, encoding="utf-8")
        return self._parse_template_file(kind=kind, path=existing_path, archived=False)

    def archive_template(self, kind: TemplateKind, key: str, scenario: ScenarioKind | None = None) -> dict[str, Any]:
        normalized = self._normalize_key(key)
        resolved_scenario = self._normalize_scenario(scenario, allow_none=True)
        self._ensure_supported_persona_scenario(kind, resolved_scenario)
        active_path = self.paths.find_template_path(
            kind=kind,
            key=normalized,
            archived=False,
            scenario=resolved_scenario,
        )
        active_dir, archived_dir = self.paths.dirs_for_kind(kind)
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
        self._ensure_supported_persona_scenario(kind, resolved_scenario)
        archived_path = self.paths.find_template_path(
            kind=kind,
            key=normalized,
            archived=True,
            scenario=resolved_scenario,
        )
        active_dir, archived_dir = self.paths.dirs_for_kind(kind)
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
        self._ensure_supported_persona_scenario(kind, resolved_scenario)
        archived_path = self.paths.find_template_path(
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
        if not KEY_PATTERN.fullmatch(normalized):
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
        if normalized not in KNOWN_SCENARIOS:
            raise RegistryError(f"Unsupported scenario: {scenario}")
        return normalized  # type: ignore[return-value]

    def _validate_key_scenario(self, key: str, scenario: ScenarioKind) -> None:
        required_prefix = f"{scenario}_"
        if not key.startswith(required_prefix):
            raise RegistryError(
                f"Key '{key}' must start with '{required_prefix}' for scenario '{scenario}'."
            )

    def _infer_scenario_from_key(self, key: str) -> ScenarioKind:
        normalized = self._normalize_key(key)
        for scenario in KNOWN_SCENARIOS:
            if normalized.startswith(f"{scenario}_"):
                return scenario
        raise RegistryError(
            "Unable to infer scenario from key. Prefix template keys with 'chat_', 'comment_', or 'label_'."
        )

    @staticmethod
    def _is_unsupported_persona_scenario(kind: TemplateKind, scenario: ScenarioKind | None) -> bool:
        return kind == "persona" and scenario == "label"

    def _ensure_supported_persona_scenario(self, kind: TemplateKind, scenario: ScenarioKind | None) -> None:
        if self._is_unsupported_persona_scenario(kind, scenario):
            raise RegistryError("Label scenario does not support persona templates.")

    def _list_from_dir(
        self,
        kind: TemplateKind,
        archived: bool,
        scenario: ScenarioKind | None,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for file_path in self.paths.iter_template_files(kind=kind, archived=archived):
            try:
                parsed = self._parse_template_file(kind=kind, path=file_path, archived=archived)
            except RegistryError as exc:
                if "does not define required variable" in str(exc):
                    continue
                raise
            if scenario and str(parsed.get("scenario", "")) != scenario:
                continue
            if parsed:
                records.append(parsed)
        return records

    def _parse_template_file(self, kind: TemplateKind, path: Path, archived: bool) -> dict[str, Any]:
        return parse_template_file(kind=kind, path=path, archived=archived, paths=self.paths)
