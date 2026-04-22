from __future__ import annotations

import json

from agent_platform_api.settings import ModelSourceConfig, clear_settings_cache, get_settings


def test_settings_parse_model_sources_from_env(monkeypatch) -> None:
    monkeypatch.setenv(
        "AGENT_PLATFORM_MODEL_SOURCES",
        json.dumps(
            [
                {
                    "id": "local",
                    "label": "Local Unsloth",
                    "base_url": "http://127.0.0.1:1234/v1",
                    "kind": "openai-compatible",
                    "enabled_for": ["chat", "comment"],
                    "letta_handle_prefix": "lmstudio_openai",
                    "api_key_env": "UNSLOTH_API_KEY",
                    "api_key_secret": "unsloth-api-key",
                },
                {
                    "id": "ark",
                    "label": "Volcengine Ark",
                    "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                    "kind": "openai-compatible",
                    "enabled_for": ["comment"],
                    "letta_handle_prefix": "openai-proxy",
                    "api_key_env": "OPENAI_API_KEY",
                    "api_key_secret": "ark-api-key",
                },
            ]
        ),
    )
    clear_settings_cache()
    try:
        settings = get_settings()
        assert [source.id for source in settings.model_sources] == ["local", "ark"]
        assert settings.model_sources[0].enabled_for == ["chat", "comment"]
        assert settings.model_sources[1].letta_handle_prefix == "openai-proxy"
    finally:
        clear_settings_cache()


def test_model_source_resolve_api_key_prefers_secret_file_over_env(tmp_path) -> None:
    source = ModelSourceConfig(
        id="local",
        label="Local",
        base_url="http://127.0.0.1:1234/v1",
        kind="openai-compatible",
        enabled_for=["comment"],
        letta_handle_prefix="lmstudio_openai",
        api_key_env="UNSLOTH_API_KEY",
        api_key_secret="unsloth-api-key",
    )
    (tmp_path / "unsloth-api-key").write_text("secret-token\n", encoding="utf-8")

    assert (
        source.resolve_api_key(
            secrets_dir=tmp_path,
            environ={"UNSLOTH_API_KEY": "env-token"},
        )
        == "secret-token"
    )

    (tmp_path / "unsloth-api-key").unlink()
    assert (
        source.resolve_api_key(
            secrets_dir=tmp_path,
            environ={"UNSLOTH_API_KEY": "env-token"},
        )
        == "env-token"
    )


def test_model_source_resolve_api_key_uses_process_env_when_environ_is_omitted(
    monkeypatch,
    tmp_path,
) -> None:
    source = ModelSourceConfig(
        id="local",
        label="Local",
        base_url="http://127.0.0.1:1234/v1",
        kind="openai-compatible",
        enabled_for=["comment"],
        letta_handle_prefix="lmstudio_openai",
        api_key_env="UNSLOTH_API_KEY",
        api_key_secret="unsloth-api-key",
    )
    monkeypatch.setenv("UNSLOTH_API_KEY", "env-token")

    assert source.resolve_api_key(secrets_dir=tmp_path) == "env-token"


def test_model_source_versioned_base_urls_cover_v1_and_v3() -> None:
    v1_source = ModelSourceConfig(
        id="local",
        label="Local",
        base_url="http://127.0.0.1:1234/v1/",
        kind="openai-compatible",
        enabled_for=["chat"],
        letta_handle_prefix="lmstudio_openai",
    )
    v3_source = ModelSourceConfig(
        id="ark",
        label="Ark",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        kind="openai-compatible",
        enabled_for=["comment"],
        letta_handle_prefix="openai-proxy",
    )

    assert v1_source.models_endpoint() == "http://127.0.0.1:1234/v1/models"
    assert v1_source.chat_completions_url() == "http://127.0.0.1:1234/v1/chat/completions"
    assert v3_source.models_endpoint() == "https://ark.cn-beijing.volces.com/api/v3/models"
    assert v3_source.chat_completions_url() == "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
