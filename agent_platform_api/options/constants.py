from __future__ import annotations

from agent_platform_api.models.common import ScenarioType

MODEL_OPTION_OVERRIDES: dict[str, dict[str, str]] = {
    "lmstudio_openai/gemma-4-31b-it": {
        "label": "Gemma 4 31B IT",
        "description": "Local model discovered from Unsloth Studio.",
    },
    "lmstudio_openai/qwen3.5-27b": {
        "label": "Qwen 3.5 27B",
        "description": "Recommended default for local development.",
    },
    "lmstudio_openai/qwen/qwen3.5-35b-a3b": {
        "label": "Qwen 3.5 35B A3B",
        "description": "Higher quality but heavier VRAM usage.",
    },
    "openai-proxy/doubao-seed-1-8-251228": {
        "label": "Doubao Seed 1.8 (ARK)",
        "description": "Requires OpenAI-compatible ARK provider configured in Letta server.",
    },
}

PROVIDER_MODEL_OPTION_OVERRIDES: dict[str, dict[str, str]] = {
    "gemma-4-31b-it": {
        "label": "Gemma 4 31B IT",
        "description": "Local model discovered from Unsloth Studio.",
    },
    "gemma4": {
        "label": "Gemma 4 (llama-server)",
        "description": "Local GGUF model served by llama-server with JSON schema support.",
    },
    "qwen3.5-27b": {
        "label": "Qwen 3.5 27B",
        "description": "Recommended default for local development.",
    },
    "qwen/qwen3.5-35b-a3b": {
        "label": "Qwen 3.5 35B A3B",
        "description": "Higher quality but heavier VRAM usage.",
    },
    "doubao-seed-1-8-251228": {
        "label": "Doubao Seed 1.8 (ARK)",
        "description": "OpenAI-compatible ARK provider model.",
    },
}

MODEL_OPTION_PRIORITY = {key: index for index, key in enumerate(MODEL_OPTION_OVERRIDES)}
PROVIDER_MODEL_OPTION_PRIORITY = {
    key: index for index, key in enumerate(PROVIDER_MODEL_OPTION_OVERRIDES)
}

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

DEFAULT_MODEL = ""
DEFAULT_CHAT_PROMPT_KEY = "chat_v20260418"
DEFAULT_CHAT_PERSONA_KEY = "chat_linxiaotang"
DEFAULT_COMMENT_PROMPT_KEY = "comment_v20260418"
DEFAULT_COMMENT_PERSONA_KEY = "comment_linxiaotang"
DEFAULT_LABEL_PROMPT_KEY = "label_generic_entities_v1"
DEFAULT_EMBEDDING = ""

SCENARIO_DEFAULTS: dict[ScenarioType, dict[str, str]] = {
    "chat": {
        "prompt_key": DEFAULT_CHAT_PROMPT_KEY,
        "persona_key": DEFAULT_CHAT_PERSONA_KEY,
    },
    "comment": {
        "prompt_key": DEFAULT_COMMENT_PROMPT_KEY,
        "persona_key": DEFAULT_COMMENT_PERSONA_KEY,
    },
    "label": {
        "prompt_key": DEFAULT_LABEL_PROMPT_KEY,
        "persona_key": "",
    },
}
