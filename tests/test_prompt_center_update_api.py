from __future__ import annotations

from fastapi.testclient import TestClient

import agent_platform_api.app as app_module
from agent_platform_api.app import create_app
from agent_platform_api.registries.prompt_persona import PromptPersonaRegistry
from agent_platform_api.routers import prompt_center


def _client(monkeypatch, registry: PromptPersonaRegistry) -> TestClient:
    monkeypatch.setattr(app_module, "validate_platform_capabilities_startup", lambda: None)
    monkeypatch.setattr(prompt_center, "ensure_platform_api_enabled", lambda: None)
    monkeypatch.setattr(prompt_center, "prompt_persona_registry", registry)
    monkeypatch.setattr(prompt_center, "invalidate_options_cache", lambda: None)
    return TestClient(create_app())


def test_update_persona_template_content_only_with_scenario(monkeypatch, tmp_path) -> None:
    registry = PromptPersonaRegistry(tmp_path)
    registry.create_template(
        "persona",
        key="chat_patch_persona",
        content="1",
        label="Persona One",
        description="Initial persona",
    )

    with _client(monkeypatch, registry) as client:
        response = client.patch(
            "/api/v1/platform/prompt-center/personas/chat_patch_persona?scenario=chat",
            json={"content": "2"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["key"] == "chat_patch_persona"
    assert payload["scenario"] == "chat"
    assert payload["content"] == "2"
    assert payload["label"] == "Persona One"
    assert payload["description"] == "Initial persona"


def test_update_prompt_template_content_only_with_scenario(monkeypatch, tmp_path) -> None:
    registry = PromptPersonaRegistry(tmp_path)
    registry.create_template(
        "prompt",
        key="chat_patch_prompt",
        content="1",
        label="Prompt One",
        description="Initial prompt",
    )

    with _client(monkeypatch, registry) as client:
        response = client.patch(
            "/api/v1/platform/prompt-center/prompts/chat_patch_prompt?scenario=chat",
            json={"content": "2"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["key"] == "chat_patch_prompt"
    assert payload["scenario"] == "chat"
    assert payload["content"] == "2"
    assert payload["label"] == "Prompt One"
    assert payload["description"] == "Initial prompt"


def test_update_label_persona_returns_clean_400(monkeypatch, tmp_path) -> None:
    registry = PromptPersonaRegistry(tmp_path)

    with _client(monkeypatch, registry) as client:
        response = client.patch(
            "/api/v1/platform/prompt-center/personas/label_patch_persona?scenario=label",
            json={"content": "2"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Label scenario does not support persona templates"


def test_update_prompt_template_requires_at_least_one_field(monkeypatch, tmp_path) -> None:
    registry = PromptPersonaRegistry(tmp_path)
    registry.create_template("prompt", key="chat_patch_empty", content="1")

    with _client(monkeypatch, registry) as client:
        response = client.patch(
            "/api/v1/platform/prompt-center/prompts/chat_patch_empty?scenario=chat",
            json={},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "At least one field must be provided"
