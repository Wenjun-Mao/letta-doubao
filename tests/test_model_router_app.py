from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import model_router.app as router_app
from model_router.catalog import RoutedModel, RouterCatalogSnapshot, RouterSourceSnapshot
from model_router.settings import RouterSourceConfig


class _FakeSettings:
    sources: list[RouterSourceConfig] = []

    def resolve_api_key(self) -> str:
        return "router-token"


class _FakeCatalog:
    def __init__(self) -> None:
        self.source = RouterSourceConfig(
            id="local_llama_server",
            label="Local llama-server",
            base_url="http://127.0.0.1:8081/v1",
            adapter="llama_cpp_server",
            enabled_for=["agent_studio", "comment_lab", "label_lab"],
        )
        self.model = RoutedModel(
            router_model_id="local_llama_server::gemma4",
            source_id="local_llama_server",
            source_label="Local llama-server",
            source_kind="openai-compatible",
            source_adapter="llama_cpp_server",
            source_base_url="http://127.0.0.1:8081/v1",
            module_visibility=("agent_studio", "comment_lab", "label_lab"),
            provider_model_id="gemma4",
            model_type="llm",
            letta_handle="openai-proxy/local_llama_server::gemma4",
            agent_studio_available=True,
            comment_lab_available=True,
            label_lab_available=True,
            structured_output_mode="json_schema",
        )

    def snapshot(self, *, force_refresh: bool = False) -> RouterCatalogSnapshot:
        return RouterCatalogSnapshot(
            generated_at=123.0,
            sources=(
                RouterSourceSnapshot(
                    id="local_llama_server",
                    label="Local llama-server",
                    kind="openai-compatible",
                    adapter="llama_cpp_server",
                    base_url="http://127.0.0.1:8081/v1",
                    module_visibility=("agent_studio", "comment_lab", "label_lab"),
                    status="healthy",
                    detail="ok",
                    models=(),
                    raw_model_count=1,
                    filtered_model_count=1,
                ),
            ),
        )

    def flatten(self, snapshot: RouterCatalogSnapshot) -> list[RoutedModel]:
        return [self.model]

    def find_routed_model(self, router_model_id: str, *, force_refresh: bool = False) -> RoutedModel | None:
        if router_model_id.endswith("local_llama_server::gemma4"):
            return self.model
        return None

    def source_config(self, source_id: str) -> RouterSourceConfig | None:
        return self.source if source_id == "local_llama_server" else None

    def source_status(self, source_id: str) -> SimpleNamespace:
        return SimpleNamespace(status="healthy", detail="ok")


def test_router_requires_api_key(monkeypatch) -> None:
    monkeypatch.setattr(router_app, "get_settings", lambda: _FakeSettings())
    client = TestClient(router_app.app)

    response = client.get("/v1/models")

    assert response.status_code == 401


def test_router_lists_agent_studio_models(monkeypatch) -> None:
    monkeypatch.setattr(router_app, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(router_app, "catalog_service", _FakeCatalog())
    client = TestClient(router_app.app)

    response = client.get("/v1/models", headers={"Authorization": "Bearer router-token"})

    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == "local_llama_server::gemma4"


def test_router_rewrites_model_and_preserves_payload(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(source: RouterSourceConfig, payload: dict[str, Any]):
        captured["source_id"] = source.id
        captured["payload"] = payload
        return JSONResponse({"ok": True, "model": payload["model"]})

    monkeypatch.setattr(router_app, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(router_app, "catalog_service", _FakeCatalog())
    monkeypatch.setattr(router_app, "_post_chat_completion", fake_post)
    client = TestClient(router_app.app)

    payload = {
        "model": "openai-proxy/local_llama_server::gemma4",
        "messages": [{"role": "user", "content": "hi"}],
        "tools": [{"type": "function", "function": {"name": "ping"}}],
        "tool_choice": "auto",
        "response_format": {"type": "json_object"},
        "stream": False,
        "reasoning": {"effort": "low"},
    }
    response = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"Authorization": "Bearer router-token"},
    )

    assert response.status_code == 200
    assert captured["source_id"] == "local_llama_server"
    assert captured["payload"]["model"] == "gemma4"
    assert captured["payload"]["tools"] == payload["tools"]
    assert captured["payload"]["tool_choice"] == "auto"
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert captured["payload"]["reasoning"] == {"effort": "low"}


def test_router_unknown_model_reports_source_status(monkeypatch) -> None:
    monkeypatch.setattr(router_app, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(router_app, "catalog_service", _FakeCatalog())
    client = TestClient(router_app.app)

    response = client.post(
        "/v1/chat/completions",
        json={"model": "local_llama_server::missing", "messages": []},
        headers={"Authorization": "Bearer router-token"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_or_unavailable_model"
    assert response.json()["error"]["source_status"] == "healthy"

