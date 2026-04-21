from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from typing import Any

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from agent_platform_api.main import app


@contextmanager
def _override_env(values: dict[str, str | None]):
    original: dict[str, str | None] = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _expect_platform_gate(response_payload: dict[str, Any]) -> None:
    detail = str(response_payload.get("detail", "") or "")
    if "AGENT_PLATFORM_API_ENABLED" not in detail:
        raise RuntimeError("Platform gate response did not include AGENT_PLATFORM_API_ENABLED detail")


def main() -> None:
    summary: dict[str, Any] = {
        "name": "platform_flag_gate_check",
        "ok": False,
        "steps": {},
        "detail": "",
    }

    with TestClient(app) as http:
        with _override_env(
            {
                "AGENT_PLATFORM_API_ENABLED": "1",
                "AGENT_PLATFORM_STRICT_CAPABILITIES": "0",
            }
        ):
            response = http.get("/api/v1/platform/capabilities")
            response.raise_for_status()
            payload = response.json()
            if not payload.get("enabled"):
                raise RuntimeError("Expected platform capabilities to report enabled=true")
            if payload.get("strict_mode"):
                raise RuntimeError("Expected strict_mode=false under baseline env")
            summary["steps"]["baseline_capabilities"] = {
                "ok": True,
                "payload": payload,
            }

        with _override_env(
            {
                "AGENT_PLATFORM_API_ENABLED": "0",
                "AGENT_PLATFORM_STRICT_CAPABILITIES": "0",
            }
        ):
            options_response = http.get("/api/v1/options")
            if options_response.status_code != 503:
                raise RuntimeError("Expected /api/v1/options to be blocked when platform API is disabled")
            _expect_platform_gate(options_response.json())

            tools_response = http.get("/api/v1/platform/tools")
            if tools_response.status_code != 503:
                raise RuntimeError("Expected /api/v1/platform/tools to be blocked when platform API is disabled")
            _expect_platform_gate(tools_response.json())

            capabilities_response = http.get("/api/v1/platform/capabilities")
            capabilities_response.raise_for_status()
            capabilities_payload = capabilities_response.json()
            if capabilities_payload.get("enabled"):
                raise RuntimeError("Expected /api/v1/platform/capabilities to report enabled=false when disabled")

            summary["steps"]["platform_disabled_gate"] = {
                "ok": True,
                "status_code": options_response.status_code,
            }

        with _override_env(
            {
                "AGENT_PLATFORM_API_ENABLED": "1",
                "AGENT_PLATFORM_STRICT_CAPABILITIES": "1",
            }
        ):
            response = http.get("/api/v1/platform/capabilities")
            response.raise_for_status()
            payload = response.json()
            if not payload.get("strict_mode"):
                raise RuntimeError("Expected strict_mode=true when AGENT_PLATFORM_STRICT_CAPABILITIES=1")
            summary["steps"]["strict_mode_flag"] = {
                "ok": True,
            }

        with _override_env(
            {
                "AGENT_PLATFORM_API_ENABLED": "1",
                "AGENT_PLATFORM_STRICT_CAPABILITIES": "0",
            }
        ):
            response = http.get("/api/v1/options")
            response.raise_for_status()
            payload = response.json()
            if not payload.get("models"):
                raise RuntimeError("Expected options payload to include models when platform API is enabled")
            summary["steps"]["platform_reenabled"] = {
                "ok": True,
            }

    summary["ok"] = True
    summary["detail"] = "Platform API gate behavior checks passed"
    print(_as_json(summary))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[FAIL] platform_flag_gate_check: {exc}")
        raise

