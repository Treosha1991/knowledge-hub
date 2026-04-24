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
from knowledge_hub.services import build_ready_for_next_chat


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the single best ready-for-next-chat handoff for a project.")
    parser.add_argument("project_slug", help="Project slug to export.")
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        create_all(app)
        db_session = get_session()
        project = db_session.scalar(select(Project).where(Project.slug == args.project_slug))
        if project is None:
            print(f"Project '{args.project_slug}' was not found.", file=sys.stderr)
            return 1

        payload = build_ready_for_next_chat(db_session, app.config, project)

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload["text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
