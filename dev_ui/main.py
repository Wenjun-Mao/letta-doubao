from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import os
import sys
from typing import Any

# Add project root to sys.path to resolve imports properly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from letta_client import Letta
from utils.message_parser import chat
from prompts.persona import PERSONAS, HUMAN_TEMPLATE
from prompts.system_prompts import (
    AGGRESSIVE_MEMORY_PROMPT,
    CUSTOM_V1_PROMPT,
    MEMGPT_V2_CHAT_PROMPT,
    STRUCTURED_MEMORY_PROMPT,
    TOOLS_FIRST_PROMPT,
)

app = FastAPI(title="Letta Dev UI")

# Allow CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    agent_id: str
    message: str

class AgentCreateRequest(BaseModel):
    name: str = "dev-agent"
    model: str = "lmstudio_openai/qwen3.5-27b"
    prompt_key: str = "custom_v1"
    embedding: str | None = None


PREFERRED_MODEL_OPTIONS = [
    {
        "key": "lmstudio_openai/qwen3.5-27b",
        "label": "Qwen 3.5 27B",
        "description": "Recommended default for local development.",
    },
    {
        "key": "lmstudio_openai/qwen/qwen3.5-35b-a3b",
        "label": "Qwen 3.5 35B A3B",
        "description": "Higher quality but heavier VRAM usage.",
    },
    {
        "key": "openai-proxy/doubao-seed-1-8-251228",
        "label": "Doubao Seed 1.8 (ARK)",
        "description": "Requires OpenAI-compatible ARK provider configured in Letta server.",
    },
]

PREFERRED_EMBEDDING_OPTIONS = [
    {
        "key": "lmstudio_openai/text-embedding-qwen3-embedding-0.6b",
        "label": "Qwen Embedding 0.6B (Local)",
        "description": "Local embedding model served by LM Studio.",
    },
    {
        "key": "lmstudio_openai/text-embedding-nomic-embed-text-v1.5",
        "label": "Nomic Embed v1.5 (Local)",
        "description": "Alternative local embedding model via LM Studio.",
    },
    {
        "key": "letta/letta-free",
        "label": "Letta Free Embedding (Cloud)",
        "description": "Cloud embedding endpoint; requires network access and endpoint support.",
    },
]

PROMPT_OPTIONS = [
    {
        "key": "custom_v1",
        "label": "Custom V1 (Baseline)",
        "description": "Current stable baseline with Chinese output formatting rules.",
    },
    {
        "key": "memgpt_v2_chat",
        "label": "MemGPT V2 Chat",
        "description": "V2-style control-flow and context instructions adapted for this project.",
    },
    {
        "key": "aggressive_memory",
        "label": "V1 Aggressive Memory",
        "description": "Stronger instruction to persist new user facts.",
    },
    {
        "key": "structured_memory",
        "label": "V1 Structured Memory",
        "description": "Numbered operational rules for memory updates.",
    },
    {
        "key": "tools_first",
        "label": "V1 Tools First",
        "description": "Tool-call-first variant for weak function-calling adherence.",
    },
]

PROMPT_MAP = {
    "custom_v1": CUSTOM_V1_PROMPT,
    "memgpt_v2_chat": MEMGPT_V2_CHAT_PROMPT,
    "aggressive_memory": AGGRESSIVE_MEMORY_PROMPT,
    "structured_memory": STRUCTURED_MEMORY_PROMPT,
    "tools_first": TOOLS_FIRST_PROMPT,
}

DEFAULT_MODEL = PREFERRED_MODEL_OPTIONS[0]["key"]
DEFAULT_PROMPT_KEY = "custom_v1"
DEFAULT_EMBEDDING = ""

# Letta Client Initialization
client = Letta(base_url=os.getenv("LETTA_BASE_URL", "http://localhost:8283"))


def _dedupe_options(options: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for option in options:
        key = option.get("key", "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(option)
    return out


def _runtime_options() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    model_options = [dict(option) for option in PREFERRED_MODEL_OPTIONS]
    embedding_options = [dict(option) for option in PREFERRED_EMBEDDING_OPTIONS]
    known_embedding_keys = {option["key"] for option in embedding_options}

    discovered_model_handles: set[str] = set()
    discovered_embedding_handles: set[str] = set()

    def _looks_like_embedding_handle(handle: str) -> bool:
        lowered = handle.lower()
        return "embedding" in lowered or "embed" in lowered

    try:
        for embedding in list(client.models.embeddings.list()):
            handle = str(getattr(embedding, "handle", "") or "")
            if handle:
                discovered_embedding_handles.add(handle)
    except Exception:
        pass

    try:
        for model in list(client.models.list()):
            handle = str(getattr(model, "handle", "") or "")
            model_type = str(getattr(model, "api_model_type", "") or getattr(model, "model_type", "") or "")
            if not handle:
                continue
            if _looks_like_embedding_handle(handle):
                discovered_embedding_handles.add(handle)
                continue
            # Never surface embedding handles in LLM selector.
            if handle in discovered_embedding_handles or handle in known_embedding_keys:
                continue
            if model_type and model_type != "llm":
                continue
            discovered_model_handles.add(handle)
    except Exception:
        # UI must stay usable even if model discovery fails.
        pass

    # Include any extra handles discovered from the running Letta server.
    existing_model_keys = {option["key"] for option in model_options}
    for handle in sorted(discovered_model_handles):
        if handle not in existing_model_keys:
            model_options.append(
                {
                    "key": handle,
                    "label": handle,
                    "description": "Discovered from current Letta server.",
                }
            )

    existing_embedding_keys = {option["key"] for option in embedding_options}
    for handle in sorted(discovered_embedding_handles):
        if handle not in existing_embedding_keys:
            embedding_options.append(
                {
                    "key": handle,
                    "label": handle,
                    "description": "Discovered from current Letta server.",
                }
            )

    model_options = _dedupe_options(model_options)
    embedding_options = _dedupe_options(embedding_options)

    # Mark whether each option is currently resolvable by this Letta server.
    for option in model_options:
        option["available"] = option["key"] in discovered_model_handles if discovered_model_handles else True

    for option in embedding_options:
        option["available"] = option["key"] in discovered_embedding_handles if discovered_embedding_handles else True

    return model_options, embedding_options


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except Exception:
        return str(value)


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return _safe_json(json.loads(stripped))
            except Exception:
                return value
        return value
    if isinstance(value, list):
        text_parts = [getattr(item, "text", None) for item in value]
        valid_parts = [part for part in text_parts if isinstance(part, str) and part]
        if valid_parts:
            return " ".join(valid_parts)
        return _safe_json(value)
    if isinstance(value, (dict, tuple)):
        return _safe_json(value)
    return str(value)


def _to_jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return _to_jsonable(model_dump(mode="json"))
        except TypeError:
            return _to_jsonable(model_dump())
        except Exception:
            pass

    to_dict = getattr(value, "dict", None)
    if callable(to_dict):
        try:
            return _to_jsonable(to_dict())
        except Exception:
            pass

    return _normalize_text(value)


def _serialize_message(msg: Any) -> dict[str, Any]:
    message_type = getattr(msg, "message_type", "unknown")
    role = getattr(msg, "role", message_type)

    content: Any = getattr(msg, "content", None)
    if message_type == "reasoning_message":
        content = getattr(msg, "reasoning", content)
    if message_type == "tool_return_message":
        content = getattr(msg, "tool_return", content)

    tool_name = None
    tool_arguments = None
    tool_call = getattr(msg, "tool_call", None)
    if tool_call is not None:
        tool_name = getattr(tool_call, "name", None)
        tool_arguments = _normalize_text(getattr(tool_call, "arguments", None))

    timestamp = getattr(msg, "created_at", None) or getattr(msg, "date", None)

    return {
        "id": str(getattr(msg, "id", "")),
        "created_at": str(timestamp or ""),
        "message_type": message_type,
        "role": role,
        "status": str(getattr(msg, "status", "")),
        "name": tool_name,
        "tool_arguments": tool_arguments,
        "content": _normalize_text(content),
    }


def _derive_last_interaction_at(agent_id: str, last_updated_at: str = "") -> str:
    if last_updated_at:
        return last_updated_at
    try:
        messages = list(client.agents.messages.list(agent_id=agent_id))
    except Exception:
        return ""

    latest = ""
    for msg in messages:
        message_type = str(getattr(msg, "message_type", ""))
        if message_type == "system_message":
            continue
        created_at = str(getattr(msg, "created_at", None) or getattr(msg, "date", None) or "")
        if created_at and created_at > latest:
            latest = created_at
    return latest

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open(os.path.join(os.path.dirname(__file__), "static", "index.html"), "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/options")
async def api_get_options():
    model_options, embedding_options = _runtime_options()

    default_model = DEFAULT_MODEL
    if not any(option["key"] == default_model for option in model_options):
        default_model = model_options[0]["key"] if model_options else ""

    default_embedding = os.getenv("LETTA_DEFAULT_EMBEDDING_HANDLE") or os.getenv("LETTA_EMBEDDING_HANDLE") or DEFAULT_EMBEDDING
    if default_embedding and not any(option["key"] == default_embedding for option in embedding_options):
        default_embedding = ""

    for option in embedding_options:
        option["is_default"] = bool(default_embedding and option["key"] == default_embedding)

    return {
        "models": model_options,
        "embeddings": embedding_options,
        "prompts": PROMPT_OPTIONS,
        "defaults": {
            "model": default_model,
            "prompt_key": DEFAULT_PROMPT_KEY,
            "embedding": default_embedding,
        },
    }


@app.get("/api/agents")
async def api_list_agents(limit: int = 100):
    """List existing agents so the UI can pull and inspect prior state."""
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >= 1")
    if limit > 500:
        limit = 500

    agents = list(client.agents.list())
    items = []
    for agent in agents:
        agent_id = str(getattr(agent, "id", ""))
        last_updated_at = str(getattr(agent, "last_updated_at", ""))
        last_interaction_at = _derive_last_interaction_at(agent_id, last_updated_at)
        items.append(
            {
                "id": agent_id,
                "name": str(getattr(agent, "name", "")),
                "model": str(getattr(agent, "model", "")),
                "created_at": str(getattr(agent, "created_at", "")),
                "last_updated_at": last_updated_at,
                "last_interaction_at": last_interaction_at,
            }
        )

    # Prefer recently updated agents first.
    items.sort(key=lambda x: (x["last_updated_at"] or x["created_at"]), reverse=True)

    return {
        "total": len(items),
        "items": items[:limit],
    }

@app.post("/api/agents")
async def api_create_agent(request: AgentCreateRequest):
    model_options, embedding_options = _runtime_options()
    allowed_models = {option["key"] for option in model_options}
    allowed_embeddings = {option["key"] for option in embedding_options}

    if request.model not in allowed_models:
        raise HTTPException(status_code=400, detail=f"Invalid model: {request.model}")
    if request.prompt_key not in PROMPT_MAP:
        raise HTTPException(status_code=400, detail=f"Invalid prompt key: {request.prompt_key}")
    if request.embedding and request.embedding not in allowed_embeddings:
        raise HTTPException(status_code=400, detail=f"Invalid embedding handle: {request.embedding}")

    create_args: dict[str, Any] = {
        "name": request.name,
        "system": PROMPT_MAP[request.prompt_key],
        "model": request.model,
        "timezone": "Asia/Shanghai",
        "context_window_limit": 16384,
        "memory_blocks": [
            {
                "label": "persona",
                "value": PERSONAS["linxiaotang"],
            },
            {
                "label": "human",
                "value": HUMAN_TEMPLATE,
            },
        ],
    }
    if request.embedding:
        create_args["embedding"] = request.embedding

    try:
        agent = client.agents.create(**create_args)
    except Exception as exc:
        error_text = str(exc)
        if "Handle" in error_text and "not found" in error_text:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{error_text}. This handle is not registered on the current Letta server. "
                    "If you want LM Studio and Doubao in one server, use a combined env profile (for example .env3)."
                ),
            ) from exc
        raise HTTPException(status_code=400, detail=error_text) from exc

    return {
        "id": agent.id,
        "name": agent.name,
        "model": request.model,
        "embedding": request.embedding,
        "prompt_key": request.prompt_key,
    }

@app.get("/api/agents/{agent_id}/details")
async def api_get_agent_details(agent_id: str):
    agent = client.agents.retrieve(agent_id=agent_id)
    tools_raw = list(client.agents.tools.list(agent_id=agent.id))
    tools = {t.name: t.description for t in tools_raw}
    
    blocks = client.agents.blocks.list(agent_id=agent_id)
    memory = {b.label: b.value for b in blocks}
    
    last_updated_at = str(getattr(agent, "last_updated_at", ""))
    last_interaction_at = _derive_last_interaction_at(agent_id, last_updated_at)

    return {
        "id": getattr(agent, "id", agent_id),
        "name": getattr(agent, "name", "Unknown"),
        "agent_type": str(getattr(agent, "agent_type", "Unknown")),
        "model": getattr(agent, "model", "Unknown"),
        "embedding": getattr(agent, "embedding", None),
        "llm_config": _to_jsonable(getattr(agent, "llm_config", None)),
        "embedding_config": _to_jsonable(getattr(agent, "embedding_config", None)),
        "tool_rules": _to_jsonable(getattr(agent, "tool_rules", None)),
        "description": getattr(agent, "description", None),
        "created_at": str(getattr(agent, "created_at", "")),
        "last_updated_at": last_updated_at,
        "last_interaction_at": last_interaction_at,
        "context_window_limit": getattr(agent, "context_window_limit", None),
        "tools": tools,
        "system": getattr(agent, "system", "Unknown"),
        "memory": memory,
    }


@app.get("/api/agents/{agent_id}/persistent_state")
async def api_get_agent_persistent_state(agent_id: str, limit: int = 120, include_system: bool = False):
    """
    Returns persisted state from Letta backend storage (Postgres/pgvector via Letta API):
    - agent metadata
    - memory blocks
    - attached tools
    - persisted conversation history
    """
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >= 1")
    if limit > 500:
        limit = 500

    agent = client.agents.retrieve(agent_id=agent_id)
    blocks = list(client.agents.blocks.list(agent_id=agent_id))
    tools_raw = list(client.agents.tools.list(agent_id=agent_id))
    messages = list(client.agents.messages.list(agent_id=agent_id))

    serialized_messages = []
    type_counts: dict[str, int] = {}

    for msg in messages:
        message_type = str(getattr(msg, "message_type", "unknown"))
        if not include_system and message_type == "system_message":
            continue

        payload = _serialize_message(msg)
        serialized_messages.append(payload)
        type_counts[message_type] = type_counts.get(message_type, 0) + 1

    total_persisted = len(serialized_messages)
    if len(serialized_messages) > limit:
        serialized_messages = serialized_messages[-limit:]

    memory_blocks = [
        {
            "label": getattr(block, "label", ""),
            "description": getattr(block, "description", ""),
            "limit": getattr(block, "limit", None),
            "value": getattr(block, "value", ""),
        }
        for block in blocks
    ]

    tool_entries = [
        {
            "id": getattr(tool, "id", ""),
            "name": getattr(tool, "name", ""),
            "description": getattr(tool, "description", ""),
        }
        for tool in tools_raw
    ]

    return {
        "source": "letta_backend_persistent_storage",
        "agent": {
            "id": getattr(agent, "id", agent_id),
            "name": getattr(agent, "name", ""),
            "agent_type": str(getattr(agent, "agent_type", "")),
            "model": getattr(agent, "model", ""),
            "embedding": getattr(agent, "embedding", None),
            "created_at": str(getattr(agent, "created_at", "")),
            "last_updated_at": str(getattr(agent, "last_updated_at", "")),
            "context_window_limit": getattr(agent, "context_window_limit", None),
            "tool_rules": _normalize_text(getattr(agent, "tool_rules", None)),
        },
        "memory_blocks": memory_blocks,
        "tools": tool_entries,
        "conversation_history": {
            "total_persisted": total_persisted,
            "displayed": len(serialized_messages),
            "limit": limit,
            "counts_by_type": type_counts,
            "items": serialized_messages,
        },
    }

@app.get("/api/agents/{agent_id}/raw_prompt")
async def api_get_raw_prompt(agent_id: str):
    messages = list(client.agents.messages.list(agent_id=agent_id))
    recent_messages = messages[-10:] if len(messages) >= 10 else messages
    
    formatted_msgs = []
    for msg in recent_messages:
        content = getattr(msg, "content", "")
        if not content:
            content = getattr(msg, "reasoning", str(msg))
        role = getattr(msg, "role", getattr(msg, "message_type", "unknown"))
        formatted_msgs.append({"role": role, "content": _normalize_text(content)})
        
    return {"messages": formatted_msgs}

@app.post("/api/chat")
async def api_chat(request: ChatRequest):
    result = chat(
        client=client,
        agent_id=request.agent_id,
        input=request.message,
    )
    result.pop("raw_messages", None)
    return result

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8284)
