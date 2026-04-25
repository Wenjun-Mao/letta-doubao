from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


ProbeResultStatus = Literal[
    "ok",
    "skipped_non_llm",
    "bad_request",
    "auth_error",
    "not_found",
    "rate_limited",
    "server_error",
    "timeout",
    "invalid_json",
    "invalid_payload",
    "network_error",
]


class ProbeCatalogAuthError(RuntimeError):
    def __init__(self, status_code: int, body: str = ""):
        self.status_code = int(status_code)
        self.body = str(body or "")
        super().__init__(f"Authentication failed ({self.status_code})")


class RetryableProbeError(RuntimeError):
    def __init__(self, status_code: int, body: str = ""):
        self.status_code = int(status_code)
        self.body = str(body or "")
        super().__init__(f"Temporary provider failure ({self.status_code})")


@dataclass(frozen=True)
class ProbedModelResult:
    provider_model_id: str
    model_type: str
    status: ProbeResultStatus
    usable: bool
    http_status: int | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_model_id": self.provider_model_id,
            "model_type": self.model_type,
            "status": self.status,
            "usable": self.usable,
            "http_status": self.http_status,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class SourceProbeReport:
    source_id: str
    checked_at: str
    probe_mode: str
    raw_model_count: int
    usable_models: tuple[str, ...]
    results: tuple[ProbedModelResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "checked_at": self.checked_at,
            "probe_mode": self.probe_mode,
            "raw_model_count": self.raw_model_count,
            "usable_models": list(self.usable_models),
            "results": [result.to_dict() for result in self.results],
        }

