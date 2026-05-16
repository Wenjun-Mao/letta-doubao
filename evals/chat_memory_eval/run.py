from __future__ import annotations

import argparse
import sys
from pathlib import Path

WORKFLOW_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = WORKFLOW_ROOT.parents[1]
if str(WORKFLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKFLOW_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evals.chat_memory_eval.config import apply_cli_overrides, load_config  # noqa: E402
from evals.chat_memory_eval.workflow import run_evaluation  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Agent Platform chat memory eval rounds.")
    parser.add_argument("--config", default=str(WORKFLOW_ROOT / "config.toml"))
    parser.add_argument("--api-base-url", default="")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--prompt-key", default="")
    parser.add_argument("--persona-key", default="")
    parser.add_argument("--embedding", default="")
    parser.add_argument("--fixture-key", default="")
    parser.add_argument("--rounds", type=int, default=None)
    parser.add_argument("--timeout-seconds", type=float, default=None)
    parser.add_argument("--retry-count", type=int, default=None)
    parser.add_argument("--judge-model-key", default="")
    parser.add_argument("--judge-enabled", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--keep-agents", action="store_true")
    args = parser.parse_args(argv)

    config = apply_cli_overrides(load_config(Path(args.config)), args)
    summary = run_evaluation(config)
    return 0 if summary.get("rounds_total") == summary.get("rounds_passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
