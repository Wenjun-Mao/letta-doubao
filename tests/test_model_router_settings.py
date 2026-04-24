from __future__ import annotations

import json

from model_router.settings import RouterSourceConfig, clear_settings_cache, get_settings


def test_router_settings_parse_sources_and_module_visibility(monkeypatch) -> None:
    monkeypatch.setenv(
        "MODEL_ROUTER_SOURCES",
        json.dumps(
            [
                {
                    "id": "local_llama_server",
                    "label": "Local llama-server",
                    "base_url": "http://127.0.0.1:8081/v1",
                    "kind": "openai-compatible",
                    "adapter": "llama_cpp_server",
                    "enabled": True,
                    "enabled_for": ["agent_studio", "comment_lab", "label_lab"],
                    "api_key_env": "LLAMA_SERVER_API_KEY",
                    "api_key_secret": "llama-server-api-key",
                },
                {
                    "id": "ark",
                    "label": "Ark",
                    "base_url": "https://ark.example/api/v3",
                    "kind": "openai-compatible",
                    "adapter": "ark_openai",
                    "enabled_for": ["chat", "comment"],
                    "module_visibility": ["agent_studio", "comment_lab"],
                    "api_key_env": "OPENAI_API_KEY",
                    "api_key_secret": "ark-api-key",
                },
            ]
        ),
    )
    clear_settings_cache()
    try:
        settings = get_settings()
        assert [source.id for source in settings.sources] == ["local_llama_server", "ark"]
        assert settings.sources[0].visible_modules() == ("agent_studio", "comment_lab", "label_lab")
        assert settings.sources[1].visible_modules() == ("agent_studio", "comment_lab")
        assert settings.sources[1].models_endpoint() == "https://ark.example/api/v3/models"
    finally:
        clear_settings_cache()


def test_router_source_auth_prefers_secret_file_over_env(tmp_path) -> None:
    source = RouterSourceConfig(
        id="local",
        label="Local",
        base_url="http://127.0.0.1:8081/v1",
        enabled_for=["label_lab"],
        api_key_env="LLAMA_SERVER_API_KEY",
        api_key_secret="llama-server-api-key",
    )
    (tmp_path / "llama-server-api-key").write_text("secret-token\n", encoding="utf-8")

    assert (
        source.resolve_api_key(
            secrets_dir=tmp_path,
            environ={"LLAMA_SERVER_API_KEY": "env-token"},
        )
        == "secret-token"
    )

    (tmp_path / "llama-server-api-key").unlink()
    assert (
        source.resolve_api_key(
            secrets_dir=tmp_path,
            environ={"LLAMA_SERVER_API_KEY": "env-token"},
        )
        == "env-token"
    )


def test_llama_router_source_falls_back_to_unsloth_key(tmp_path) -> None:
    source = RouterSourceConfig(
        id="local_llama_server",
        label="Local llama-server",
        base_url="http://127.0.0.1:8081/v1",
        adapter="llama_cpp_server",
        enabled_for=["label_lab"],
        api_key_env="LLAMA_SERVER_API_KEY",
        api_key_secret="llama-server-api-key",
    )

    assert (
        source.resolve_api_key(
            secrets_dir=tmp_path,
            environ={"LLAMA_SERVER_API_KEY": "", "UNSLOTH_API_KEY": "fallback-token"},
        )
        == "fallback-token"
    )

