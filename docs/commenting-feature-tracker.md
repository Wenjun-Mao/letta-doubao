# Commenting Feature Tracker

This document tracks implementation progress for the stateless commenting capability.

## Scope

- Build a stateless comment generation path for scenario `comment`.
- Keep commenting separated from Letta stateful chat workflows.
- Use OpenAI-compatible provider endpoints for portability.
- Provide a dedicated frontend testing surface in ADE.

## Architecture Decisions

- Commenting uses `POST /api/v1/commenting/generate`.
- Commenting uses direct provider calls via `utils/commenting_service.py`.
- Commenting does not require Letta memory or embeddings.
- Provider interface remains OpenAI-compatible `chat/completions` for cross-provider flexibility.

## Progress Checklist

### Backend API and Contracts

- [x] Add scenario-aware prompt/persona selection (`chat` vs `comment`).
- [x] Add `CommentingGenerateRequest` and `ApiCommentingGenerateResponse` contracts.
- [x] Add `POST /api/v1/commenting/generate` endpoint with scenario guards.
- [x] Validate prompt/persona keys are comment-only (`comment_*`).
- [x] Add model selection with allowlist validation.

### Stateless Provider Layer

- [x] Add `CommentingService` with retry logic (`tenacity`).
- [x] Add timeout and provider metadata controls.
- [x] Normalize OpenAI-compatible response content payloads.
- [x] Confirm provider endpoint wiring in all target environments.
- [x] Add reasoning-compatible fallback path when provider returns empty assistant `content`.
- [ ] Add explicit tests covering model-handle prefix normalization.

### Configuration and Runtime

- [x] Add dedicated commenting env controls (`AGENT_PLATFORM_COMMENTING_*`).
- [x] Default commenting model target to `qwen3.5-27b`.
- [x] Validate connectivity in local LM Studio runtime.
- [ ] Validate fallback behavior when commenting env vars are absent.

### Frontend ADE

- [x] Decide UI direction: isolate commenting from Agent Studio.
- [x] Create dedicated route: `frontend-ade/app/comment-lab`.
- [x] Add API client call for comment generation.
- [x] Add model/prompt/persona selectors and input/output panel.
- [ ] Add richer UX polish (presets, copy-to-clipboard, history).
- [x] Add dashboard/module docs references for discoverability.

### Verification

- [x] Run backend check with LM Studio reachable.
- [x] Run `npm --prefix frontend-ade run build` after UI changes.
- [ ] Add/extend E2E checks for successful comment generation.

## Open Questions

- Should we keep optional support for LM Studio native REST endpoints in the future as a feature flag, while keeping OpenAI-compatible as default?
- Do we want comment generation history persisted in ADE, or stay fully transient?
- Should we add async job mode or frontend progress UX for long-running local reasoning generations (60-230s observed on `qwen3.5-27b`)?

## Current Risks

- With local reasoning-enabled `qwen3.5-27b`, generation latency can be high and variable.
- During container restarts or heavy local load, occasional transient connection resets can occur; retrying the same request typically succeeds.

## Change Log

- 2026-04-19: Tracker initialized and aligned with current implementation status.
- 2026-04-19: Added Comment Lab route, navigation wiring, and commenting provider env defaults. Frontend build passed; backend runtime verification is pending LM Studio response behavior with selected Qwen preset.
- 2026-04-19: Closed the original connection-refused gap by wiring commenting env vars into `dev_ui` container runtime; current blocker is model output behavior/timeouts (reasoning-only responses) rather than endpoint reachability.
- 2026-04-19: Implemented reasoning-compatible generation hardening in `CommentingService` (multi-attempt payload strategy, publishable-output checks, and fallback extraction), and validated `/api/v1/commenting/generate` success against `qwen3.5-27b` with reasoning enabled.
