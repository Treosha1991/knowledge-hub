from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from knowledge_hub import create_app
from knowledge_hub.db import create_all, get_session
from knowledge_hub.services import (
    SessionImportError,
    import_project_package,
    refresh_project_export_bundles,
    safe_record_automation_event,
)
from knowledge_hub.utils import decode_text_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a full project package into Knowledge Hub.")
    parser.add_argument(
        "source",
        nargs="?",
        help="Path to the package JSON file.",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Import the bundled sample package from examples/project_package.sample.json.",
    )
    parser.add_argument(
        "--no-auto-create-project",
        action="store_true",
        help="Fail instead of auto-creating the project if it does not exist.",
    )
    parser.add_argument(
        "--workspace-slug",
        help="Optional fallback workspace slug when the package project does not specify one.",
    )
    args = parser.parse_args()

    source_path = _resolve_source_path(args.source, use_sample=args.sample)
    if source_path is None:
        parser.error("Provide a package file path or use --sample.")

    if not source_path.exists():
        sample_hint = ROOT / "examples" / "project_package.sample.json"
        print(
            f"Package file was not found: {source_path}\n"
            f"Use an existing JSON file or run:\n"
            f"python tools/import_project_package.py --sample\n"
            f"Bundled sample: {sample_hint}",
            file=sys.stderr,
        )
        return 1

    raw_text = decode_text_bytes(source_path.read_bytes())
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}.", file=sys.stderr)
        return 1

    if args.workspace_slug and isinstance(payload, dict):
        project_payload = payload.setdefault("project", {})
        if isinstance(project_payload, dict) and not project_payload.get("workspace_slug"):
            project_payload["workspace_slug"] = args.workspace_slug

    app = create_app()
    with app.app_context():
        create_all(app)
        db_session = get_session()
        try:
            result = import_project_package(
                db_session,
                payload,
                auto_create_project=not args.no_auto_create_project,
                config=app.config,
            )
            export_paths = refresh_project_export_bundles(
                db_session,
                app.config,
                [result.project_slug],
            )
            safe_record_automation_event(
                db_session,
                event_type="project_package_import",
                source="cli",
                message=(
                    f"Project package import completed. Logs imported {result.session_logs.imported_count}, "
                    f"duplicates skipped {result.session_logs.skipped_count}."
                ),
                project_slug=result.project_slug,
                details={
                    "session_logs_imported": result.session_logs.imported_count,
                    "session_logs_skipped_duplicates": result.session_logs.skipped_count,
                },
            )
        except SessionImportError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    output = {
        "ok": True,
        "workspace_slug": result.workspace_slug,
        "project_slug": result.project_slug,
        "project_created": result.project_created,
        "session_logs_imported": result.session_logs.imported_count,
        "session_logs_skipped_duplicates": result.session_logs.skipped_count,
        "prompt_templates_created": result.prompt_templates.created_count,
        "prompt_templates_updated": result.prompt_templates.updated_count,
        "snapshots_created": result.snapshots.created_count,
        "snapshots_updated": result.snapshots.updated_count,
        "project_exports": [item.to_dict() for item in export_paths],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def _resolve_source_path(source: str | None, *, use_sample: bool) -> Path | None:
    if use_sample:
        return ROOT / "examples" / "project_package.sample.json"
    if source is None:
        return None
    return Path(source)


if __name__ == "__main__":
    raise SystemExit(main())
