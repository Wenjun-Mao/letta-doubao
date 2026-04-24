from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_platform_api.settings import clear_settings_cache


@pytest.fixture(autouse=True)
def _disable_live_router_by_default(monkeypatch):
    monkeypatch.setenv("AGENT_PLATFORM_MODEL_ROUTER_BASE_URL", "")
    clear_settings_cache()
    yield
    clear_settings_cache()
