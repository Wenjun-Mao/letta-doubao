# Agent Platform ADE Milestone Tracker

Updated: 2026-04-13

## Milestone Objective

Deliver a production-ready Agent Platform backbone for ADE, retire the legacy in-package frontend, and prepare OpenAPI-driven self-hosted docs.

## Locked Decisions

- API name remains Agent Platform API.
- Keep the backend API surface stable while ADE becomes the primary UI.
- Build new ADE frontend as a separate Next.js + TypeScript app.
- Tool discovery is included in ADE MVP.
- MVP auth posture is internal network boundary only (no new auth layer in MVP).
- Cutover gate is backend E2E green plus ADE smoke suite green.
- Self-hosted API docs are rendered in ADE with Scalar.
- API reference source is a committed OpenAPI artifact synchronized into frontend static assets.

## Scope Checklist

### Backend Foundation

- [x] Capability baseline and strict capability guard.
- [x] Shared backend domain layer for runtime/control operations.
- [x] Agent Platform runtime and control endpoints.
- [x] Orchestrated test-run endpoints.
- [x] Platform API E2E check.
- [x] Versioned route cutover completion for all targeted endpoints.
- [x] Platform-only feature-flag behavior finalized.

### ADE Support APIs

- [x] Tool catalog discovery endpoint (MVP).
- [x] Prompt and persona metadata endpoint (MVP).
- [x] Test-run artifact listing and artifact content endpoints.
- [x] Tool test invocation endpoint (phase-2).
- [x] Prompt/persona revision history endpoint (phase-2).

### Frontend

- [x] Separate Next.js + TypeScript ADE app scaffold.
- [x] Agent Studio MVP.
- [x] Prompt and Persona Lab MVP.
- [x] Toolbench MVP (discovery + attach/detach).
- [x] Test Center MVP.
- [x] API Docs entry in ADE UI.

### Docs and OpenAPI

- [x] FastAPI metadata and endpoint docs quality pass.
- [x] Deterministic OpenAPI export workflow.
- [x] Committed canonical OpenAPI artifact.
- [x] Self-hosted API docs route in ADE.
- [x] CI checks for OpenAPI validity and drift.

### Verification and Rollout

- [x] Full backend Docker E2E baseline is green in latest cycle.
- [x] ADE smoke E2E suite implemented and green.
- [x] Dual-run acceptance gate passed.

## Current Implementation Delta (This Pass)

- Added tool discovery endpoint: GET /api/v1/platform/tools.
- Added tool test invocation endpoint: POST /api/v1/platform/tools/test-invoke.
- Added prompt/persona metadata endpoint: GET /api/v1/platform/metadata/prompts-personas.
- Added prompt/persona revision history endpoint: GET /api/v1/platform/metadata/prompts-personas/revisions.
- Added run artifact endpoints:
  - GET /api/v1/platform/test-runs/{run_id}/artifacts
  - GET /api/v1/platform/test-runs/{run_id}/artifacts/{artifact_id}
- Added feature-flag gating for platform routes.
- Unified runtime chat through AgentPlatformService shared messaging path.
- Added deterministic OpenAPI export script and committed OpenAPI artifact.
- Added self-hosted API docs pipeline and overview pages in docs.
- Added OpenAPI/docs CI validation workflow.
- Added separate Next.js ADE frontend scaffold and compose profile service (`ade_frontend`).
- Implemented functional ADE MVP pages for Agent Studio, Prompt and Persona Lab, Toolbench, Test Center, and live dashboard status.
- Added frontend build validation (`npm run build`) to implementation verification.
- Added ADE MVP smoke E2E check script (`tests/checks/ade_mvp_smoke_e2e_check.py`).
- Added platform flag gate check script (`tests/checks/platform_flag_gate_check.py`).
- Added combined dual-run cutover gate (`tests/checks/platform_dual_run_gate.py`).
- Extended orchestrator/Test Center run types to include ADE smoke, platform-flag gate, and dual-run gate checks.
- Consolidated Prompt/Persona Lab and Toolbench into Agent Studio wrappers with deep-link redirects.
- Added Agent Studio phase-2 UX: compact mode, execution trace filtering, tool probe UI, and prompt/persona revision timeline panel.
- Extended platform API E2E check to validate phase-2 tool probe and revision history endpoints.

## Feature Flags

- AGENT_PLATFORM_API_ENABLED (default: 1)
- AGENT_PLATFORM_STRICT_CAPABILITIES (default: off)

## Immediate Next Tasks

1. Add richer ADE artifact browsing (download/filters) as post-MVP polish.
2. Consider revision timeline diff drill-down (full before/after modal).
3. Add scripted browser-level regression for Agent Studio deep-link wrappers.
