# Tests Layout

This directory uses a role-based structure:

- checks/: focused diagnostics and sanity checks
- runners/: config-driven or scenario-driven test runners
- shared/: constants shared by checks and runners
- configs/: test configurations and reusable conversation fixtures
- outputs/: generated artifacts from test runs

## Main Entry Points

- tests/runners/persona_guardrail_runner.py
  - Runs suite JSON configs from tests/configs/suites/
  - Writes per-run artifacts to tests/outputs/persona_guardrail/
  - Appends run index to tests/outputs/persona_guardrail/run_index.{csv,jsonl}
- tests/runners/memory_update_runner.py
  - Runs fresh-agent rounds to validate memory update reliability
  - Validates expected-name persistence and memory mutation
  - Writes per-run artifacts to tests/outputs/memory_update/
  - Appends run index to tests/outputs/memory_update/run_index.{csv,jsonl}
- tests/checks/provider_embedding_matrix_check.py
  - Smoke checks Agent Platform API options/create and embedding combos
- tests/checks/prompt_strategy_check.py
  - Compares prompt strategy behavior on memory updates
- tests/checks/agent_bootstrap_check.py
  - Verifies bootstrap memory block descriptions and defaults
- tests/checks/platform_api_e2e_check.py
  - Validates Agent Platform runtime/control endpoints and orchestrator flow
- tests/checks/ade_mvp_smoke_e2e_check.py
  - Covers ADE MVP user journeys across Dashboard, Agent Studio, Prompt and Persona Lab, Toolbench, and Test Center
- tests/checks/platform_flag_gate_check.py
  - Verifies platform API gate behavior and strict-capability flag state
- tests/checks/platform_dual_run_gate.py
  - Runs backend platform API E2E plus ADE smoke suite as one cutover gate

## Typical Commands

```bash
uv run tests/runners/persona_guardrail_runner.py --config tests/configs/suites --model lmstudio_openai/gemma-4-31b-it --embedding letta/letta-free
uv run tests/runners/memory_update_runner.py --rounds 10 --model lmstudio_openai/gemma-4-31b-it --embedding letta/letta-free
uv run tests/checks/provider_embedding_matrix_check.py
uv run tests/checks/prompt_strategy_check.py
uv run tests/checks/agent_bootstrap_check.py
uv run tests/checks/platform_api_e2e_check.py
uv run tests/checks/ade_mvp_smoke_e2e_check.py
uv run tests/checks/platform_flag_gate_check.py
uv run tests/checks/platform_dual_run_gate.py
```

If `agent_platform_api` routes in your running container lag behind source changes, point checks at a source-backed API server:

```bash
$env:AGENT_PLATFORM_API_BASE_URL="http://127.0.0.1:8285"
uv run tests/checks/platform_dual_run_gate.py
```

Examples:
```bash
uv run python tests/runners/persona_guardrail_runner.py --config tests/configs/suites/lmstudio_chat_v20260418.json --model lmstudio_openai/gemma-4-31b-it --embedding letta/letta-free

uv run python tests/runners/memory_update_runner.py --rounds 10 --model lmstudio_openai/gemma-4-31b-it --embedding letta/letta-free --turn "你好，我叫张伟"

uv run python tests/runners/memory_update_runner.py --rounds 10 --model lmstudio_openai/gemma-4-31b-it --embedding letta/letta-free --turn "你好，我叫张伟" --turn "我喜欢狗狗" --turn "你记得我的名字吗？"

uv run python tests/runners/memory_update_runner.py --rounds 10 --model openai-proxy/doubao-seed-1-8-251228 --embedding letta/letta-free --turn "你好，我叫张伟"
```
