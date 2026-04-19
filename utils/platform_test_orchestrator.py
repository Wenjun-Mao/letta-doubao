from __future__ import annotations

import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tests.shared.config_defaults import DEFAULT_EMBEDDING_HANDLE, DEFAULT_TEST_MODEL_HANDLE


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_SUMMARY_WRITTEN_PATTERN = re.compile(r"Summary written to:\\s*(.+)$")
_RUNNER_OUTPUT_PATTERN = re.compile(r"\\boutput=(.+\\.json)\\s*$")


class PlatformTestOrchestrator:
    """In-process orchestrator for launching and tracking test runs."""

    def __init__(self, project_root: Path):
        self._project_root = project_root
        self._log_root = (project_root / "tests" / "outputs" / "platform_orchestrator").resolve()
        self._log_root.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._runs: dict[str, dict[str, Any]] = {}

    def _build_command(
        self,
        *,
        run_type: str,
        model: str,
        embedding: str,
        rounds: int,
        config_path: str,
    ) -> list[str]:
        python = sys.executable

        if run_type == "agent_bootstrap_check":
            return [
                python,
                "tests/checks/agent_bootstrap_check.py",
                "--model",
                model,
                "--embedding",
                embedding,
            ]
        if run_type == "provider_embedding_matrix_check":
            return [python, "tests/checks/provider_embedding_matrix_check.py"]
        if run_type == "prompt_strategy_check":
            return [python, "tests/checks/prompt_strategy_check.py"]
        if run_type == "platform_api_e2e_check":
            return [python, "tests/checks/platform_api_e2e_check.py"]
        if run_type == "ade_mvp_smoke_e2e_check":
            return [python, "tests/checks/ade_mvp_smoke_e2e_check.py"]
        if run_type == "platform_flag_gate_check":
            return [python, "tests/checks/platform_flag_gate_check.py"]
        if run_type == "platform_dual_run_gate":
            return [python, "tests/checks/platform_dual_run_gate.py"]
        if run_type == "persona_guardrail_runner":
            return [
                python,
                "tests/runners/persona_guardrail_runner.py",
                "--config",
                config_path,
                "--model",
                model,
                "--embedding",
                embedding,
            ]
        if run_type == "memory_update_runner":
            return [
                python,
                "tests/runners/memory_update_runner.py",
                "--rounds",
                str(rounds),
                "--model",
                model,
                "--embedding",
                embedding,
                "--turn",
                "你好，我叫张伟",
            ]

        raise ValueError(f"Unsupported run_type: {run_type}")

    def _public_record(self, run: dict[str, Any]) -> dict[str, Any]:
        artifacts = self._resolve_artifacts(run)
        return {
            "run_id": run["run_id"],
            "run_type": run["run_type"],
            "status": run["status"],
            "command": list(run["command"]),
            "created_at": run["created_at"],
            "started_at": run.get("started_at", ""),
            "finished_at": run.get("finished_at", ""),
            "exit_code": run.get("exit_code"),
            "log_file": run.get("log_file", ""),
            "cancel_requested": bool(run.get("cancel_requested", False)),
            "output_tail": list(run.get("output_tail", [])),
            "error": run.get("error", ""),
            "artifacts": artifacts,
        }

    def _summary_paths_from_log(self, log_file: str) -> list[Path]:
        log_path = Path(log_file).resolve()
        if not log_path.exists():
            return []

        summary_paths: list[Path] = []
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            summary_match = _SUMMARY_WRITTEN_PATTERN.search(line)
            if summary_match:
                raw_path = summary_match.group(1).strip()
                if raw_path:
                    candidate = Path(raw_path)
                    if not candidate.is_absolute():
                        candidate = (self._project_root / candidate).resolve()
                    summary_paths.append(candidate)

            output_match = _RUNNER_OUTPUT_PATTERN.search(line)
            if output_match:
                raw_path = output_match.group(1).strip()
                if raw_path:
                    candidate = Path(raw_path)
                    if not candidate.is_absolute():
                        candidate = (self._project_root / candidate).resolve()
                    summary_paths.append(candidate)

        seen: set[str] = set()
        unique: list[Path] = []
        for path in summary_paths:
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            unique.append(path)
        return unique

    def _resolve_artifacts(self, run: dict[str, Any]) -> list[dict[str, Any]]:
        artifacts: list[dict[str, Any]] = []

        log_file = str(run.get("log_file", "") or "")
        if log_file:
            log_path = Path(log_file).resolve()
            artifacts.append(
                {
                    "artifact_id": "orchestrator_log",
                    "type": "log",
                    "path": str(log_path),
                    "exists": log_path.exists(),
                    "size_bytes": log_path.stat().st_size if log_path.exists() else 0,
                }
            )

            for index, summary_path in enumerate(self._summary_paths_from_log(log_file)):
                artifacts.append(
                    {
                        "artifact_id": f"summary_{index}",
                        "type": "summary",
                        "path": str(summary_path),
                        "exists": summary_path.exists(),
                        "size_bytes": summary_path.stat().st_size if summary_path.exists() else 0,
                    }
                )

        return artifacts

    def create_run(
        self,
        *,
        run_type: str,
        model: str | None,
        embedding: str | None,
        rounds: int | None,
        config_path: str | None,
    ) -> dict[str, Any]:
        resolved_model = (model or "").strip() or DEFAULT_TEST_MODEL_HANDLE
        resolved_embedding = (embedding or "").strip() or DEFAULT_EMBEDDING_HANDLE
        resolved_rounds = max(1, int(rounds or 10))
        resolved_config_path = (config_path or "").strip() or "tests/configs/suites/lmstudio_chat_v20260418.json"

        command = self._build_command(
            run_type=run_type,
            model=resolved_model,
            embedding=resolved_embedding,
            rounds=resolved_rounds,
            config_path=resolved_config_path,
        )

        run_id = str(uuid.uuid4())
        log_file = str((self._log_root / f"{run_id}.log").resolve())

        run: dict[str, Any] = {
            "run_id": run_id,
            "run_type": run_type,
            "status": "queued",
            "command": command,
            "created_at": _utc_now_iso(),
            "started_at": "",
            "finished_at": "",
            "exit_code": None,
            "log_file": log_file,
            "cancel_requested": False,
            "output_tail": [],
            "error": "",
            "_process": None,
        }

        with self._lock:
            self._runs[run_id] = run

        worker = threading.Thread(target=self._run_worker, args=(run_id,), daemon=True)
        worker.start()

        return self._public_record(run)

    def _run_worker(self, run_id: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            run["status"] = "running"
            run["started_at"] = _utc_now_iso()
            command = list(run["command"])
            log_file = str(run["log_file"])

        try:
            with open(log_file, "w", encoding="utf-8") as log:
                log.write(f"Command: {' '.join(command)}\n")
                log.write(f"Started: {run['started_at']}\n\n")

                process = subprocess.Popen(
                    command,
                    cwd=str(self._project_root),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )

                with self._lock:
                    tracked = self._runs.get(run_id)
                    if not tracked:
                        process.kill()
                        return
                    tracked["_process"] = process

                assert process.stdout is not None
                for line in process.stdout:
                    log.write(line)
                    log.flush()

                    clean_line = line.rstrip("\n")
                    with self._lock:
                        tracked = self._runs.get(run_id)
                        if not tracked:
                            continue
                        tail = tracked.setdefault("output_tail", [])
                        tail.append(clean_line)
                        if len(tail) > 200:
                            del tail[:-200]

                exit_code = process.wait()

                with self._lock:
                    tracked = self._runs.get(run_id)
                    if not tracked:
                        return
                    tracked["exit_code"] = int(exit_code)
                    tracked["finished_at"] = _utc_now_iso()
                    tracked["_process"] = None
                    if tracked.get("cancel_requested"):
                        tracked["status"] = "cancelled"
                    else:
                        tracked["status"] = "passed" if exit_code == 0 else "failed"

        except Exception as exc:
            with self._lock:
                tracked = self._runs.get(run_id)
                if not tracked:
                    return
                tracked["status"] = "error"
                tracked["error"] = str(exc)
                tracked["finished_at"] = _utc_now_iso()
                tracked["_process"] = None

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            runs = [self._public_record(run) for run in self._runs.values()]

        runs.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return runs

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return None
            return self._public_record(run)

    def list_artifacts(self, run_id: str) -> list[dict[str, Any]] | None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return None
            run_snapshot = {
                "log_file": str(run.get("log_file", "") or ""),
            }

        return self._resolve_artifacts(run_snapshot)

    def read_artifact(self, run_id: str, artifact_id: str, *, max_lines: int = 400) -> dict[str, Any] | None:
        artifacts = self.list_artifacts(run_id)
        if artifacts is None:
            return None

        target = next((item for item in artifacts if item.get("artifact_id") == artifact_id), None)
        if not target:
            return None

        artifact_path = Path(str(target.get("path", ""))).resolve()
        if not artifact_path.exists():
            return {
                "run_id": run_id,
                "artifact": target,
                "content": "",
                "truncated": False,
                "line_count": 0,
            }

        resolved_max_lines = max(1, min(int(max_lines), 2000))
        lines = artifact_path.read_text(encoding="utf-8", errors="replace").splitlines()
        truncated = len(lines) > resolved_max_lines
        if truncated:
            lines = lines[-resolved_max_lines:]

        return {
            "run_id": run_id,
            "artifact": target,
            "content": "\n".join(lines),
            "truncated": truncated,
            "line_count": len(lines),
        }

    def cancel_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return None

            run["cancel_requested"] = True
            process = run.get("_process")
            if process and run.get("status") == "running":
                process.terminate()

            return self._public_record(run)
