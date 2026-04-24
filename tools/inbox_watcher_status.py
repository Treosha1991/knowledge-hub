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
from knowledge_hub.services import get_inbox_watcher_status


def _render_text(payload: dict) -> str:
    lines = [
        f"State: {payload['state']}",
        f"PID: {payload.get('pid') or 'Not running'}",
        f"Interval: {payload.get('interval_seconds') or '-'}",
        f"Started: {payload.get('started_at') or 'Not started'}",
        f"Last heartbeat: {payload.get('last_heartbeat_at') or 'No heartbeat'}",
        f"Heartbeat age: {payload.get('heartbeat_age_seconds') if payload.get('heartbeat_age_seconds') is not None else '-'}",
        f"Stop reason: {payload.get('stop_reason') or '-'}",
        f"Status file: {payload.get('status_path')}",
    ]
    last_summary = payload.get("last_summary") or {}
    if last_summary:
        lines.extend(
            [
                f"Last scan: scanned {last_summary.get('scanned_count', 0)}, "
                f"succeeded {last_summary.get('success_count', 0)}, "
                f"failed {last_summary.get('failed_count', 0)}",
            ]
        )
    if payload.get("last_error"):
        lines.append(f"Last error: {payload['last_error']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Show Knowledge Hub inbox watcher status.")
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        payload = get_inbox_watcher_status(app.config)

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_render_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
