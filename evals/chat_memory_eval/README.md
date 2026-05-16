# Chat Memory Eval

Runs fresh Agent Studio agents through a fixed multi-turn conversation and checks whether the selected model stays in persona while updating user memory.

## Quick Commands

Smoke one round:

```bash
uv run python evals/chat_memory_eval/run.py --config evals/chat_memory_eval/config.toml --rounds 1
```

Run the default matrix:

```bash
uv run python evals/chat_memory_eval/run.py --config evals/chat_memory_eval/config.toml
```

Outputs stream to `evals/chat_memory_eval/outputs/` as timestamped CSV, JSONL, and summary JSON files. The JSONL preserves the full turn records, final memory, deterministic score, and optional judge payload.

## What It Checks

- The assistant does not self-disclose as an AI, bot, virtual assistant, or generated program.
- The final `human` memory block changed from its initial value.
- The final `human` memory contains expected user facts from the fixture: `张伟`, `Rocky`, and `哈士奇/Husky`.
- Per-turn tool calls and memory-tool calls are recorded when visible in the Agent Platform response.

The optional LLM judge is diagnostic only. The process exit code uses deterministic checks.

## Config

The default config is `evals/chat_memory_eval/config.toml`.

| Field | Default | Meaning |
| --- | --- | --- |
| `api_base_url` | `http://127.0.0.1:8284` | Agent Platform API base URL. |
| `output_dir` | `evals/chat_memory_eval/outputs` | Directory for generated artifacts. |
| `fixture_key` | `recent_user_chat_turns` | Fixture JSON in `fixtures/`. |
| `rounds` | `3` | Number of fresh agents to run. |
| `model` | `openai-proxy/dgx_vllm::qwen3.6-35b-a3b-fp8` | Agent Studio model handle. |
| `prompt_key` | `chat_v20260516` | Chat prompt key. |
| `persona_key` | `chat_linxiaotang` | Chat persona key. |
| `embedding` | `letta/letta-free` | Letta embedding handle. |
| `timeout_seconds` | `180` | Runtime timeout sent to `/api/v1/chat`. |
| `retry_count` | `0` | Runtime retry count sent to `/api/v1/chat`. |
| `judge_enabled` | `true` | Run advisory router-backed LLM judge. |
| `judge_model_key` | blank | Router model key for judge; blank derives it from `model`. |
| `api_retry_count` | `2` | Transport retry count for script-to-API calls. |

## Test Center

ADE Test Center can launch this workflow with a focused form. UI-launched runs write artifacts under `tests/outputs/platform_orchestrator/<run_id>/` so the log, CSV, JSONL, and summary are all visible from the run artifact panel.

## Troubleshooting

- If options validation fails, refresh ADE options and confirm the selected chat model, prompt, persona, and embedding are available.
- If judge calls fail but deterministic checks pass, inspect the JSONL `judge.error`; judge failures are advisory.
- If temporary agents remain after an interrupted run, archive/purge them from Agent Studio.
