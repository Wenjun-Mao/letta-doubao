from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_platform_api.registries.prompt_persona_store.types import (
    KNOWN_SCENARIOS,
    RegistryError,
    ScenarioKind,
    TemplateKind,
)


@dataclass(frozen=True)
class PromptPersonaPaths:
    project_root: Path
    prompt_dir: Path
    prompt_archive_dir: Path
    persona_dir: Path
    persona_archive_dir: Path

    @classmethod
    def from_project_root(cls, project_root: Path) -> "PromptPersonaPaths":
        resolved_project_root = Path(project_root).resolve()
        return cls(
            project_root=resolved_project_root,
            prompt_dir=resolved_project_root / "prompts" / "system_prompts",
            prompt_archive_dir=resolved_project_root / "prompts" / "system_prompts" / "archive",
            persona_dir=resolved_project_root / "prompts" / "persona",
            persona_archive_dir=resolved_project_root / "prompts" / "persona" / "archive",
        )

    def ensure_dirs(self) -> None:
        self.prompt_dir.mkdir(parents=True, exist_ok=True)
        self.persona_dir.mkdir(parents=True, exist_ok=True)
        self.prompt_archive_dir.mkdir(parents=True, exist_ok=True)
        self.persona_archive_dir.mkdir(parents=True, exist_ok=True)

    def dirs_for_kind(self, kind: TemplateKind) -> tuple[Path, Path]:
        if kind == "prompt":
            return self.prompt_dir, self.prompt_archive_dir
        if kind == "persona":
            return self.persona_dir, self.persona_archive_dir
        raise RegistryError(f"Unsupported template kind: {kind}")

    def file_path_for_create(self, kind: TemplateKind, key: str, scenario: ScenarioKind, archived: bool) -> Path:
        active_dir, archived_dir = self.dirs_for_kind(kind)
        base = archived_dir if archived else active_dir
        return base / scenario / f"{key}.py"

    def find_template_path(
        self,
        *,
        kind: TemplateKind,
        key: str,
        archived: bool,
        scenario: ScenarioKind | None,
    ) -> Path:
        active_dir, archived_dir = self.dirs_for_kind(kind)
        base_dir = archived_dir if archived else active_dir
        if not base_dir.exists():
            return base_dir / f"{key}.py"

        matches: list[Path] = []
        for file_path in self.iter_template_files(kind=kind, archived=archived):
            if file_path.stem != key:
                continue
            inferred_scenario = self.infer_scenario_from_path(kind=kind, path=file_path, archived=archived)
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

    def iter_template_files(self, *, kind: TemplateKind, archived: bool) -> list[Path]:
        active_dir, archived_dir = self.dirs_for_kind(kind)
        base_dir = archived_dir if archived else active_dir
        if not base_dir.exists():
            return []

        files: list[Path] = []
        for file_path in sorted(base_dir.rglob("*.py")):
            if file_path.name == "__init__.py" or file_path.name.startswith("_"):
                continue
            rel = file_path.relative_to(base_dir)
            if not archived and rel.parts and rel.parts[0] == "archive":
                continue
            files.append(file_path)
        return files

    def infer_scenario_from_path(self, *, kind: TemplateKind, path: Path, archived: bool) -> ScenarioKind:
        active_dir, archived_dir = self.dirs_for_kind(kind)
        base_dir = archived_dir if archived else active_dir
        rel = path.relative_to(base_dir)
        if rel.parts:
            first = str(rel.parts[0]).strip().lower()
            if first in KNOWN_SCENARIOS:
                return first  # type: ignore[return-value]

        key = path.stem
        if key.startswith("comment_"):
            return "comment"
        if key.startswith("label_"):
            return "label"
        return "chat"
