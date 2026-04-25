# Codebase Map

This is the fast orientation guide for Letta Open ADE. If you are wondering "where is this wired?", start here.

## Runtime Flow

```text
Browser / Bruno / tests
  -> frontend-ade or direct HTTP
  -> agent_platform_api
  -> model_router
  -> upstream OpenAI-compatible providers

Agent Studio also creates persistent agents through Letta:

agent_platform_api -> Letta server -> model_router -> upstream providers
```

The router is the canonical LLM access layer. `agent_platform_api` should not traverse provider base URLs directly for normal model discovery or generation.

## Backend Packages

- `model_router/`: the first-party OpenAI-compatible router. It owns upstream source discovery, source health, Ark allowlist filtering, model id routing, and module visibility.
- `agent_platform_api/`: the ADE backend API. It owns routes, Pydantic response/request models, feature services, registries, Letta orchestration, and router catalog consumption.
- `agent_platform_api/services/`: feature services for Agent Studio/Letta operations, Comment Lab, and Label Lab.
- `agent_platform_api/registries/`: file-backed registries for prompts/personas, label schemas, custom tools, and agent lifecycle metadata.
- `agent_platform_api/clients/`: outbound service clients, currently the model router client.
- `agent_platform_api/llm/`: LLM tooling that belongs to ADE, such as provider probe/report generation.
- `agent_platform_api/letta/`: Letta SDK convenience helpers and generated Letta tool constants.
- `agent_platform_api/testing/`: Test Center orchestration.
- `ade_core/`: small shared helpers used by more than one backend service. Keep this intentionally tiny.

## Frontend Modules

- `frontend-ade/app/agent-studio/`: persistent Letta agent creation and chat.
- `frontend-ade/app/comment-lab/`: stateless comment generation.
- `frontend-ade/app/label-lab/`: stateless structured entity extraction.
- `frontend-ade/app/prompt-center/`: prompt/persona editing.
- `frontend-ade/app/schema-center/`: label schema editing.
- `frontend-ade/app/tool-center/` and `frontend-ade/app/toolbench/`: custom tool management and runtime tool testing.
- `frontend-ade/app/test-center/`: maintained live checks.
- `frontend-ade/lib/api.ts`: frontend API client and shared UI-facing types.

## Persistent Content

- `config/model_router_sources.json`: the single model-source config file. Edit this to enable, disable, reorder, or retag LLM upstreams.
- `prompts/system_prompts/`: prompt templates grouped by scenario.
- `prompts/persona/`: persona templates grouped by scenario.
- `schemas/label/`: Label Lab JSON schema center storage.
- `tools/custom/`: file-backed custom tool source storage.
- `agent_platform_api/catalog_data/`: checked-in model probe reports and allowlists.
- `data/`: runtime data root. Keep committed files here minimal; generated service state should normally stay untracked.

## Where Do I Change X?

| Task | Start Here |
| --- | --- |
| Add or disable an LLM backend | `config/model_router_sources.json` |
| Change model discovery/routing behavior | `model_router/catalog.py` and `model_router/app.py` |
| Change Comment Lab generation | `agent_platform_api/services/commenting.py` and `agent_platform_api/routers/commenting.py` |
| Change Label Lab generation | `agent_platform_api/services/labeling.py`, `agent_platform_api/services/labeling_helpers.py`, and `agent_platform_api/routers/labeling.py` |
| Change options returned to the UI | `agent_platform_api/model_options.py` |
| Change Prompt Center behavior | `agent_platform_api/registries/prompt_persona.py` and `agent_platform_api/routers/prompt_center.py` |
| Change Schema Center behavior | `agent_platform_api/registries/label_schema.py` and `agent_platform_api/routers/schema_center.py` |
| Change Agent Studio / Letta orchestration | `agent_platform_api/services/agent_platform.py` and `agent_platform_api/routers/agents.py` |
| Change frontend page behavior | the matching `frontend-ade/app/<module>/page.tsx` file |
| Update OpenAPI artifacts | `uv run python scripts/export_openapi.py` |
| Re-probe Ark usable models | `uv run python scripts/probe_provider_models.py --source-id ark --mode chat-probe --write` |
| Collect runtime diagnostics | `scripts/collect_diagnostics.sh` |

## Guardrails

- Do not add new `utils/` imports. Shared backend helpers belong in `ade_core/`; Agent Platform code belongs under `agent_platform_api/`.
- Do not add a second Agent Platform model-source config. The router source file is the source of truth.
- Do not reintroduce Agent Platform direct-provider traversal for normal model discovery or generation.
- Keep generated build/cache/runtime artifacts out of git.
- If a historical note becomes misleading, delete it or move the important fact into this map or `MANUAL.md`.

