# Comment Persona Eval

Runs active Comment Lab personas against one news article through the live Agent Platform API. The goal is to compare whether different personas produce meaningfully different comment styles.

## Quick Commands

Smoke test one persona:

```bash
uv run python evals/comment_persona_eval/run.py --config evals/comment_persona_eval/config.toml --persona-key comment_linxiaotang --limit 1
```

Run the full matrix:

```bash
uv run python evals/comment_persona_eval/run.py --config evals/comment_persona_eval/config.toml
```

Outputs are streamed to `evals/comment_persona_eval/outputs/` as timestamped CSV and JSONL files. The console prints simple attempt progress like `[35/200]`, and each completed attempt is flushed to disk immediately so partial results survive an interrupted run.

## Config

The default config is `evals/comment_persona_eval/config.toml`.

| Field | Default | Meaning |
| --- | --- | --- |
| `api_base_url` | `http://127.0.0.1:8284` | Agent Platform API base URL. |
| `output_dir` | `evals/comment_persona_eval/outputs` | Directory for generated CSV/JSONL artifacts. |
| `news_path` | `evals/comment_persona_eval/inputs/sports_news_demo.txt` | Text file used as the Comment Lab input. |
| `rounds` | `3` | Number of times each persona comments on the same input. |
| `concurrency` | `1` | Reserved for future use; only `1` is supported because local LLM serving is GPU-bound. |
| `stop_on_error` | `false` | Stop the run after the first failed attempt. |
| `persona_keys` | `[]` | Optional explicit list of persona keys to run. |
| `persona_search` | `""` | Optional server-side Prompt Center persona search query. |
| `limit` | `0` | Optional cap on matched personas; `0` means no cap. |
| `model_key` | `local_llama_server::gemma4` | Router-scoped Comment Lab model key. |
| `prompt_key` | `comment_v20260418` | Comment Lab system prompt key. |
| `max_tokens` | `0` | Comment Lab token budget; `0` means no `max_tokens` is sent. |
| `timeout_seconds` | `180` | Provider timeout sent to Comment Lab. |
| `retry_count` | `0` | Comment Lab provider retry count. |
| `task_shape` | `all_in_system` | Prompt packing strategy. |
| `cache_prompt` | `false` | llama.cpp prompt-cache toggle. Keep off for fair persona comparison runs. |
| `temperature` | `0.6` | Comment Lab sampling temperature. |
| `top_p` | `1.0` | Comment Lab nucleus sampling value. |
| `top_k` | `64` | Optional top-k sampling value; set blank/omit in custom configs to leave unset. |
| `api_retry_count` | `2` | Transport retry count for script-to-API calls. |

CLI overrides:

```text
--api-base-url
--output-dir
--limit
--persona-key  # repeatable
```

## CSV Columns

The CSV is for comparison and spreadsheet review. It includes:

`run_id`, `round`, `persona_key`, `persona_label`, `persona_description`, `status`, `elapsed_seconds`, `content`, `content_length`, `finish_reason`, `content_source`, `usage_prompt_tokens`, `usage_completion_tokens`, `usage_total_tokens`, `error`, `model_key`, `prompt_key`, `task_shape`, `cache_prompt`, `temperature`, `top_p`, `top_k`, `max_tokens`, `timeout_seconds`, `retry_count`, `timings_cache_n`, `timings_prompt_n`, `timings_predicted_n`.

The JSONL sidecar preserves the full request, persona metadata, response payload, error text, and timing for each attempt.

Both files are written incrementally. If a run is stopped early, open the latest timestamped CSV/JSONL and you should still see all attempts that completed before the interruption.

## Troubleshooting

- If persona listing fails, make sure `agent_platform_api` is rebuilt/restarted and can open `data/personas/personas.sqlite3`.
- If the script says `model_key ... is not available`, copy an exact key from `GET /api/v1/options?scenario=comment`; Ark model ids are exact, including version fragments such as `2-0`.
- If model calls fail, check `http://127.0.0.1:8290/v1/router/model-catalog` and confirm `local_llama_server::gemma4` is healthy.
- If the run is slow, lower `rounds`, use `--persona-key`, or use `--limit` for a pilot run.
