from __future__ import annotations

import inspect
from typing import Any

from letta_client import Letta
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from agent_platform_api.letta.message_parser import chat

_RETRY_KWARGS = {
    "stop": stop_after_attempt(3),
    "wait": wait_exponential(multiplier=1, min=1, max=8),
    "retry": retry_if_exception_type(Exception),
    "reraise": True,
}

DEFAULT_RUNTIME_TIMEOUT_SECONDS = 180.0
MIN_RUNTIME_TIMEOUT_SECONDS = 5.0
MAX_RUNTIME_TIMEOUT_SECONDS = 600.0
DEFAULT_RUNTIME_RETRY_COUNT = 0
MAX_RUNTIME_RETRY_COUNT = 5


class AgentPlatformService:
    """Shared backend service for runtime and control-plane agent operations."""

    def __init__(self, client: Letta):
        self._client = client

    def _message_create_params(self, client: Letta | None = None) -> set[str]:
        target_client = client or self._client
        return set(inspect.signature(target_client.agents.messages.create).parameters.keys())

    @staticmethod
    def _clamp_timeout_seconds(value: float | None) -> float:
        if value is None:
            return DEFAULT_RUNTIME_TIMEOUT_SECONDS
        return max(MIN_RUNTIME_TIMEOUT_SECONDS, min(MAX_RUNTIME_TIMEOUT_SECONDS, float(value)))

    @staticmethod
    def _clamp_retry_count(value: int | None) -> int:
        if value is None:
            return DEFAULT_RUNTIME_RETRY_COUNT
        return max(0, min(MAX_RUNTIME_RETRY_COUNT, int(value)))

    def _runtime_client(self, *, timeout_seconds: float | None, retry_count: int | None) -> Letta:
        return self._client.with_options(
            timeout=self._clamp_timeout_seconds(timeout_seconds),
            max_retries=self._clamp_retry_count(retry_count),
        )

    @staticmethod
    def _serialize_tool(tool: Any) -> dict[str, Any]:
        tags_raw = getattr(tool, "tags", None) or []
        tags = [str(tag) for tag in tags_raw if str(tag).strip()]
        return {
            "id": str(getattr(tool, "id", "") or ""),
            "name": str(getattr(tool, "name", "") or ""),
            "description": str(getattr(tool, "description", "") or ""),
            "tool_type": str(getattr(tool, "tool_type", "") or ""),
            "source_type": str(getattr(tool, "source_type", "") or ""),
            "created_at": str(getattr(tool, "created_at", "") or ""),
            "last_updated_at": str(getattr(tool, "last_updated_at", "") or ""),
            "tags": tags,
            "source_code": str(getattr(tool, "source_code", "") or ""),
            "return_char_limit": getattr(tool, "return_char_limit", None),
            "enable_parallel_execution": bool(getattr(tool, "enable_parallel_execution", False)),
            "default_requires_approval": bool(getattr(tool, "default_requires_approval", False)),
        }

    @staticmethod
    def _is_context_limit_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return "context size has been exceeded" in text or "maximum context length" in text

    @retry(**_RETRY_KWARGS)
    def list_available_tools(self, *, search: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        resolved_limit = max(1, min(int(limit), 500))
        query = (search or "").strip()

        list_kwargs: dict[str, Any] = {
            "limit": resolved_limit,
        }
        if query:
            list_kwargs["search"] = query

        tools = list(self._client.tools.list(**list_kwargs))
        return [self._serialize_tool(tool) for tool in tools]

    @retry(**_RETRY_KWARGS)
    def retrieve_tool(self, *, tool_id: str) -> dict[str, Any]:
        if not str(tool_id or "").strip():
            raise ValueError("tool_id is required")
        tool = self._client.tools.retrieve(tool_id=tool_id)
        return self._serialize_tool(tool)

    @retry(**_RETRY_KWARGS)
    def create_tool(
        self,
        *,
        source_code: str,
        description: str | None = None,
        tags: list[str] | None = None,
        source_type: str | None = "python",
        enable_parallel_execution: bool | None = None,
        default_requires_approval: bool | None = None,
        return_char_limit: int | None = None,
        pip_requirements: list[dict[str, Any]] | None = None,
        npm_requirements: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        text = str(source_code or "").strip()
        if not text:
            raise ValueError("source_code is required")

        create_kwargs: dict[str, Any] = {
            "source_code": source_code,
        }
        if description is not None:
            create_kwargs["description"] = description
        if tags:
            create_kwargs["tags"] = tags
        if source_type:
            create_kwargs["source_type"] = source_type
        if enable_parallel_execution is not None:
            create_kwargs["enable_parallel_execution"] = bool(enable_parallel_execution)
        if default_requires_approval is not None:
            create_kwargs["default_requires_approval"] = bool(default_requires_approval)
        if return_char_limit is not None:
            create_kwargs["return_char_limit"] = int(return_char_limit)
        if pip_requirements:
            create_kwargs["pip_requirements"] = pip_requirements
        if npm_requirements:
            create_kwargs["npm_requirements"] = npm_requirements

        created = self._client.tools.create(**create_kwargs)
        return self._serialize_tool(created)

    @retry(**_RETRY_KWARGS)
    def update_tool(
        self,
        *,
        tool_id: str,
        source_code: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        source_type: str | None = None,
        enable_parallel_execution: bool | None = None,
        default_requires_approval: bool | None = None,
        return_char_limit: int | None = None,
        pip_requirements: list[dict[str, Any]] | None = None,
        npm_requirements: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        resolved_tool_id = str(tool_id or "").strip()
        if not resolved_tool_id:
            raise ValueError("tool_id is required")

        update_kwargs: dict[str, Any] = {}
        if source_code is not None:
            update_kwargs["source_code"] = source_code
        if description is not None:
            update_kwargs["description"] = description
        if tags is not None:
            update_kwargs["tags"] = tags
        if source_type is not None:
            update_kwargs["source_type"] = source_type
        if enable_parallel_execution is not None:
            update_kwargs["enable_parallel_execution"] = bool(enable_parallel_execution)
        if default_requires_approval is not None:
            update_kwargs["default_requires_approval"] = bool(default_requires_approval)
        if return_char_limit is not None:
            update_kwargs["return_char_limit"] = int(return_char_limit)
        if pip_requirements is not None:
            update_kwargs["pip_requirements"] = pip_requirements
        if npm_requirements is not None:
            update_kwargs["npm_requirements"] = npm_requirements

        if not update_kwargs:
            raise ValueError("At least one updatable tool field is required")

        updated = self._client.tools.update(tool_id=resolved_tool_id, **update_kwargs)
        return self._serialize_tool(updated)

    @retry(**_RETRY_KWARGS)
    def delete_tool(self, *, tool_id: str) -> None:
        resolved_tool_id = str(tool_id or "").strip()
        if not resolved_tool_id:
            raise ValueError("tool_id is required")
        self._client.tools.delete(tool_id=resolved_tool_id)

    def capabilities(self) -> dict[str, Any]:
        message_params = self._message_create_params()
        update_params = set(inspect.signature(self._client.agents.update).parameters.keys())
        block_update_params = set(inspect.signature(self._client.agents.blocks.update).parameters.keys())

        supports_override_model = "override_model" in message_params
        supports_override_system = "override_system" in message_params
        supports_extra_body = "extra_body" in message_params

        return {
            "runtime": {
                "per_request_model_override": supports_override_model,
                "per_request_model_override_via_extra_body": (not supports_override_model) and supports_extra_body,
                "per_request_system_override": supports_override_system,
                "per_request_system_override_via_extra_body": (not supports_override_system) and supports_extra_body,
            },
            "control": {
                "update_system_prompt": "system" in update_params,
                "update_agent_model": "model" in update_params,
                "update_core_memory_block": "value" in block_update_params,
                "attach_tool": hasattr(self._client.agents.tools, "attach"),
                "detach_tool": hasattr(self._client.agents.tools, "detach"),
            },
            "sdk": {
                "messages_create_params": sorted(message_params),
                "agents_update_params": sorted(update_params),
                "blocks_update_params": sorted(block_update_params),
            },
        }

    def send_runtime_message(
        self,
        *,
        agent_id: str,
        message: str,
        override_model: str | None = None,
        override_system: str | None = None,
        timeout_seconds: float | None = None,
        retry_count: int | None = None,
    ) -> dict[str, Any]:
        runtime_client = self._runtime_client(timeout_seconds=timeout_seconds, retry_count=retry_count)
        message_params = self._message_create_params(runtime_client)
        payload: dict[str, Any] = {
            "input": message,
        }
        extra_body: dict[str, Any] = {}

        if override_model:
            if "override_model" in message_params:
                payload["override_model"] = override_model
            elif "extra_body" in message_params:
                extra_body["override_model"] = override_model
            else:
                raise ValueError("The active Letta SDK does not support request-time model override.")

        if override_system:
            if "override_system" in message_params:
                payload["override_system"] = override_system
            elif "extra_body" in message_params:
                # Older SDKs can still forward alias field `system` through extra_body.
                extra_body["system"] = override_system
            else:
                raise ValueError("The active Letta SDK does not support request-time system override.")

        if extra_body:
            payload["extra_body"] = extra_body

        result = chat(client=runtime_client, agent_id=agent_id, **payload)
        result.pop("raw_messages", None)
        return {
            "agent_id": agent_id,
            "override_model": override_model,
            "override_system": override_system,
            "result": result,
        }

    def send_chat_message(
        self,
        *,
        agent_id: str,
        message: str,
        datetime_system_hint: str | None = None,
        timeout_seconds: float | None = None,
        retry_count: int | None = None,
    ) -> dict[str, Any]:
        runtime_client = self._runtime_client(timeout_seconds=timeout_seconds, retry_count=retry_count)
        if datetime_system_hint:
            try:
                result = chat(
                    client=runtime_client,
                    agent_id=agent_id,
                    messages=[
                        {"role": "system", "content": datetime_system_hint},
                        {"role": "user", "content": message},
                    ],
                )
            except Exception as exc:
                if not self._is_context_limit_error(exc):
                    raise
                result = chat(
                    client=runtime_client,
                    agent_id=agent_id,
                    input=message,
                )
        else:
            result = chat(
                client=runtime_client,
                agent_id=agent_id,
                input=message,
            )

        result.pop("raw_messages", None)
        return result

    @retry(**_RETRY_KWARGS)
    def delete_agent(self, *, agent_id: str) -> None:
        resolved_agent_id = str(agent_id or "").strip()
        if not resolved_agent_id:
            raise ValueError("agent_id is required")
        self._client.agents.delete(agent_id=resolved_agent_id)

    @retry(**_RETRY_KWARGS)
    def update_system_prompt(self, *, agent_id: str, system_prompt: str) -> dict[str, Any]:
        before = self._client.agents.retrieve(agent_id=agent_id)
        updated = self._client.agents.update(agent_id=agent_id, system=system_prompt)

        return {
            "agent_id": agent_id,
            "model": str(getattr(updated, "model", "") or getattr(before, "model", "")),
            "system_before": str(getattr(before, "system", "")),
            "system_after": str(getattr(updated, "system", "")),
        }

    @retry(**_RETRY_KWARGS)
    def update_agent_model(self, *, agent_id: str, model_handle: str) -> dict[str, Any]:
        before = self._client.agents.retrieve(agent_id=agent_id)
        updated = self._client.agents.update(agent_id=agent_id, model=model_handle)

        return {
            "agent_id": agent_id,
            "model_before": str(getattr(before, "model", "")),
            "model_after": str(getattr(updated, "model", "")),
            "system": str(getattr(updated, "system", "")),
        }

    @retry(**_RETRY_KWARGS)
    def update_core_memory_block(self, *, agent_id: str, block_label: str, value: str) -> dict[str, Any]:
        before = self._client.agents.blocks.retrieve(agent_id=agent_id, block_label=block_label)
        updated = self._client.agents.blocks.update(agent_id=agent_id, block_label=block_label, value=value)

        return {
            "agent_id": agent_id,
            "block_label": block_label,
            "value_before": str(getattr(before, "value", "")),
            "value_after": str(getattr(updated, "value", "")),
            "description": str(getattr(updated, "description", "") or ""),
            "limit": getattr(updated, "limit", None),
        }

    @retry(**_RETRY_KWARGS)
    def _list_tool_ids(self, agent_id: str) -> list[str]:
        tools = list(self._client.agents.tools.list(agent_id=agent_id))
        return [
            str(getattr(tool, "id", ""))
            for tool in tools
            if str(getattr(tool, "id", "")).strip()
        ]

    @retry(**_RETRY_KWARGS)
    def attach_tool(self, *, agent_id: str, tool_id: str) -> dict[str, Any]:
        before_tool_ids = self._list_tool_ids(agent_id)
        self._client.agents.tools.attach(agent_id=agent_id, tool_id=tool_id)
        after_tool_ids = self._list_tool_ids(agent_id)

        return {
            "agent_id": agent_id,
            "tool_id": tool_id,
            "tool_was_attached": tool_id in before_tool_ids,
            "tool_is_attached": tool_id in after_tool_ids,
            "tool_count_before": len(before_tool_ids),
            "tool_count_after": len(after_tool_ids),
        }

    @retry(**_RETRY_KWARGS)
    def detach_tool(self, *, agent_id: str, tool_id: str) -> dict[str, Any]:
        before_tool_ids = self._list_tool_ids(agent_id)
        self._client.agents.tools.detach(agent_id=agent_id, tool_id=tool_id)
        after_tool_ids = self._list_tool_ids(agent_id)

        return {
            "agent_id": agent_id,
            "tool_id": tool_id,
            "tool_was_attached": tool_id in before_tool_ids,
            "tool_is_attached": tool_id in after_tool_ids,
            "tool_count_before": len(before_tool_ids),
            "tool_count_after": len(after_tool_ids),
        }
