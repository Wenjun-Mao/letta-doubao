from __future__ import annotations

import json

import pytest

from model_router.profiles import load_model_profiles


def _profile_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "base_model": "nvidia/Gemma-4-31B-IT-NVFP4",
        "profile_source": "https://huggingface.co/google/gemma-4-31B-it",
        "supports_top_k": True,
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
    assert profile.agent_studio_compatible is False


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

