# Tests Layout

This directory now keeps only two maintained test layers:

- `tests/test_*.py`: pytest unit and API coverage
- `tests/checks/`: the two live stack checks used by Test Center

Supporting files:

- `tests/shared/config_defaults.py`: shared base URLs and default handles for the live checks
- `tests/outputs/platform_orchestrator/`: transient runtime logs written by orchestrated Test Center runs
- Chat/model behavior evals live under `evals/`, for example `evals/chat_memory_eval/`

## Maintained Entry Points

- `uv run python -m pytest`
- `uv run python evals/chat_memory_eval/run.py --config evals/chat_memory_eval/config.toml --rounds 1`
- `uv run python tests/checks/platform_api_e2e_check.py`
- `uv run python tests/checks/ade_mvp_smoke_e2e_check.py`

If `agent_platform_api` routes in your running container lag behind source changes, point the live checks at a source-backed API server:

```bash
$env:AGENT_PLATFORM_API_BASE_URL="http://127.0.0.1:8285"
uv run python tests/checks/platform_api_e2e_check.py
uv run python tests/checks/ade_mvp_smoke_e2e_check.py
```
