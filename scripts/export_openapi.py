from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _canonical_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _build_openapi_schema(project_root: Path) -> dict:
    sys.path.insert(0, str(project_root))
    from dev_ui.main import app  # Imported lazily so script can run from any cwd.

    schema = app.openapi()

    if not schema.get("servers"):
        schema["servers"] = [
            {
                "url": "http://127.0.0.1:8284",
                "description": "Dev UI local",
            }
        ]

    return schema


def _check_artifact(path: Path, rendered: str) -> bool:
    if not path.exists():
        print(f"[FAIL] Missing OpenAPI artifact: {path}")
        return False

    existing = path.read_text(encoding="utf-8")
    if existing != rendered:
        print(f"[FAIL] OpenAPI artifact is out of date: {path}")
        return False

    print(f"[OK] OpenAPI artifact is current: {path}")
    return True


def _write_artifact(path: Path, rendered: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    print(f"[OK] OpenAPI artifact written: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export canonical OpenAPI artifact for Agent Platform API.")
    parser.add_argument(
        "--output",
        default="docs/openapi/agent-platform-openapi.json",
        help="Output OpenAPI JSON file path.",
    )
    parser.add_argument(
        "--frontend-output",
        default="frontend-ade/public/openapi/agent-platform-openapi.json",
        help="Secondary OpenAPI JSON path used by the ADE frontend.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check mode: fail if committed artifact differs from generated schema.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    output_path = (project_root / args.output).resolve()
    frontend_output_path = (project_root / args.frontend_output).resolve()
    output_paths = [output_path, frontend_output_path]

    schema = _build_openapi_schema(project_root)
    rendered = _canonical_json(schema)

    if args.check:
        results = [_check_artifact(path, rendered) for path in output_paths]
        if not all(results):
            print("Run: uv run python scripts/export_openapi.py")
            return 1

        return 0

    for path in output_paths:
        _write_artifact(path, rendered)

    print(f"[INFO] paths={len(schema.get('paths', {}))} schemas={len(schema.get('components', {}).get('schemas', {}))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
