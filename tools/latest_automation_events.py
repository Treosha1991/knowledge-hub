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
from knowledge_hub.services import list_recent_automation_events


def main() -> int:
    parser = argparse.ArgumentParser(description="List the latest automation events.")
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of events to return.",
    )
    parser.add_argument(
        "--project-slug",
        help="Optional project slug to scope the events.",
    )
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
        payload = list_recent_automation_events(
            get_session(),
            project_slug=args.project_slug,
            limit=args.limit,
        )

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if not payload:
        print("No automation events found.")
        return 0

    for item in payload:
        project_label = item["project_slug"] or "global"
        print(f"{item['created_at']} | {project_label} | {item['event_type']} | {item['source']} | {item['status']}")
        print(f"  Message: {item['message']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
