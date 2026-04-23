from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

from agent_platform_api.settings import get_settings
from utils.model_allowlist import resolve_source_allowlist_path
from utils.provider_model_probe import probe_source_chat_models, probe_source_label_models


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe configured provider models and optionally write a checked-in allowlist report.",
    )
    parser.add_argument("--source-id", required=True, help="Configured source id from AGENT_PLATFORM_MODEL_SOURCES.")
    parser.add_argument(
        "--mode",
        default="chat-probe",
        choices=["chat-probe", "label-structured"],
        help="Probe mode to run.",
    )
    parser.add_argument("--write", action="store_true", help="Write the probe report to the configured allowlist path.")
    parser.add_argument("--output", help="Optional output path override for the generated report.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    args = parse_args(argv)
    settings = get_settings()
    source_id = str(args.source_id or "").strip()
    source = next((item for item in settings.model_sources if item.id == source_id), None)
    if source is None:
        print(f"Unknown source id: {source_id}", file=sys.stderr)
        return 2

    if args.mode == "label-structured":
        report = probe_source_label_models(
            source,
            timeout_seconds=settings.model_discovery_timeout_seconds,
        )
    else:
        report = probe_source_chat_models(
            source,
            timeout_seconds=settings.model_discovery_timeout_seconds,
        )
    payload = report.to_dict()
    if not args.write:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    output_path = _resolve_output_path(source_id, probe_mode=args.mode, explicit_path=args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n", encoding="utf-8")
    print(f"Wrote probe report to {output_path}")
    return 0


def _resolve_output_path(source_id: str, *, probe_mode: str, explicit_path: str | None) -> Path:
    if explicit_path:
        return Path(explicit_path).expanduser().resolve()

    configured_path = resolve_source_allowlist_path(source_id, probe_mode=probe_mode)
    if configured_path is None:
        raise ValueError(
            f"No checked-in allowlist path is configured for source '{source_id}' and mode '{probe_mode}'"
        )
    return configured_path


if __name__ == "__main__":
    raise SystemExit(main())
