from __future__ import annotations

import argparse
import os
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_ROOT = Path(__file__).resolve().parent
DEFAULT_ROUTER_MODEL_KEY = "dgx_vllm::qwen3.6-35b-a3b-fp8"
DEFAULT_AGENT_MODEL_HANDLE = f"openai-proxy/{DEFAULT_ROUTER_MODEL_KEY}"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ChatMemoryEvalConfig:
    api_base_url: str = "http://127.0.0.1:8284"
    model_router_base_url: str = ""
    model_router_api_key: str = ""
    output_dir: Path = Path("evals/chat_memory_eval/outputs")
    fixtures_dir: Path = Path("evals/chat_memory_eval/fixtures")
    fixture_key: str = "recent_user_chat_turns"
    rounds: int = 3
    stop_on_error: bool = False
    keep_agents: bool = False
    model: str = DEFAULT_AGENT_MODEL_HANDLE
    prompt_key: str = "chat_v20260516"
    persona_key: str = "chat_linxiaotang"
    embedding: str = "letta/letta-free"
    timeout_seconds: float = 180.0
    retry_count: int = 0
    judge_enabled: bool = True
    judge_model_key: str = ""
    judge_timeout_seconds: float = 120.0
    api_retry_count: int = 2


def _project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _strip(value: object) -> str:
    return str(value or "").strip()


def _env_router_base_url() -> str:
    return _strip(
        os.getenv("CHAT_MEMORY_EVAL_MODEL_ROUTER_BASE_URL")
        or os.getenv("AGENT_PLATFORM_MODEL_ROUTER_BASE_URL")
        or os.getenv("MODEL_ROUTER_BASE_URL")
    )


def _env_router_api_key() -> str:
    return _strip(os.getenv("MODEL_ROUTER_API_KEY") or "local-router-dev-key")


def load_config(path: Path) -> ChatMemoryEvalConfig:
    env_router_base_url = _env_router_base_url()
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    payload: dict[str, Any] = {}
    if path.exists():
        with path.open("rb") as handle:
            payload = tomllib.load(handle)
    elif path != WORKFLOW_ROOT / "config.toml":
        raise ConfigError(f"Config file not found: {path}")

    config = ChatMemoryEvalConfig(
        api_base_url=_strip(payload.get("api_base_url", ChatMemoryEvalConfig.api_base_url)).rstrip("/"),
        model_router_base_url=_strip(payload.get("model_router_base_url", "")) or env_router_base_url,
        model_router_api_key=_strip(payload.get("model_router_api_key", "")) or _env_router_api_key(),
        output_dir=_project_path(payload.get("output_dir", ChatMemoryEvalConfig.output_dir)),
        fixtures_dir=_project_path(payload.get("fixtures_dir", ChatMemoryEvalConfig.fixtures_dir)),
        fixture_key=_strip(payload.get("fixture_key", ChatMemoryEvalConfig.fixture_key)),
        rounds=int(payload.get("rounds", ChatMemoryEvalConfig.rounds)),
        stop_on_error=bool(payload.get("stop_on_error", ChatMemoryEvalConfig.stop_on_error)),
        keep_agents=bool(payload.get("keep_agents", ChatMemoryEvalConfig.keep_agents)),
        model=_strip(payload.get("model", ChatMemoryEvalConfig.model)),
        prompt_key=_strip(payload.get("prompt_key", ChatMemoryEvalConfig.prompt_key)),
        persona_key=_strip(payload.get("persona_key", ChatMemoryEvalConfig.persona_key)),
        embedding=_strip(payload.get("embedding", ChatMemoryEvalConfig.embedding)),
        timeout_seconds=float(payload.get("timeout_seconds", ChatMemoryEvalConfig.timeout_seconds)),
        retry_count=int(payload.get("retry_count", ChatMemoryEvalConfig.retry_count)),
        judge_enabled=bool(payload.get("judge_enabled", ChatMemoryEvalConfig.judge_enabled)),
        judge_model_key=_strip(payload.get("judge_model_key", "")),
        judge_timeout_seconds=float(payload.get("judge_timeout_seconds", ChatMemoryEvalConfig.judge_timeout_seconds)),
        api_retry_count=int(payload.get("api_retry_count", ChatMemoryEvalConfig.api_retry_count)),
    )
    validate_config(config)
    return config


def validate_config(config: ChatMemoryEvalConfig) -> None:
    if not config.api_base_url:
        raise ConfigError("api_base_url is required")
    if not config.fixtures_dir.is_dir():
        raise ConfigError(f"fixtures_dir does not exist: {config.fixtures_dir}")
    if not config.fixture_key:
        raise ConfigError("fixture_key is required")
    if config.rounds < 1:
        raise ConfigError("rounds must be >= 1")
    if not config.model:
        raise ConfigError("model is required")
    if not config.prompt_key.startswith("chat_"):
        raise ConfigError("prompt_key must start with chat_")
    if not config.persona_key.startswith("chat_"):
        raise ConfigError("persona_key must start with chat_")
    if config.timeout_seconds <= 0 or config.timeout_seconds > 600:
        raise ConfigError("timeout_seconds must be > 0 and <= 600")
    if not 0 <= config.retry_count <= 5:
        raise ConfigError("retry_count must be between 0 and 5")
    if config.judge_timeout_seconds <= 0 or config.judge_timeout_seconds > 600:
        raise ConfigError("judge_timeout_seconds must be > 0 and <= 600")
    if config.api_retry_count < 0:
        raise ConfigError("api_retry_count must be >= 0")


def apply_cli_overrides(config: ChatMemoryEvalConfig, args: argparse.Namespace) -> ChatMemoryEvalConfig:
    updates: dict[str, Any] = {}
    for field in (
        "api_base_url",
        "model",
        "prompt_key",
        "persona_key",
        "embedding",
        "fixture_key",
        "judge_model_key",
    ):
        value = getattr(args, field, None)
        if value:
            updates[field] = _strip(value)
    if args.output_dir:
        updates["output_dir"] = _project_path(args.output_dir)
    for field in ("rounds", "retry_count"):
        value = getattr(args, field, None)
        if value is not None:
            updates[field] = int(value)
    if args.timeout_seconds is not None:
        updates["timeout_seconds"] = float(args.timeout_seconds)
    if args.judge_enabled is not None:
        updates["judge_enabled"] = bool(args.judge_enabled)
    if args.keep_agents:
        updates["keep_agents"] = True

    next_config = replace(config, **updates)
    validate_config(next_config)
    return next_config


def router_v1_base_url(config: ChatMemoryEvalConfig) -> str:
    base = (config.model_router_base_url or "http://127.0.0.1:8290").rstrip("/")
    if base.lower().endswith("/v1"):
        return base
    return f"{base}/v1"


def router_model_key_from_agent_handle(model: str) -> str:
    handle = _strip(model)
    if handle.startswith("openai-proxy/"):
        handle = handle.split("/", 1)[1]
    if "::" in handle:
        return handle
    return DEFAULT_ROUTER_MODEL_KEY
