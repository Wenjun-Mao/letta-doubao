from __future__ import annotations

from typing import cast

from agent_platform_api.dependencies import commenting_service, labeling_service
from agent_platform_api.models.agents import ApiAgentStudioRuntimeDefaultsResponse
from agent_platform_api.models.commenting import ApiCommentingRuntimeDefaultsResponse
from agent_platform_api.models.common import CommentingTaskShape
from agent_platform_api.models.labeling import ApiLabelingRuntimeDefaultsResponse
from agent_platform_api.settings import get_settings


def commenting_runtime_defaults() -> ApiCommentingRuntimeDefaultsResponse:
    defaults = commenting_service.runtime_defaults()
    task_shape = str(defaults.get("task_shape", "classic") or "classic").strip().lower()
    if task_shape not in {"classic", "all_in_system", "structured_output"}:
        task_shape = "classic"
    resolved_task_shape = cast(CommentingTaskShape, task_shape)
    return ApiCommentingRuntimeDefaultsResponse(
        max_tokens=int(defaults.get("max_tokens", 0)),
        timeout_seconds=float(defaults.get("timeout_seconds", 60.0)),
        task_shape=resolved_task_shape,
        cache_prompt=bool(defaults.get("cache_prompt", False)),
        temperature=float(defaults.get("temperature", 0.6)),
        top_p=float(defaults.get("top_p", 1.0)),
    )


def labeling_runtime_defaults() -> ApiLabelingRuntimeDefaultsResponse:
    defaults = labeling_service.runtime_defaults()
    return ApiLabelingRuntimeDefaultsResponse(
        max_tokens=int(defaults.get("max_tokens", 0)),
        timeout_seconds=float(defaults.get("timeout_seconds", 60.0)),
        repair_retry_count=int(defaults.get("repair_retry_count", 1)),
        temperature=float(defaults.get("temperature", 0.0)),
        top_p=float(defaults.get("top_p", 1.0)),
    )


def agent_studio_runtime_defaults() -> ApiAgentStudioRuntimeDefaultsResponse:
    settings = get_settings()
    return ApiAgentStudioRuntimeDefaultsResponse(
        temperature=settings.agent_studio_temperature,
        top_p=settings.agent_studio_top_p,
    )
