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
    import_session_payload,
    refresh_project_export_bundles,
    safe_record_events_for_projects,
)
from knowledge_hub.utils import decode_text_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description="Import one or more session logs into Knowledge Hub.")
    parser.add_argument(
        "source",
        nargs="?",
        default="-",
        help="Path to a JSON file. Use '-' to read from stdin.",
    )
    parser.add_argument(
        "--project-slug",
        help="Fallback project slug if the payload omits it.",
    )
    parser.add_argument(
        "--project-id",
        type=int,
        help="Fallback project id if the payload omits project information.",
    )
    parser.add_argument(
        "--workspace-id",
        type=int,
        help="Fallback workspace id when auto-creating a project from the payload.",
    )
    parser.add_argument(
        "--workspace-slug",
        help="Fallback workspace slug when auto-creating a project from the payload.",
    )
    parser.add_argument(
        "--no-auto-create-project",
        action="store_true",
        help="Fail instead of auto-creating a project from an unknown project_slug.",
    )
    args = parser.parse_args()

    raw_text = _read_input(args.source)
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}.", file=sys.stderr)
        return 1

    app = create_app()
    with app.app_context():
        create_all(app)
        db_session = get_session()
        try:
            result = import_session_payload(
                db_session,
                payload,
                fallback_project_id=args.project_id,
                fallback_project_slug=args.project_slug,
                fallback_workspace_id=args.workspace_id,
                fallback_workspace_slug=args.workspace_slug,
                auto_create_project=not args.no_auto_create_project,
                config=app.config,
            )
            export_paths = refresh_project_export_bundles(
                db_session,
                app.config,
                [log.project.slug for log in result.logs + result.skipped_logs],
            )
            safe_record_events_for_projects(
                db_session,
                project_slugs=[log.project.slug for log in result.logs + result.skipped_logs],
                event_type="session_log_import",
                source="cli",
                message=(
                    f"Session log import completed. Imported {result.imported_count}, "
                    f"skipped duplicates {result.skipped_count}."
                ),
                details={
                    "imported_count": result.imported_count,
                    "skipped_duplicates": result.skipped_count,
                },
                log_global_if_empty=True,
            )
        except SessionImportError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        output = {
            "ok": True,
            "imported_count": result.imported_count,
            "skipped_duplicates": result.skipped_count,
            "project_slugs": [log.project.slug for log in result.logs],
            "projects_created": [project.slug for project in result.projects_created],
            "log_ids": [log.id for log in result.logs],
            "skipped_log_ids": [log.id for log in result.skipped_logs],
            "project_exports": [item.to_dict() for item in export_paths],
        }

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def _read_input(source: str) -> str:
    if source == "-":
        return decode_text_bytes(sys.stdin.buffer.read())
    return decode_text_bytes(Path(source).read_bytes())


if __name__ == "__main__":
    raise SystemExit(main())
