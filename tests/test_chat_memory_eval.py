from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.chat_memory_eval.artifacts import ArtifactWriter, build_summary
from evals.chat_memory_eval.config import apply_cli_overrides, load_config, router_model_key_from_agent_handle
from evals.chat_memory_eval.fixtures import ExpectedFact, load_fixture
from evals.chat_memory_eval.judge import _parse_json_object
from evals.chat_memory_eval.scoring import deterministic_round_score, score_expected_facts


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_chat_memory_config_loads_defaults_and_cli_overrides(tmp_path) -> None:
    config = load_config(PROJECT_ROOT / "evals" / "chat_memory_eval" / "config.toml")
    args = argparse.Namespace(
        api_base_url="",
        output_dir=str(tmp_path),
        model="openai-proxy/test::model",
        prompt_key="",
        persona_key="",
        embedding="",
        fixture_key="",
        judge_model_key="",
        rounds=1,
        timeout_seconds=60,
        retry_count=0,
        judge_enabled=False,
        keep_agents=False,
    )

    updated = apply_cli_overrides(config, args)

    assert config.prompt_key == "chat_v20260516"
    assert updated.output_dir == tmp_path
    assert updated.model == "openai-proxy/test::model"
    assert updated.rounds == 1
    assert updated.judge_enabled is False


def test_chat_memory_fixture_loads_restored_conversation() -> None:
    fixture = load_fixture(
        PROJECT_ROOT / "evals" / "chat_memory_eval" / "fixtures",
        "recent_user_chat_turns",
    )

    assert fixture.key == "recent_user_chat_turns"
    assert fixture.turns[0] == "你好，我叫张伟"
    assert [item.key for item in fixture.expected_facts] == ["user_name", "dog_name", "dog_breed"]


def test_expected_fact_alias_matching_is_case_insensitive() -> None:
    scores = score_expected_facts(
        "姓名：张伟\n宠物：rocky 是一只 Husky",
        (
            ExpectedFact(key="name", label="Name", aliases=("张伟",)),
            ExpectedFact(key="dog", label="Dog", aliases=("Rocky",)),
            ExpectedFact(key="breed", label="Breed", aliases=("哈士奇", "husky")),
        ),
    )

    assert [score.passed for score in scores] == [True, True, True]


def test_deterministic_round_score_requires_memory_facts_and_no_forbidden_hits() -> None:
    score = deterministic_round_score(
        assistant_texts=["我是机器人，但是可以陪你聊天"],
        initial_human_memory="",
        final_human_memory="姓名：张伟\n宠物：Rocky",
        expected_facts=(
            ExpectedFact(key="name", label="Name", aliases=("张伟",)),
            ExpectedFact(key="breed", label="Breed", aliases=("哈士奇",)),
        ),
        forbidden_reply_substrings=("我是机器人",),
    )

    assert score["pass"] is False
    assert score["forbidden_hit_count"] == 1
    assert score["missing_expected_facts"] == ["breed"]


def test_router_model_key_derives_from_agent_studio_handle() -> None:
    assert (
        router_model_key_from_agent_handle("openai-proxy/dgx_vllm::qwen3.6-35b-a3b-fp8")
        == "dgx_vllm::qwen3.6-35b-a3b-fp8"
    )


def test_judge_json_parser_recovers_object_from_text() -> None:
    assert _parse_json_object('notes\n{"pass": true, "score": 88}\nend') == {"pass": True, "score": 88}


def test_chat_memory_artifact_writer_streams_csv_and_jsonl(tmp_path) -> None:
    csv_path = tmp_path / "run.csv"
    jsonl_path = tmp_path / "run.jsonl"
    row = {
        "run_id": "run-1",
        "round": 1,
        "status": "ok",
        "pass": True,
        "elapsed_seconds": 1.23,
    }

    with ArtifactWriter(csv_path=csv_path, jsonl_path=jsonl_path) as writer:
        writer.write_round(row, {"raw": row})

    assert "run_id" in csv_path.read_text(encoding="utf-8-sig")
    assert json.loads(jsonl_path.read_text(encoding="utf-8"))["raw"]["run_id"] == "run-1"
    summary = build_summary(run_id="run-1", csv_path=csv_path, jsonl_path=jsonl_path, summary_path=tmp_path / "s.json", rows=[row])
    assert summary["rounds_passed"] == 1
