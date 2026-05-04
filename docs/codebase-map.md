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

- `model_router/`: the first-party OpenAI-compatible router. It owns upstream source discovery, source health, Ark allowlist filtering, model profiles, model id routing, and module visibility.
- `agent_platform_api/`: the ADE backend API. It owns routes, Pydantic response/request models, feature services, registries, Letta orchestration, and router catalog consumption.
- `agent_platform_api/services/`: feature services for Agent Studio/Letta operations, Comment Lab, and Label Lab.
- `agent_platform_api/registries/`: registries for file-backed prompts/schemas/tools, SQLite-backed personas, and agent lifecycle metadata.
- `agent_platform_api/options/`: router-backed model catalog enrichment, UI option building, model selection, and runtime defaults.
- `agent_platform_api/clients/`: outbound service clients, currently the model router client.
- `agent_platform_api/llm/`: LLM tooling that belongs to ADE, such as provider probe/report generation.
- `agent_platform_api/letta/`: Letta SDK convenience helpers and generated Letta tool constants.
- `agent_platform_api/testing/`: Test Center orchestration.
- `ade_core/`: small shared helpers used by more than one backend service. Keep this intentionally tiny.
- `evals/`: self-contained evaluation/probe workflows with colocated runner, config, docs, inputs, and ignored outputs.

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
- `config/model_router_model_profiles.json`: router model intelligence such as recommended sampling defaults, `top_k` support, and Agent Studio compatibility flags.
- `prompts/system_prompts/`: prompt templates grouped by scenario.
- `agent_platform_api/seed_data/personas.jsonl`: checked-in seed personas loaded into SQLite on first startup.
- `data/personas/personas.sqlite3`: tracked SQLite persona library; SQLite sidecars remain ignored.
- `schemas/label/`: Label Lab JSON schema center storage.
- `tools/custom/`: file-backed custom tool source storage.
- `agent_platform_api/catalog_data/`: checked-in model probe reports and allowlists.
- `evals/*/outputs/`: local generated eval/probe outputs, ignored by git.
- `data/`: runtime data root. Keep committed files here minimal; generated service state should normally stay untracked.

## Where Do I Change X?

| Task | Start Here |
| --- | --- |
| Add or disable an LLM backend | `config/model_router_sources.json` |
| Add or tune model-specific defaults | `config/model_router_model_profiles.json` |
| Change model discovery/routing behavior | `model_router/catalog.py` and `model_router/app.py` |
| Change Comment Lab generation | `agent_platform_api/services/commenting.py` and `agent_platform_api/routers/commenting.py` |
| Change Label Lab generation | `agent_platform_api/services/labeling.py`, `agent_platform_api/services/labeling_helpers.py`, and `agent_platform_api/routers/labeling.py` |
| Change options returned to the UI | `agent_platform_api/options/` |
| Change Prompt Center prompt behavior | `agent_platform_api/registries/prompt_persona_store/` and `agent_platform_api/routers/prompt_center.py` |
| Change Prompt Center persona storage | `agent_platform_api/registries/persona_sqlite.py` |
| Import/export the persona library | `uv run python scripts/persona_library.py --help` |
| Change Schema Center behavior | `agent_platform_api/registries/label_schema.py` and `agent_platform_api/routers/schema_center.py` |
| Change Agent Studio / Letta orchestration | `agent_platform_api/services/agent_platform.py` and `agent_platform_api/routers/agents.py` |
| Run Comment Persona Eval | `uv run python evals/comment_persona_eval/run.py --config evals/comment_persona_eval/config.toml` |
| Change frontend page behavior | the matching `frontend-ade/app/<module>/page.tsx` file |
| Update OpenAPI artifacts | `uv run python scripts/export_openapi.py` |
| Re-probe Ark usable models | `uv run python evals/provider_model_probe/run.py --source-id ark --mode chat-probe --write` |
| Collect runtime diagnostics | `scripts/collect_diagnostics.sh` |
| Update repo conventions | `docs/development-conventions.md` |

## Guardrails

- Do not add new `utils/` imports. Shared backend helpers belong in `ade_core/`; Agent Platform code belongs under `agent_platform_api/`.
- Do not add a second Agent Platform model-source config. The router source file is the source of truth.
- Do not reintroduce Agent Platform direct-provider traversal for normal model discovery or generation.
- Keep generated build/cache/runtime artifacts out of git.
- Keep multi-file workflows colocated under `evals/` instead of splitting runner/config/output across root folders.
- If a historical note becomes misleading, delete it or move the important fact into this map or `MANUAL.md`.
