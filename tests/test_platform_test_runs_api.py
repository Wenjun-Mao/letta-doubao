from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from agent_platform_api.models.platform import PlatformTestRunRequest
from agent_platform_api.routers import platform_runtime


def test_platform_test_run_request_accepts_only_kept_run_types() -> None:
    assert PlatformTestRunRequest(run_type="platform_api_e2e_check").run_type == "platform_api_e2e_check"
    assert PlatformTestRunRequest(run_type="ade_mvp_smoke_e2e_check").run_type == "ade_mvp_smoke_e2e_check"
    assert PlatformTestRunRequest(run_type="chat_memory_eval").run_type == "chat_memory_eval"

    with pytest.raises(ValidationError):
        PlatformTestRunRequest(run_type="agent_bootstrap_check")


def test_platform_test_run_request_rejects_removed_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PlatformTestRunRequest(
            run_type="platform_api_e2e_check",
            model="lmstudio_openai/gemma-4-31b-it",
            embedding="letta/letta-free",
            rounds=5,
            config_path="legacy-config.json",
        )


def test_platform_create_test_run_passes_only_run_type(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeOrchestrator:
        def create_run(self, *, run_type: str):
            captured["run_type"] = run_type
            return {
                "run_id": "run-1",
                "run_type": run_type,
                "status": "queued",
                "command": ["python", "tests/checks/platform_api_e2e_check.py"],
                "created_at": "2026-04-22T00:00:00+00:00",
                "started_at": "",
                "finished_at": "",
                "exit_code": None,
                "log_file": "tests/outputs/platform_orchestrator/run-1.log",
                "cancel_requested": False,
                "output_tail": [],
                "error": "",
                "artifacts": [],
            }

    monkeypatch.setattr(platform_runtime, "ensure_platform_api_enabled", lambda: None)
    monkeypatch.setattr(platform_runtime, "test_orchestrator", _FakeOrchestrator())

    payload = asyncio.run(
        platform_runtime.api_platform_create_test_run(
            PlatformTestRunRequest(run_type="platform_api_e2e_check")
        )
    )

    assert captured["run_type"] == "platform_api_e2e_check"
    assert payload["run_type"] == "platform_api_e2e_check"


def test_platform_chat_memory_eval_request_accepts_focused_fields() -> None:
    request = PlatformTestRunRequest(
        run_type="chat_memory_eval",
        model="openai-proxy/dgx_vllm::qwen3.6-35b-a3b-fp8",
        prompt_key="chat_v20260516",
        persona_key="chat_linxiaotang",
        embedding="letta/letta-free",
        rounds=1,
        fixture_key="recent_user_chat_turns",
        timeout_seconds=180,
        retry_count=0,
        judge_enabled=False,
    )

    assert request.rounds == 1
    assert request.judge_enabled is False


def test_platform_chat_memory_eval_create_passes_options(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeOrchestrator:
        def create_run(self, **kwargs):
            captured.update(kwargs)
            return {
                "run_id": "run-2",
                "run_type": kwargs["run_type"],
                "status": "queued",
                "command": ["python", "evals/chat_memory_eval/run.py"],
                "created_at": "2026-04-22T00:00:00+00:00",
                "started_at": "",
                "finished_at": "",
                "exit_code": None,
                "log_file": "tests/outputs/platform_orchestrator/run-2/orchestrator.log",
                "cancel_requested": False,
                "output_tail": [],
                "error": "",
                "artifacts": [],
            }

    monkeypatch.setattr(platform_runtime, "ensure_platform_api_enabled", lambda: None)
    monkeypatch.setattr(platform_runtime, "test_orchestrator", _FakeOrchestrator())

    payload = asyncio.run(
        platform_runtime.api_platform_create_test_run(
            PlatformTestRunRequest(
                run_type="chat_memory_eval",
                model="openai-proxy/test::model",
                rounds=1,
                judge_enabled=False,
            )
        )
    )

    assert captured["run_type"] == "chat_memory_eval"
    assert captured["model"] == "openai-proxy/test::model"
    assert captured["rounds"] == 1
    assert captured["judge_enabled"] is False
    assert payload["run_type"] == "chat_memory_eval"


def test_platform_orchestrator_discovers_run_output_artifacts(tmp_path) -> None:
    from agent_platform_api.testing.orchestrator import PlatformTestOrchestrator

    orchestrator = PlatformTestOrchestrator(project_root=tmp_path)
    output_dir = tmp_path / "tests" / "outputs" / "platform_orchestrator" / "run-3"
    output_dir.mkdir(parents=True)
    log_file = output_dir / "orchestrator.log"
    csv_file = output_dir / "chat_memory_eval_20260516.csv"
    log_file.write_text("log", encoding="utf-8")
    csv_file.write_text("csv", encoding="utf-8")

    artifacts = orchestrator._resolve_artifacts(
        {
            "log_file": str(log_file),
            "output_dir": str(output_dir),
        }
    )

    assert [item["artifact_id"] for item in artifacts] == [
        "orchestrator_log",
        "chat_memory_eval_20260516.csv",
    ]
