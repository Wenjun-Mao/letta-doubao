from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_platform_api.models.agents import AgentCreateRequest
from agent_platform_api.routers.agents import _router_llm_config_for_model
from agent_platform_api.settings import clear_settings_cache


def test_router_llm_config_includes_create_time_sampling(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_MODEL_ROUTER_BASE_URL", "http://model_router:8290")
    clear_settings_cache()

    config = _router_llm_config_for_model(
        "openai-proxy/local_llama_server::gemma4",
        temperature=0.7,
        top_p=0.85,
    )

    assert config is not None
    assert config["model"] == "local_llama_server::gemma4"
    assert config["temperature"] == 0.7
    assert config["top_p"] == 0.85


def test_router_llm_config_omits_unspecified_sampling(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_PLATFORM_MODEL_ROUTER_BASE_URL", "http://model_router:8290")
    clear_settings_cache()

    config = _router_llm_config_for_model("openai-proxy/local_llama_server::gemma4")

    assert config is not None
    assert "temperature" not in config
    assert "top_p" not in config


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("temperature", -0.1),
        ("temperature", 2.1),
        ("top_p", 0),
        ("top_p", 1.1),
    ],
)
def test_agent_create_request_rejects_invalid_sampling_ranges(field: str, value: float) -> None:
    kwargs = {
        "name": "agent",
        "model": "openai-proxy/local_llama_server::gemma4",
        field: value,
    }
    with pytest.raises(ValidationError):
        AgentCreateRequest(**kwargs)
