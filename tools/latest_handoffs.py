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
from knowledge_hub.services import list_latest_handoffs


def main() -> int:
    parser = argparse.ArgumentParser(description="List the latest ready-to-chat handoffs across projects.")
    parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Maximum number of handoffs to return.",
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
        payload = list_latest_handoffs(get_session(), app.config, limit=args.limit)

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if not payload:
        print("No ready-to-chat handoffs found.")
        return 0

    for item in payload:
        print(f"{item['handoff_updated_at']} | {item['project_slug']} | {item['project_name']}")
        print(f"  Preview: {item['preview']}")
        print(f"  File: {item['export_paths']['chat_bootstrap_text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
