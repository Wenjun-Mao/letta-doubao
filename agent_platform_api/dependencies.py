from __future__ import annotations

import os
from pathlib import Path

from letta_client import Letta

from agent_platform_api.clients.model_router import ModelRouterClient
from agent_platform_api.registries.agent_lifecycle import AgentLifecycleRegistry
from agent_platform_api.registries.custom_tool import CustomToolRegistry
from agent_platform_api.registries.label_schema import LabelSchemaRegistry
from agent_platform_api.registries.prompt_persona_store import PromptPersonaRegistry
from agent_platform_api.services.agent_platform import AgentPlatformService
from agent_platform_api.services.commenting import CommentingService
from agent_platform_api.services.labeling import LabelingService
from agent_platform_api.testing.orchestrator import PlatformTestOrchestrator

APP_VERSION = os.getenv("AGENT_PLATFORM_API_VERSION", "0.2.0")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
REVISION_LOG_DIR = PROJECT_ROOT / "diagnostics"
REVISION_LOG_FILE = REVISION_LOG_DIR / "prompt_persona_revisions.jsonl"

client = Letta(base_url=os.getenv("LETTA_BASE_URL", "http://localhost:8283"))
agent_platform = AgentPlatformService(client)
test_orchestrator = PlatformTestOrchestrator(project_root=PROJECT_ROOT)
prompt_persona_registry = PromptPersonaRegistry(PROJECT_ROOT)
label_schema_registry = LabelSchemaRegistry(PROJECT_ROOT)
custom_tool_registry = CustomToolRegistry(PROJECT_ROOT)
agent_lifecycle_registry = AgentLifecycleRegistry(PROJECT_ROOT)
model_router_client = ModelRouterClient()
commenting_service = CommentingService()
labeling_service = LabelingService()
