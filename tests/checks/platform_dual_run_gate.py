from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHECKS: list[tuple[str, str]] = [
    ("backend_platform_api_e2e", "tests/checks/platform_api_e2e_check.py"),
    ("agent_archive_e2e", "tests/checks/agent_archive_api_check.py"),
    ("prompt_tool_archive_e2e", "tests/checks/prompt_tool_archive_api_check.py"),
    ("ade_mvp_smoke_e2e", "tests/checks/ade_mvp_smoke_e2e_check.py"),
]


def _as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _tail(text: str, max_lines: int = 120) -> list[str]:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) <= max_lines:
        return lines
    return lines[-max_lines:]


def _run_check(name: str, script_path: str) -> dict[str, Any]:
    script = (PROJECT_ROOT / script_path).resolve()
    if not script.exists():
        raise RuntimeError(f"Check script not found: {script}")

    command = [sys.executable, str(script)]
    started_at = time.time()
    completed = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    duration_seconds = round(time.time() - started_at, 3)

    return {
        "name": name,
        "script": script_path,
        "ok": completed.returncode == 0,
        "exit_code": int(completed.returncode),
        "duration_seconds": duration_seconds,
        "stdout_tail": _tail(completed.stdout),
        "stderr_tail": _tail(completed.stderr),
    }


def main() -> None:
    summary: dict[str, Any] = {
        "name": "platform_dual_run_gate",
        "ok": False,
        "checks": [],
        "detail": "",
    }

    for check_name, script_path in CHECKS:
        result = _run_check(check_name, script_path)
        summary["checks"].append(result)
        if not result["ok"]:
            summary["detail"] = f"Gate failed at {check_name}"
            print(_as_json(summary))
            raise RuntimeError(summary["detail"])

    summary["ok"] = True
    summary["detail"] = "Backend platform E2E and ADE smoke suite both passed"
    print(_as_json(summary))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[FAIL] platform_dual_run_gate: {exc}")
        raise
