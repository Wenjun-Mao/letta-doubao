from __future__ import annotations

from typing import Any

from agent_platform_api.dependencies import client


def looks_like_embedding_handle(handle: str) -> bool:
    lowered = str(handle or "").strip().lower()
    return "embedding" in lowered or "embed" in lowered


def resolve_model_handle(model_obj: Any) -> str:
    for attr in ("handle", "id", "model", "name"):
        value = str(getattr(model_obj, attr, "") or "").strip()
        if value:
            return value
    return ""


def resolve_letta_catalog_handles() -> tuple[set[str], set[str]]:
    discovered_model_handles: set[str] = set()
    discovered_embedding_handles: set[str] = set()

    try:
        for embedding in list(client.models.embeddings.list()):
            handle = resolve_model_handle(embedding)
            if handle:
                discovered_embedding_handles.add(handle)
    except Exception:
        pass

    try:
        for model in list(client.models.list()):
            handle = resolve_model_handle(model)
            model_type = str(
                getattr(model, "api_model_type", "") or getattr(model, "model_type", "") or ""
            ).strip().lower()
            if not handle:
                continue
            if looks_like_embedding_handle(handle) or model_type in {"embedding", "embeddings"}:
                discovered_embedding_handles.add(handle)
                continue
            discovered_model_handles.add(handle)
    except Exception:
        pass

    return discovered_model_handles, discovered_embedding_handles
