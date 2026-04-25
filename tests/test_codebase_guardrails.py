from __future__ import annotations

import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEXT_ROOTS = (
    PROJECT_ROOT / "agent_platform_api",
    PROJECT_ROOT / "ade_core",
    PROJECT_ROOT / "model_router",
    PROJECT_ROOT / "scripts",
    PROJECT_ROOT / "tests",
    PROJECT_ROOT / ".github",
)


def _text_files() -> list[Path]:
    suffixes = {".py", ".md", ".yml", ".yaml", ".toml", ".json"}
    files: list[Path] = []
    for root in TEXT_ROOTS:
        if not root.exists():
            continue
        files.extend(
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in suffixes and "__pycache__" not in path.parts
        )
    return files


def test_no_utils_imports_reintroduced() -> None:
    offenders: list[str] = []
    for path in _text_files():
        if path.name == "test_codebase_guardrails.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "from utils" in text or "import utils" in text:
            offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert offenders == []


def test_removed_agent_platform_model_source_config_stays_removed() -> None:
    removed_env_key = "AGENT_PLATFORM_" + "MODEL_SOURCES"
    offenders: list[str] = []
    for path in _text_files():
        if path.name == "test_codebase_guardrails.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if removed_env_key in text:
            offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert offenders == []


def test_agent_platform_has_no_direct_provider_catalog_fallback() -> None:
    forbidden = (
        "direct-provider fallback",
        "legacy direct-provider",
        "ModelCatalogService",
        "model_catalog_service",
    )
    offenders: list[str] = []
    for path in (PROJECT_ROOT / "agent_platform_api").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(marker in text for marker in forbidden):
            offenders.append(str(path.relative_to(PROJECT_ROOT)))

    assert offenders == []


def test_no_tracked_generated_or_stale_artifacts() -> None:
    completed = subprocess.run(
        ["git", "ls-files"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    forbidden_fragments = (
        "__pycache__/",
        ".pyc",
        "frontend-ade/.next/",
        "frontend-ade/node_modules/",
        "temps/",
        "notebooks/zz",
        "data/agent_lifecycle/registry.json",
    )
    tracked = [line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()]
    offenders = [
        path
        for path in tracked
        if (PROJECT_ROOT / path).exists() and any(fragment in path for fragment in forbidden_fragments)
    ]

    assert offenders == []
