from __future__ import annotations

import json

import pytest

from model_router.profiles import load_model_profiles


def _profile_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "base_model": "nvidia/Gemma-4-31B-IT-NVFP4",
        "profile_source": "https://huggingface.co/google/gemma-4-31B-it",
        "supports_top_k": True,
        "supports_thinking": True,
        "thinking_default_enabled": False,
        "agent_studio_candidate": True,
        "agent_studio_compatible": False,
        "sampling_defaults": {"temperature": 1.0, "top_p": 0.95, "top_k": 64},
        "scenario_sampling_defaults": {
            "chat": {"temperature": 1.0, "top_p": 0.95, "top_k": 64},
            "comment": {"temperature": 1.0, "top_p": 0.95, "top_k": 64},
            "label": {"temperature": 0.0, "top_p": 0.95, "top_k": 64},
        },
    }
    payload.update(overrides)
    return payload


def test_load_model_profiles_resolves_sampling_defaults(tmp_path) -> None:
    profiles_path = tmp_path / "model_profiles.json"
    profiles_path.write_text(
        json.dumps({"dgx_vllm::gemma4-31b-nvfp4": _profile_payload()}),
        encoding="utf-8",
    )

    profiles = load_model_profiles(profiles_path)

    profile = profiles["dgx_vllm::gemma4-31b-nvfp4"]
    assert profile.sampling_defaults.as_payload() == {
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 64,
    }
    assert profile.effective_defaults_for("label_lab").as_payload() == {
        "temperature": 0.0,
        "top_p": 0.95,
        "top_k": 64,
    }
    assert profile.scenario_defaults_payload()["agent_studio"]["top_k"] == 64
    assert profile.supports_thinking is True
    assert profile.thinking_default_enabled is False
    assert profile.agent_studio_compatible is False


def test_load_model_profiles_accepts_qwen_vllm_sampling_defaults(tmp_path) -> None:
    profiles_path = tmp_path / "model_profiles.json"
    profiles_path.write_text(
        json.dumps(
            {
                "dgx_vllm::qwen3.6-35b-a3b-fp8": {
                    "base_model": "Qwen/Qwen3.6-35B-A3B-FP8",
                    "profile_source": "temps/new_LLM/llm/settings.py",
                    "supports_top_k": True,
                    "supports_thinking": True,
                    "thinking_default_enabled": True,
                    "agent_studio_candidate": True,
                    "agent_studio_compatible": True,
                    "sampling_defaults": {
                        "temperature": 1.0,
                        "top_p": 0.95,
                        "top_k": 20,
                        "min_p": 0.0,
                        "presence_penalty": 1.5,
                        "repetition_penalty": 1.0,
                    },
                    "scenario_sampling_defaults": {
                        "chat": {"top_k": 20, "min_p": 0.0},
                        "comment": {"presence_penalty": 1.5},
                        "label": {"repetition_penalty": 1.0},
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    profiles = load_model_profiles(profiles_path)

    profile = profiles["dgx_vllm::qwen3.6-35b-a3b-fp8"]
    assert profile.sampling_defaults.as_payload() == {
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 20,
        "min_p": 0.0,
        "presence_penalty": 1.5,
        "repetition_penalty": 1.0,
    }
    assert profile.effective_defaults_for("agent_studio").as_payload()["min_p"] == 0.0
    assert profile.effective_defaults_for("comment_lab").as_payload()["presence_penalty"] == 1.5
    assert profile.effective_defaults_for("label_lab").as_payload()["repetition_penalty"] == 1.0
    assert profile.thinking_default_enabled is True
    assert profile.agent_studio_compatible is True


def test_load_model_profiles_rejects_duplicate_profile_keys(tmp_path) -> None:
    profiles_path = tmp_path / "model_profiles.json"
    profiles_path.write_text(
        """
        {
          "dgx_vllm::gemma4-31b-nvfp4": {"sampling_defaults": {"temperature": 1.0}},
          "dgx_vllm::gemma4-31b-nvfp4": {"sampling_defaults": {"temperature": 0.5}}
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate JSON key"):
        load_model_profiles(profiles_path)


def test_load_model_profiles_rejects_invalid_sampling_ranges(tmp_path) -> None:
    profiles_path = tmp_path / "model_profiles.json"
    profiles_path.write_text(
        json.dumps(
            {
                "dgx_vllm::gemma4-31b-nvfp4": _profile_payload(
                    sampling_defaults={"temperature": 3.0, "top_p": 0.95, "top_k": 64},
                )
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="temperature"):
        load_model_profiles(profiles_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("min_p", -0.1),
        ("min_p", 1.1),
        ("presence_penalty", -2.1),
        ("presence_penalty", 2.1),
        ("repetition_penalty", 0),
    ],
)
def test_load_model_profiles_rejects_invalid_vllm_sampling_ranges(
    tmp_path,
    field: str,
    value: float | int,
) -> None:
    profiles_path = tmp_path / "model_profiles.json"
    profiles_path.write_text(
        json.dumps(
            {
                "dgx_vllm::qwen3.6-35b-a3b-fp8": _profile_payload(
                    sampling_defaults={
                        "temperature": 1.0,
                        "top_p": 0.95,
                        "top_k": 20,
                        field: value,
                    },
                )
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(Exception, match=field):
        load_model_profiles(profiles_path)
