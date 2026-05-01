from __future__ import annotations

import asyncio

import agent_platform_api.options.catalog as options_catalog
import agent_platform_api.options.letta_catalog as letta_catalog
import agent_platform_api.runtime as runtime
from agent_platform_api.routers import core, platform_meta


class _FakeRouterClient:
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
                    "allowlist_applied": None,
                    "allowlist_checked_at": None,
                    "raw_model_count": 1,
                    "filtered_model_count": 1,
                },
                {
                    "id": "ark",
                    "label": "Volcengine Ark",
                    "kind": "openai-compatible",
                    "adapter": "ark_openai",
                    "base_url": "https://ark.example/api/v3",
                    "module_visibility": ["agent_studio", "comment_lab"],
                    "status": "healthy",
                    "detail": "Allowlist applied: 1 of 3 catalog entries remain selectable.",
                    "models": [{"provider_model_id": "doubao-seed-1-8-251228", "model_type": "llm"}],
                    "allowlist_applied": True,
                    "allowlist_checked_at": "2026-04-22T12:00:00+00:00",
                    "raw_model_count": 3,
                    "filtered_model_count": 1,
                },
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
                },
                {
                    "router_model_id": "ark::doubao-seed-1-8-251228",
                    "model_key": "ark::doubao-seed-1-8-251228",
                    "source_id": "ark",
                    "source_label": "Volcengine Ark",
                    "source_kind": "openai-compatible",
                    "source_adapter": "ark_openai",
                    "source_base_url": "https://ark.example/api/v3",
                    "module_visibility": ["agent_studio", "comment_lab"],
                    "provider_model_id": "doubao-seed-1-8-251228",
                    "model_type": "llm",
                    "letta_handle": "openai-proxy/ark::doubao-seed-1-8-251228",
                    "agent_studio_available": True,
                    "comment_lab_available": True,
                    "label_lab_available": False,
                    "structured_output_mode": None,
                },
            ],
        }


def test_options_api_uses_router_catalog_for_all_scenarios(monkeypatch) -> None:
    monkeypatch.setattr(core, "ensure_platform_api_enabled", lambda: None)
    monkeypatch.setattr(options_catalog, "model_router_client", _FakeRouterClient())
    monkeypatch.setattr(
        letta_catalog,
        "resolve_letta_catalog_handles",
        lambda: (
            {
                "openai-proxy/local_llama_server::gemma4",
                "openai-proxy/ark::doubao-seed-1-8-251228",
            },
            {"letta/letta-free"},
        ),
    )

    chat_payload = asyncio.run(core.api_get_options(refresh=True, scenario="chat"))
    comment_payload = asyncio.run(core.api_get_options(refresh=True, scenario="comment"))
    label_payload = asyncio.run(core.api_get_options(refresh=True, scenario="label"))

    assert chat_payload["defaults"]["model"] == ""
    assert [item["key"] for item in chat_payload["models"]] == [
        "openai-proxy/local_llama_server::gemma4",
        "openai-proxy/ark::doubao-seed-1-8-251228",
    ]
    assert [item["key"] for item in comment_payload["models"]] == [
        "local_llama_server::gemma4",
        "ark::doubao-seed-1-8-251228",
    ]
    assert [item["key"] for item in label_payload["models"]] == ["local_llama_server::gemma4"]
    assert label_payload["models"][0]["structured_output_mode"] == "json_schema"
    assert label_payload["defaults"]["schema_key"] == "label_entity_groups_v1"
    assert chat_payload["agent_studio"] == {"temperature": None, "top_p": None}
    assert comment_payload["commenting"]["cache_prompt"] is False
    assert comment_payload["commenting"]["temperature"] == 0.6
    assert comment_payload["commenting"]["top_p"] == 1.0
    assert label_payload["labeling"]["temperature"] == 0.0
    assert label_payload["labeling"]["top_p"] == 1.0


def test_model_catalog_api_reports_router_source_health_and_items(monkeypatch) -> None:
    monkeypatch.setattr(platform_meta, "ensure_platform_api_enabled", lambda: None)
    monkeypatch.setattr(options_catalog, "model_router_client", _FakeRouterClient())
    monkeypatch.setattr(
        letta_catalog,
        "resolve_letta_catalog_handles",
        lambda: ({"openai-proxy/local_llama_server::gemma4"}, {"letta/letta-free"}),
    )

    payload = asyncio.run(platform_meta.api_platform_model_catalog(refresh=True))
    ark_source = next(source for source in payload["sources"] if source["id"] == "ark")
    llama_model = next(item for item in payload["items"] if item["source_id"] == "local_llama_server")
    ark_model = next(item for item in payload["items"] if item["source_id"] == "ark")

    assert payload["generated_at"] == 123.0
    assert payload["router"]["base_url"] == "http://model-router.local/v1"
    assert ark_source["allowlist_applied"] is True
    assert ark_source["raw_model_count"] == 3
    assert ark_source["filtered_model_count"] == 1
    assert llama_model["provider_model_id"] == "local_llama_server::gemma4"
    assert llama_model["upstream_provider_model_id"] == "gemma4"
    assert llama_model["label_lab_available"] is True
    assert ark_model["agent_studio_available"] is False
