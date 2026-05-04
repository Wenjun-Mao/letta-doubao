from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ade_core.settings_file_loader import load_json_config_list


RouterSourceKind = Literal["openai-compatible"]
RouterSourceAdapter = Literal["generic_openai", "ark_openai", "llama_cpp_server", "vllm_openai"]
RouterSourceStatus = Literal["healthy", "auth_error", "unreachable", "empty", "disabled"]
RouterModelType = Literal["llm", "embedding", "unknown"]
_DEFAULT_SECRETS_DIR = Path("/run/secrets")
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_VERSION_PATH_RE = re.compile(r"/v\d+(?:\.\d+)?$", re.IGNORECASE)
_SCENARIO_TO_MODULE = {
    "chat": "agent_studio",
    "comment": "comment_lab",
    "label": "label_lab",
}


class RouterSourceConfig(BaseModel):
    id: str
    label: str
    base_url: str
    kind: RouterSourceKind = "openai-compatible"
    adapter: RouterSourceAdapter = "generic_openai"
    enabled: bool = True
    enabled_for: list[str] = Field(default_factory=list)
    module_visibility: list[str] = Field(default_factory=list)
    letta_handle_prefix: str = "openai-proxy"
    api_key_env: str = ""
    api_key_secret: str = ""

    @field_validator(
        "id",
        "label",
        "base_url",
        "adapter",
        "letta_handle_prefix",
        "api_key_env",
        "api_key_secret",
    )
    @classmethod
    def _strip_text_fields(cls, value: str) -> str:
        return str(value or "").strip()

    @field_validator("adapter")
    @classmethod
    def _normalize_adapter(cls, value: str) -> str:
        normalized = str(value or "").strip().lower().replace("-", "_")
        if not normalized:
            return "generic_openai"
        if normalized not in {"generic_openai", "ark_openai", "llama_cpp_server", "vllm_openai"}:
            raise ValueError("adapter must be 'generic_openai', 'ark_openai', 'llama_cpp_server', or 'vllm_openai'")
        return normalized

    @field_validator("enabled_for", "module_visibility", mode="before")
    @classmethod
    def _normalize_string_list(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("enabled_for", "module_visibility")
    @classmethod
    def _dedupe_string_list(cls, value: list[str]) -> list[str]:
        deduped: list[str] = []
        for item in value:
            normalized = str(item or "").strip().lower()
            if normalized and normalized not in deduped:
                deduped.append(normalized)
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

    def visible_modules(self) -> tuple[str, ...]:
        raw_tags = self.module_visibility or self.enabled_for
        modules: list[str] = []
        for tag in raw_tags:
            normalized = str(tag or "").strip().lower()
            module = _SCENARIO_TO_MODULE.get(normalized, normalized)
            if module and module not in modules:
                modules.append(module)
        return tuple(modules)

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


class ModelRouterSettings(BaseSettings):
    sources: list[RouterSourceConfig] = Field(default_factory=list)
    sources_file: str = "config/model_router_sources.json"
    model_profiles_file: str = "config/model_router_model_profiles.json"
    api_key: str = ""
    api_key_secret: str = "model-router-api-key"
    cache_ttl_seconds: int = 30
    discovery_timeout_seconds: float = 5.0
    request_timeout_seconds: float = 600.0

    model_config = SettingsConfigDict(
        env_prefix="MODEL_ROUTER_",
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

    @field_validator("sources")
    @classmethod
    def _ensure_unique_source_ids(cls, value: list[RouterSourceConfig]) -> list[RouterSourceConfig]:
        cls._validate_sources(value)
        return value

    @field_validator("sources_file", "model_profiles_file")
    @classmethod
    def _strip_config_file(cls, value: str) -> str:
        return str(value or "").strip()

    @model_validator(mode="after")
    def _load_sources_from_file_when_env_is_empty(self) -> "ModelRouterSettings":
        if self.sources:
            return self
        loaded_items = load_json_config_list(self.sources_file, project_root=_PROJECT_ROOT)
        self.sources = [RouterSourceConfig.model_validate(item) for item in loaded_items]
        self._validate_sources(self.sources)
        return self

    @staticmethod
    def _validate_sources(value: list[RouterSourceConfig]) -> None:
        seen: set[str] = set()
        for source in value:
            if source.id in seen:
                raise ValueError(f"Duplicate model-router source id: {source.id}")
            if not source.visible_modules():
                raise ValueError(f"Source '{source.id}' must include module visibility")
            seen.add(source.id)

    @field_validator("cache_ttl_seconds")
    @classmethod
    def _clamp_cache_ttl(cls, value: int) -> int:
        return max(1, int(value))

    @field_validator("discovery_timeout_seconds")
    @classmethod
    def _clamp_discovery_timeout(cls, value: float) -> float:
        return max(1.0, min(60.0, float(value)))

    @field_validator("request_timeout_seconds")
    @classmethod
    def _clamp_request_timeout(cls, value: float) -> float:
        return max(5.0, min(1800.0, float(value)))

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
        env_value = str(env_map.get("MODEL_ROUTER_API_KEY", "") or "").strip()
        return env_value or self.api_key.strip()


@lru_cache(maxsize=1)
def get_settings() -> ModelRouterSettings:
    return ModelRouterSettings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
