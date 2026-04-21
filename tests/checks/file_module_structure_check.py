from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOFT_LINE_LIMIT = 400
HARD_LINE_LIMIT = 500
SKIP_DIRS = {
    ".git",
    ".venv",
    ".playwright-mcp",
    "__pycache__",
    "frontend-ade",
    "notebooks",
}
SOFT_LIMIT_EXCEPTIONS = {
    Path("agent_platform_api/routers/agents.py"): "Agent routes are grouped by API surface and should be revisited if more endpoints are added.",
    Path("tests/checks/comment_shape_ab_benchmark.py"): "Benchmark harness is still a single scenario runner.",
    Path("utils/prompt_persona_registry.py"): "Registry persistence and metadata shaping still live together.",
}
HARD_LIMIT_EXCEPTIONS = {
    Path("scripts/generate_openapi_zh_manual.py"): "OpenAPI translation catalog is still inline.",
    Path("tests/runners/memory_update_runner.py"): "Legacy runner still mixes CLI parsing, orchestration, and artifact output.",
    Path("tests/runners/persona_guardrail_runner.py"): "Legacy runner still mixes config loading, orchestration, and reporting.",
}


def iter_project_python_files() -> list[Path]:
    paths: list[Path] = []
    for path in PROJECT_ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        paths.append(path.relative_to(PROJECT_ROOT))
    return sorted(paths)


def line_count(path: Path) -> int:
    return sum(1 for _ in (PROJECT_ROOT / path).open("r", encoding="utf-8"))


def test_no_unapproved_oversized_python_modules():
    soft_violations: list[str] = []
    hard_violations: list[str] = []

    for relative_path in iter_project_python_files():
        count = line_count(relative_path)
        if count > HARD_LINE_LIMIT and relative_path not in HARD_LIMIT_EXCEPTIONS:
            hard_violations.append(f"{relative_path} ({count} lines)")
            continue
        if (
            count > SOFT_LINE_LIMIT
            and relative_path not in SOFT_LIMIT_EXCEPTIONS
            and relative_path not in HARD_LIMIT_EXCEPTIONS
        ):
            soft_violations.append(f"{relative_path} ({count} lines)")

    assert not hard_violations, (
        "Python files above the 500-line hard limit must be split:\n"
        + "\n".join(hard_violations)
    )
    assert not soft_violations, (
        "Python files above the 400-line advisory limit should be split or explicitly documented:\n"
        + "\n".join(soft_violations)
    )


def test_no_catch_all_utils_modules():
    offenders = [str(path) for path in iter_project_python_files() if path.name == "utils.py"]
    assert not offenders, "Catch-all utils.py modules are not allowed:\n" + "\n".join(offenders)
