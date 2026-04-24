from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from knowledge_hub import create_app
from knowledge_hub.db import create_all, get_session, remove_session
from knowledge_hub.services import (
    get_inbox_status,
    get_inbox_watcher_status,
    mark_inbox_watcher_heartbeat,
    mark_inbox_watcher_started,
    mark_inbox_watcher_stopped,
    process_inbox,
    safe_record_automation_event,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Process JSON files from the Knowledge Hub inbox.")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Keep polling the inbox folder instead of processing once.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Polling interval in seconds for --watch mode.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Process only the first N pending files in one pass.",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        help="Stop after N polling cycles in --watch mode. Useful for testing and scheduled runs.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print the current inbox watcher status file and exit.",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        create_all(app)
        if args.status:
            print(json.dumps(get_inbox_watcher_status(app.config), ensure_ascii=False, indent=2))
            return 0

        if not args.watch:
            summary = process_inbox(get_session(), app.config, limit=args.limit)
            print(json.dumps({"ok": True, **summary.to_dict()}, ensure_ascii=False, indent=2))
            remove_session()
            return 0

        mark_inbox_watcher_started(app.config, pid=os.getpid(), interval_seconds=max(args.interval, 0.5))
        safe_record_automation_event(
            get_session(),
            event_type="inbox_watcher",
            source="worker",
            status="success",
            message=f"Inbox watcher started with {max(args.interval, 0.5)}s interval.",
            details={"pid": os.getpid(), "interval_seconds": max(args.interval, 0.5)},
        )
        remove_session()

        first_iteration = True
        cycle_count = 0
        try:
            while True:
                session = get_session()
                try:
                    summary = process_inbox(session, app.config, limit=args.limit)
                    mark_inbox_watcher_heartbeat(
                        app.config,
                        summary={
                            **summary.to_dict(),
                            "inbox_status": get_inbox_status(app.config),
                        },
                    )
                    if first_iteration or summary.scanned_count > 0:
                        payload = {
                            "ok": True,
                            **summary.to_dict(),
                            "inbox_status": get_inbox_status(app.config),
                            "watcher_status": get_inbox_watcher_status(app.config),
                        }
                        print(json.dumps(payload, ensure_ascii=False, indent=2))
                        first_iteration = False
                except Exception as exc:
                    mark_inbox_watcher_heartbeat(
                        app.config,
                        summary={
                            "scanned_count": 0,
                            "success_count": 0,
                            "failed_count": 1,
                            "files": [],
                        },
                        error=str(exc),
                    )
                    safe_record_automation_event(
                        session,
                        event_type="inbox_watcher_cycle",
                        source="worker",
                        status="failed",
                        message=f"Inbox watcher cycle failed: {exc}",
                        details={"error": str(exc)},
                    )
                    print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
                finally:
                    remove_session()

                cycle_count += 1
                if args.max_cycles and cycle_count >= args.max_cycles:
                    break
                time.sleep(max(args.interval, 0.5))
        finally:
            mark_inbox_watcher_stopped(
                app.config,
                reason="max_cycles_reached" if args.max_cycles and cycle_count >= args.max_cycles else "stopped",
            )
            safe_record_automation_event(
                get_session(),
                event_type="inbox_watcher",
                source="worker",
                status="success",
                message="Inbox watcher stopped.",
                details={"pid": os.getpid(), "cycles_completed": cycle_count},
            )
            remove_session()

        return 0


if __name__ == "__main__":
    raise SystemExit(main())
