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
    def __init__(
        self,
        *,
        source: RouterSourceConfig | None = None,
        model: RoutedModel | None = None,
    ) -> None:
        self.source = source or RouterSourceConfig(
            id="local_llama_server",
            label="Local llama-server",
            base_url="http://127.0.0.1:8081/v1",
            adapter="llama_cpp_server",
            enabled_for=["agent_studio", "comment_lab", "label_lab"],
        )
        self.model = model or RoutedModel(
            router_model_id="local_llama_server::gemma4",
            source_id=self.source.id,
            source_label=self.source.label,
            source_kind="openai-compatible",
            source_adapter=self.source.adapter,
            source_base_url=self.source.base_url,
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
                    id=self.source.id,
                    label=self.source.label,
                    kind="openai-compatible",
                    adapter=self.source.adapter,
                    base_url=self.source.base_url,
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
        if router_model_id.endswith(self.model.router_model_id):
            return self.model
        return None

    def source_config(self, source_id: str) -> RouterSourceConfig | None:
        return self.source if source_id == self.source.id else None

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


def test_router_injects_profile_sampling_defaults_for_vllm_when_omitted(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    source = RouterSourceConfig(
        id="dgx_vllm",
        label="DGX Spark vLLM",
        base_url="http://100.64.35.71:8000/v1",
        adapter="vllm_openai",
        enabled_for=["comment_lab", "label_lab"],
    )
    model = RoutedModel(
        router_model_id="dgx_vllm::gemma4-31b-nvfp4",
        source_id="dgx_vllm",
        source_label="DGX Spark vLLM",
        source_kind="openai-compatible",
        source_adapter="vllm_openai",
        source_base_url="http://100.64.35.71:8000/v1",
        module_visibility=("comment_lab", "label_lab"),
        provider_model_id="gemma4-31b-nvfp4",
        model_type="llm",
        letta_handle=None,
        agent_studio_available=False,
        comment_lab_available=True,
        label_lab_available=True,
        structured_output_mode="json_schema",
        sampling_defaults={"temperature": 1.0, "top_p": 0.95, "top_k": 64},
        supports_top_k=True,
        profile_applied=True,
    )

    def fake_post(_source: RouterSourceConfig, payload: dict[str, Any]):
        captured["payload"] = payload
        return JSONResponse({"ok": True, "model": payload["model"]})

    monkeypatch.setattr(router_app, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(router_app, "catalog_service", _FakeCatalog(source=source, model=model))
    monkeypatch.setattr(router_app, "_post_chat_completion", fake_post)
    client = TestClient(router_app.app)

    response = client.post(
        "/v1/chat/completions",
        json={"model": "dgx_vllm::gemma4-31b-nvfp4", "messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": "Bearer router-token"},
    )

    assert response.status_code == 200
    assert captured["payload"]["model"] == "gemma4-31b-nvfp4"
    assert captured["payload"]["temperature"] == 1.0
    assert captured["payload"]["top_p"] == 0.95
    assert captured["payload"]["top_k"] == 64


def test_router_preserves_explicit_sampling_values(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    source = RouterSourceConfig(
        id="dgx_vllm",
        label="DGX Spark vLLM",
        base_url="http://100.64.35.71:8000/v1",
        adapter="vllm_openai",
        enabled_for=["comment_lab", "label_lab"],
    )
    model = RoutedModel(
        router_model_id="dgx_vllm::gemma4-31b-nvfp4",
        source_id="dgx_vllm",
        source_label="DGX Spark vLLM",
        source_kind="openai-compatible",
        source_adapter="vllm_openai",
        source_base_url="http://100.64.35.71:8000/v1",
        module_visibility=("comment_lab", "label_lab"),
        provider_model_id="gemma4-31b-nvfp4",
        model_type="llm",
        letta_handle=None,
        agent_studio_available=False,
        comment_lab_available=True,
        label_lab_available=True,
        structured_output_mode="json_schema",
        sampling_defaults={"temperature": 1.0, "top_p": 0.95, "top_k": 64},
        supports_top_k=True,
    )

    def fake_post(_source: RouterSourceConfig, payload: dict[str, Any]):
        captured["payload"] = payload
        return JSONResponse({"ok": True, "model": payload["model"]})

    monkeypatch.setattr(router_app, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(router_app, "catalog_service", _FakeCatalog(source=source, model=model))
    monkeypatch.setattr(router_app, "_post_chat_completion", fake_post)
    client = TestClient(router_app.app)

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "dgx_vllm::gemma4-31b-nvfp4",
            "messages": [{"role": "user", "content": "hi"}],
            "temperature": 0.4,
            "top_p": 0.8,
            "top_k": 16,
        },
        headers={"Authorization": "Bearer router-token"},
    )

    assert response.status_code == 200
    assert captured["payload"]["temperature"] == 0.4
    assert captured["payload"]["top_p"] == 0.8
    assert captured["payload"]["top_k"] == 16


def test_router_drops_non_positive_max_tokens_before_forwarding(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(source: RouterSourceConfig, payload: dict[str, Any]):
        captured["source_id"] = source.id
        captured["payload"] = payload
        return JSONResponse({"ok": True, "model": payload["model"]})

    monkeypatch.setattr(router_app, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(router_app, "catalog_service", _FakeCatalog())
    monkeypatch.setattr(router_app, "_post_chat_completion", fake_post)
    client = TestClient(router_app.app)

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "local_llama_server::gemma4",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 0,
        },
        headers={"Authorization": "Bearer router-token"},
    )

    assert response.status_code == 200
    assert "max_tokens" not in captured["payload"]


def test_router_does_not_inject_top_k_for_generic_sources(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    source = RouterSourceConfig(
        id="generic",
        label="Generic",
        base_url="https://generic.example/v1",
        adapter="generic_openai",
        enabled_for=["comment_lab"],
    )
    model = RoutedModel(
        router_model_id="generic::model-a",
        source_id="generic",
        source_label="Generic",
        source_kind="openai-compatible",
        source_adapter="generic_openai",
        source_base_url="https://generic.example/v1",
        module_visibility=("comment_lab",),
        provider_model_id="model-a",
        model_type="llm",
        letta_handle=None,
        agent_studio_available=False,
        comment_lab_available=True,
        label_lab_available=False,
        structured_output_mode=None,
        sampling_defaults={"temperature": 0.7, "top_p": 0.9, "top_k": 64},
        supports_top_k=False,
    )

    def fake_post(_source: RouterSourceConfig, payload: dict[str, Any]):
        captured["payload"] = payload
        return JSONResponse({"ok": True, "model": payload["model"]})

    monkeypatch.setattr(router_app, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(router_app, "catalog_service", _FakeCatalog(source=source, model=model))
    monkeypatch.setattr(router_app, "_post_chat_completion", fake_post)
    client = TestClient(router_app.app)

    response = client.post(
        "/v1/chat/completions",
        json={"model": "generic::model-a", "messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": "Bearer router-token"},
    )

    assert response.status_code == 200
    assert captured["payload"]["temperature"] == 0.7
    assert captured["payload"]["top_p"] == 0.9
    assert "top_k" not in captured["payload"]


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
