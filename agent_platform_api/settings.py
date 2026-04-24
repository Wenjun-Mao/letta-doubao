from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


CommentingTaskShapeSetting = Literal["classic", "all_in_system", "structured_output"]
ModelSourceKind = Literal["openai-compatible"]
ModelSourceAdapter = Literal["generic_openai", "ark_openai", "llama_cpp_server"]
ScenarioName = Literal["chat", "comment", "label"]
_KNOWN_MODEL_HANDLE_PREFIXES = ("lmstudio_openai/", "openai-proxy/", "openai/", "anthropic/")
_DEFAULT_SECRETS_DIR = Path("/run/secrets")
_VERSION_PATH_RE = re.compile(r"/v\d+(?:\.\d+)?$", re.IGNORECASE)


class ModelSourceConfig(BaseModel):
    id: str
    label: str
    base_url: str
    kind: ModelSourceKind = "openai-compatible"
    adapter: ModelSourceAdapter = "generic_openai"
    enabled: bool = True
    enabled_for: list[ScenarioName] = Field(default_factory=list)
    letta_handle_prefix: str = ""
    api_key_env: str = ""
    api_key_secret: str = ""

    @field_validator("id", "label", "base_url", "adapter", "letta_handle_prefix", "api_key_env", "api_key_secret")
    @classmethod
    def _strip_text_fields(cls, value: str) -> str:
        return str(value or "").strip()

    @field_validator("adapter")
    @classmethod
    def _normalize_adapter(cls, value: str) -> str:
        normalized = str(value or "").strip().lower().replace("-", "_")
        if not normalized:
            return "generic_openai"
        if normalized not in {"generic_openai", "ark_openai", "llama_cpp_server"}:
            raise ValueError("adapter must be 'generic_openai', 'ark_openai', or 'llama_cpp_server'")
        return normalized

    @field_validator("enabled_for", mode="before")
    @classmethod
    def _normalize_enabled_for(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("enabled_for")
    @classmethod
    def _validate_enabled_for(cls, value: list[ScenarioName]) -> list[ScenarioName]:
        normalized = [str(item or "").strip().lower() for item in value]
        deduped: list[ScenarioName] = []
        for item in normalized:
            if item not in {"chat", "comment", "label"}:
                raise ValueError("enabled_for entries must be 'chat', 'comment', and/or 'label'")
            typed_item = item  # type: ignore[assignment]
            if typed_item not in deduped:
                deduped.append(typed_item)
        if not deduped:
            raise ValueError("enabled_for must include at least one scenario")
        return deduped

    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")

    def models_endpoint(self) -> str:
        base = self.normalized_base_url()
        if not base:
            return ""
        if base.endswith("/models"):
            return base
        if base.endswith("/chat/completions"):
            return f"{base[:-len('/chat/completions')]}/models"
        if _VERSION_PATH_RE.search(base):
            return f"{base}/models"
        return f"{base}/v1/models"

    def chat_completions_url(self) -> str:
        base = self.normalized_base_url()
        if not base:
            return ""
        if base.endswith("/chat/completions"):
            return base
        if _VERSION_PATH_RE.search(base):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def derive_letta_handle(self, provider_model_id: str) -> str | None:
        model_id = str(provider_model_id or "").strip().strip("/")
        if not model_id:
            return None
        lowered = model_id.lower()
        if lowered.startswith(_KNOWN_MODEL_HANDLE_PREFIXES):
            return model_id
        prefix = self.letta_handle_prefix.strip().strip("/")
        if not prefix:
            return None
        return f"{prefix}/{model_id}"

    def resolve_api_key(
        self,
        *,
        secrets_dir: Path = _DEFAULT_SECRETS_DIR,
        environ: dict[str, str] | None = None,
    ) -> str:
        env_map = os.environ if environ is None else environ
        secret_name = self.api_key_secret.strip()
        if secret_name:
            secret_path = secrets_dir / secret_name
            try:
                if secret_path.is_file():
                    secret_value = secret_path.read_text(encoding="utf-8").strip()
                    if secret_value:
                        return secret_value
            except OSError:
                pass

        env_name = self.api_key_env.strip()
        if env_name:
            env_value = str(env_map.get(env_name, "") or "").strip()
            if env_value:
                return env_value
        if self.adapter == "llama_cpp_server":
            return str(env_map.get("UNSLOTH_API_KEY", "") or "").strip()
        return ""


class AgentPlatformSettings(BaseSettings):
    model_sources: list[ModelSourceConfig] = Field(default_factory=list)
    model_router_base_url: str = ""
    model_router_api_key_env: str = "MODEL_ROUTER_API_KEY"
    model_router_api_key_secret: str = "model-router-api-key"
    commenting_timeout_seconds: float = 60.0
    commenting_max_tokens: int = 0
    commenting_task_shape: CommentingTaskShapeSetting = "classic"
    labeling_timeout_seconds: float = 60.0
    labeling_max_tokens: int = 1024
    labeling_repair_retry_count: int = 1
    options_cache_ttl_seconds: int = 30
    model_discovery_timeout_seconds: float = 5.0

    model_config = SettingsConfigDict(
        env_prefix="AGENT_PLATFORM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        secrets_dir=str(_DEFAULT_SECRETS_DIR),
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        # Secret files should win over plain environment variables.
        if not _DEFAULT_SECRETS_DIR.is_dir():
            return (
                init_settings,
                env_settings,
                dotenv_settings,
            )
        return (
            init_settings,
            file_secret_settings,
            env_settings,
            dotenv_settings,
        )

    @field_validator("model_sources")
    @classmethod
    def _ensure_unique_source_ids(cls, value: list[ModelSourceConfig]) -> list[ModelSourceConfig]:
        seen: set[str] = set()
        for source in value:
            if source.id in seen:
                raise ValueError(f"Duplicate model source id: {source.id}")
            seen.add(source.id)
        return value

    @field_validator("model_router_base_url", "model_router_api_key_env", "model_router_api_key_secret")
    @classmethod
    def _strip_router_text_fields(cls, value: str) -> str:
        return str(value or "").strip()

    @field_validator("commenting_timeout_seconds")
    @classmethod
    def _clamp_timeout_seconds(cls, value: float) -> float:
        return max(5.0, min(600.0, float(value)))

    @field_validator("commenting_max_tokens")
    @classmethod
    def _clamp_commenting_max_tokens(cls, value: int) -> int:
        if int(value) <= 0:
            return 0
        return max(64, min(8192, int(value)))

    @field_validator("labeling_timeout_seconds")
    @classmethod
    def _clamp_labeling_timeout_seconds(cls, value: float) -> float:
        return max(5.0, min(600.0, float(value)))

    @field_validator("labeling_max_tokens")
    @classmethod
    def _clamp_labeling_max_tokens(cls, value: int) -> int:
        if int(value) <= 0:
            return 0
        return max(64, min(8192, int(value)))

    @field_validator("labeling_repair_retry_count")
    @classmethod
    def _clamp_labeling_repair_retry_count(cls, value: int) -> int:
        return max(0, min(3, int(value)))

    @field_validator("options_cache_ttl_seconds")
    @classmethod
    def _clamp_cache_ttl(cls, value: int) -> int:
        return max(1, int(value))

    @field_validator("model_discovery_timeout_seconds")
    @classmethod
    def _clamp_discovery_timeout(cls, value: float) -> float:
        return max(1.0, min(60.0, float(value)))

    def normalized_model_router_base_url(self) -> str:
        return self.model_router_base_url.rstrip("/")

    def model_router_v1_base_url(self) -> str:
        base = self.normalized_model_router_base_url()
        if not base:
            return ""
        if _VERSION_PATH_RE.search(base):
            return base
        return f"{base}/v1"

    def resolve_model_router_api_key(
        self,
        *,
        secrets_dir: Path = _DEFAULT_SECRETS_DIR,
        environ: dict[str, str] | None = None,
    ) -> str:
        env_map = os.environ if environ is None else environ
        secret_name = self.model_router_api_key_secret.strip()
        if secret_name:
            secret_path = secrets_dir / secret_name
            try:
                if secret_path.is_file():
                    secret_value = secret_path.read_text(encoding="utf-8").strip()
                    if secret_value:
                        return secret_value
            except OSError:
                pass

        env_name = self.model_router_api_key_env.strip()
        if env_name:
            env_value = str(env_map.get(env_name, "") or "").strip()
            if env_value:
                return env_value
        return ""


@lru_cache(maxsize=1)
def get_settings() -> AgentPlatformSettings:
    return AgentPlatformSettings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
