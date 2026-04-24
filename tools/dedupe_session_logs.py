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
    load_projects_for_dedupe,
    run_session_log_dedupe,
    safe_record_events_for_projects,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Find or remove exact duplicate session logs.")
    parser.add_argument("project_slug", nargs="?", help="Optional project slug to scope the scan.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scan every project instead of one project.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete exact duplicate logs and refresh project exports.",
    )
    args = parser.parse_args()

    if args.project_slug is None and not args.all:
        parser.error("Provide a project slug or use --all.")
    if args.project_slug is not None and args.all:
        parser.error("Use either a project slug or --all, not both.")

    app = create_app()
    with app.app_context():
        create_all(app)
        db_session = get_session()
        try:
            projects = load_projects_for_dedupe(
                db_session,
                project_slug=args.project_slug,
                use_all=args.all,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        result = run_session_log_dedupe(
            db_session,
            app.config,
            projects,
            apply=args.apply,
        )

        if args.apply and result.removed_logs:
            safe_record_events_for_projects(
                db_session,
                project_slugs=result.touched_project_slugs,
                event_type="session_log_dedupe",
                source="cli",
                message=f"Removed {result.removed_logs} duplicate session logs.",
                details={
                    "removed_logs": result.removed_logs,
                    "duplicate_groups": result.duplicate_groups,
                },
                log_global_if_empty=True,
            )

    payload = {
        "ok": True,
        "mode": "apply" if args.apply else "dry_run",
        "duplicate_groups": result.duplicate_groups,
        "duplicate_logs": result.duplicate_logs,
        "removed_logs": result.removed_logs,
        "groups": result.groups,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
