from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from sqlalchemy import select


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
from knowledge_hub.models import Project
from knowledge_hub.services import refresh_project_export_bundles, safe_record_events_for_projects


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild ready-to-chat export files for Knowledge Hub projects.")
    parser.add_argument("project_slug", nargs="?", help="Optional single project slug to rebuild.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Rebuild exports for every project.",
    )
    args = parser.parse_args()

    if args.project_slug is None and not args.all:
        parser.error("Provide a project slug or use --all.")
    if args.project_slug is not None and args.all:
        parser.error("Use either a single project slug or --all, not both.")

    app = create_app()
    with app.app_context():
        create_all(app)
        db_session = get_session()
        if args.all:
            project_slugs = db_session.scalars(select(Project.slug).order_by(Project.slug.asc())).all()
        else:
            project_slugs = [args.project_slug]

        export_paths = refresh_project_export_bundles(db_session, app.config, project_slugs)
        safe_record_events_for_projects(
            db_session,
            project_slugs=project_slugs,
            event_type="exports_rebuild",
            source="cli",
            message=f"Rebuilt export bundle for {len(export_paths)} project(s).",
            details={"rebuilt_count": len(export_paths)},
            log_global_if_empty=True,
        )

    payload = {
        "ok": True,
        "rebuilt_count": len(export_paths),
        "project_exports": [item.to_dict() for item in export_paths],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
