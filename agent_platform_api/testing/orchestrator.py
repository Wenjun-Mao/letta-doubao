from __future__ import annotations

import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        output_dir: Path,
        options: dict[str, Any],
    ) -> list[str]:
        python = sys.executable

        if run_type == "platform_api_e2e_check":
            return [python, "tests/checks/platform_api_e2e_check.py"]
        if run_type == "ade_mvp_smoke_e2e_check":
            return [python, "tests/checks/ade_mvp_smoke_e2e_check.py"]
        if run_type == "chat_memory_eval":
            command = [
                python,
                "evals/chat_memory_eval/run.py",
                "--config",
                "evals/chat_memory_eval/config.toml",
                "--output-dir",
                str(output_dir),
            ]
            _append_option(command, "--model", options.get("model"))
            _append_option(command, "--prompt-key", options.get("prompt_key"))
            _append_option(command, "--persona-key", options.get("persona_key"))
            _append_option(command, "--embedding", options.get("embedding"))
            _append_option(command, "--fixture-key", options.get("fixture_key"))
            _append_option(command, "--judge-model-key", options.get("judge_model_key"))
            _append_option(command, "--rounds", options.get("rounds"))
            _append_option(command, "--timeout-seconds", options.get("timeout_seconds"))
            _append_option(command, "--retry-count", options.get("retry_count"))
            if options.get("judge_enabled") is True:
                command.append("--judge-enabled")
            if options.get("judge_enabled") is False:
                command.append("--no-judge-enabled")
            return command

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

        output_dir = str(run.get("output_dir", "") or "")
        if output_dir:
            output_path = Path(output_dir).resolve()
            if output_path.is_dir():
                for path in sorted(item for item in output_path.rglob("*") if item.is_file()):
                    if log_file and path.resolve() == Path(log_file).resolve():
                        continue
                    relative = path.relative_to(output_path).as_posix()
                    artifact_id = relative.replace("/", "__")
                    artifacts.append(
                        {
                            "artifact_id": artifact_id,
                            "type": path.suffix.lower().lstrip(".") or "artifact",
                            "path": str(path.resolve()),
                            "exists": True,
                            "size_bytes": path.stat().st_size,
                        }
                    )

        return artifacts

    def create_run(
        self,
        *,
        run_type: str,
        **options: Any,
    ) -> dict[str, Any]:
        run_id = str(uuid.uuid4())
        output_dir = (self._log_root / run_id).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        command = self._build_command(
            run_type=run_type,
            output_dir=output_dir,
            options=options,
        )

        log_file = str((output_dir / "orchestrator.log").resolve())

        run: dict[str, Any] = {
            "run_id": run_id,
            "run_type": run_type,
            "status": "queued",
            "command": command,
            "output_dir": str(output_dir),
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
                "output_dir": str(run.get("output_dir", "") or ""),
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


def _append_option(command: list[str], flag: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str) and not value.strip():
        return
    command.extend([flag, str(value)])
