from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


CommentingTaskShapeSetting = Literal["classic", "all_in_system", "structured_output"]
_DEFAULT_SECRETS_DIR = Path("/run/secrets")
_VERSION_PATH_RE = re.compile(r"/v\d+(?:\.\d+)?$", re.IGNORECASE)


class AgentPlatformSettings(BaseSettings):
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
