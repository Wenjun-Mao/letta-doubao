from __future__ import annotations

import agent_platform_api.runtime as runtime
import agent_platform_api.model_options as model_options


class _FakeRouterClient:
    def enabled(self) -> bool:
        return True

    def invalidate(self) -> None:
        pass

    def v1_base_url(self) -> str:
        return "http://model-router.local/v1"

    def api_key(self) -> str:
        return "router-token"

    def catalog(self, *, force_refresh: bool = False) -> dict[str, object]:
        return {
            "generated_at": 123.0,
            "sources": [
                {
                    "id": "local_llama_server",
                    "label": "Local llama-server",
                    "kind": "openai-compatible",
                    "adapter": "llama_cpp_server",
                    "base_url": "http://127.0.0.1:8081/v1",
                    "module_visibility": ["agent_studio", "comment_lab", "label_lab"],
                    "status": "healthy",
                    "detail": "ok",
                    "models": [{"provider_model_id": "gemma4", "model_type": "llm"}],
                }
            ],
            "items": [
                {
                    "router_model_id": "local_llama_server::gemma4",
                    "model_key": "local_llama_server::gemma4",
                    "source_id": "local_llama_server",
                    "source_label": "Local llama-server",
                    "source_kind": "openai-compatible",
                    "source_adapter": "llama_cpp_server",
                    "source_base_url": "http://127.0.0.1:8081/v1",
                    "module_visibility": ["agent_studio", "comment_lab", "label_lab"],
                    "provider_model_id": "gemma4",
                    "model_type": "llm",
                    "letta_handle": "openai-proxy/local_llama_server::gemma4",
                    "agent_studio_available": True,
                    "comment_lab_available": True,
                    "label_lab_available": True,
                    "structured_output_mode": "json_schema",
                }
            ],
        }


def test_runtime_options_use_router_catalog_and_letta_intersection(monkeypatch) -> None:
    monkeypatch.setattr(model_options, "model_router_client", _FakeRouterClient())
    monkeypatch.setattr(
        model_options,
        "_resolve_letta_catalog_handles",
        lambda: ({"openai-proxy/local_llama_server::gemma4"}, {"letta/letta-free"}),
    )

    chat_options, _ = runtime.runtime_options("chat", force_refresh=True)
    comment_options, _ = runtime.runtime_options("comment", force_refresh=True)
    label_options, _ = runtime.runtime_options("label", force_refresh=True)

    assert chat_options[0]["key"] == "openai-proxy/local_llama_server::gemma4"
    assert comment_options[0]["key"] == "local_llama_server::gemma4"
    assert label_options[0]["structured_output_mode"] == "json_schema"


def test_resolve_comment_selection_uses_router_base_url_and_key(monkeypatch) -> None:
    monkeypatch.setattr(model_options, "model_router_client", _FakeRouterClient())
    monkeypatch.setattr(
        model_options,
        "_resolve_letta_catalog_handles",
        lambda: ({"openai-proxy/local_llama_server::gemma4"}, set()),
    )

    selection = runtime.resolve_comment_model_selection(model_key="local_llama_server::gemma4")

    assert selection["base_url"] == "http://model-router.local/v1"
    assert selection["provider_model_id"] == "local_llama_server::gemma4"
    assert selection["upstream_provider_model_id"] == "gemma4"
    assert selection["api_key"] == "router-token"
