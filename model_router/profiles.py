from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCENARIO_ALIASES = {
    "chat": "agent_studio",
    "comment": "comment_lab",
    "label": "label_lab",
}


class SamplingDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None

    @field_validator("temperature")
    @classmethod
    def _validate_temperature(cls, value: float | None) -> float | None:
        if value is None:
            return None
        resolved = float(value)
        if resolved < 0 or resolved > 2:
            raise ValueError("temperature must be between 0 and 2")
        return resolved

    @field_validator("top_p")
    @classmethod
    def _validate_top_p(cls, value: float | None) -> float | None:
        if value is None:
            return None
        resolved = float(value)
        if resolved <= 0 or resolved > 1:
            raise ValueError("top_p must be > 0 and <= 1")
        return resolved

    @field_validator("top_k")
    @classmethod
    def _validate_top_k(cls, value: int | None) -> int | None:
        if value is None:
            return None
        resolved = int(value)
        if resolved <= 0:
            raise ValueError("top_k must be > 0")
        return resolved

    def merged_with(self, override: "SamplingDefaults | None") -> "SamplingDefaults":
        if override is None:
            return self
        return SamplingDefaults(
            temperature=override.temperature if override.temperature is not None else self.temperature,
            top_p=override.top_p if override.top_p is not None else self.top_p,
            top_k=override.top_k if override.top_k is not None else self.top_k,
        )

    def as_payload(self) -> dict[str, float | int]:
        return self.model_dump(exclude_none=True)


class ModelProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_model: str = ""
    profile_source: str = ""
    supports_top_k: bool = False
    supports_thinking: bool = False
    thinking_default_enabled: bool = False
    agent_studio_candidate: bool = False
    agent_studio_compatible: bool = True
    sampling_defaults: SamplingDefaults = Field(default_factory=SamplingDefaults)
    scenario_sampling_defaults: dict[str, SamplingDefaults] = Field(default_factory=dict)

    @field_validator("base_model", "profile_source")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return str(value or "").strip()

    @field_validator("scenario_sampling_defaults", mode="before")
    @classmethod
    def _normalize_scenario_keys(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        normalized: dict[str, object] = {}
        for raw_key, raw_defaults in value.items():
            scenario = _normalize_scenario_key(raw_key)
            if scenario in normalized:
                raise ValueError(f"Duplicate scenario sampling defaults: {scenario}")
            normalized[scenario] = raw_defaults
        return normalized

    def effective_defaults_for(self, scenario: str) -> SamplingDefaults:
        return self.sampling_defaults.merged_with(
            self.scenario_sampling_defaults.get(_normalize_scenario_key(scenario))
        )

    def scenario_defaults_payload(self) -> dict[str, dict[str, float | int]]:
        return {
            scenario: self.effective_defaults_for(scenario).as_payload()
            for scenario in sorted(self.scenario_sampling_defaults)
        }


def load_model_profiles(
    path: str | Path,
    *,
    project_root: Path = _PROJECT_ROOT,
) -> dict[str, ModelProfile]:
    resolved_path = Path(path)
    if not resolved_path.is_absolute():
        resolved_path = project_root / resolved_path
    if not resolved_path.is_file():
        return {}

    raw_text = resolved_path.read_text(encoding="utf-8")
    raw_payload = json.loads(raw_text, object_pairs_hook=_reject_duplicate_object_keys)
    if not isinstance(raw_payload, dict):
        raise ValueError("Model profile config must be a JSON object keyed by router model id")

    profiles: dict[str, ModelProfile] = {}
    for raw_key, raw_value in raw_payload.items():
        key = str(raw_key or "").strip()
        if not key or "::" not in key:
            raise ValueError(f"Invalid model profile key: {raw_key!r}")
        if key in profiles:
            raise ValueError(f"Duplicate model profile key: {key}")
        profiles[key] = ModelProfile.model_validate(raw_value)
    return profiles


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _normalize_scenario_key(value: object) -> str:
    normalized = str(value or "").strip().lower()
    normalized = _SCENARIO_ALIASES.get(normalized, normalized)
    if not normalized:
        raise ValueError("Scenario sampling default key cannot be empty")
    return normalized
