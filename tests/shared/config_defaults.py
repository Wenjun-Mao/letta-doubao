from __future__ import annotations

import os

# Test/runtime defaults used by suites and validation scripts.
DEFAULT_LETTA_BASE_URL = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
DEFAULT_AGENT_PLATFORM_API_BASE_URL = os.getenv("AGENT_PLATFORM_API_BASE_URL", "http://127.0.0.1:8284")
DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_CONTEXT_WINDOW_LIMIT = 16384
DEFAULT_CLIENT_TIMEOUT_SECONDS = 300.0
DEFAULT_SCENARIO = "chat"
DEFAULT_PROMPT_KEY = "chat_v20260418"
DEFAULT_PERSONA_KEY = "chat_linxiaotang"
DEFAULT_TEST_MODEL_HANDLE = "lmstudio_openai/gemma-4-31b-it"
DEFAULT_EMBEDDING_HANDLE = "letta/letta-free"

# Strict phrase checks used to detect persona breaks (AI/virtual self-disclosure).
DEFAULT_FORBIDDEN_REPLY_SUBSTRINGS = [
    "我是ai",
    "我是一个ai",
    "作为ai",
    "语言模型",
    "大语言模型",
    "虚拟助手",
    "虚拟角色",
    "我是虚拟",
    "我是模拟",
    "我不是真的",
    "我并不真实",
    "我不是真实",
    "线上角色",
    "我是机器人",
    "程序生成",
]

# Lean central run index files for quick historical review.
RUN_INDEX_CSV = "run_index.csv"
RUN_INDEX_JSONL = "run_index.jsonl"
RUN_INDEX_FIELDS = [
    "run_tag",
    "run_started_at",
    "test_name",
    "config_file",
    "model",
    "embedding",
    "prompt_key",
    "pass",
    "forbidden_hits",
    "human_memory_changed",
    "duration_seconds",
    "output_file",
    "error",
]

