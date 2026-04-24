from __future__ import annotations

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
from knowledge_hub.db import create_all, get_session, remove_session
from knowledge_hub.services import create_backup_archive, safe_record_automation_event


def main() -> int:
    app = create_app()
    with app.app_context():
        create_all(app)
        session = get_session()
        try:
            result = create_backup_archive(app.config)
            safe_record_automation_event(
                session,
                event_type="backup_create",
                source="cli",
                message=f"Created backup archive {result.archive.filename}.",
                details=result.to_dict(),
            )
            print(json.dumps({"ok": True, **result.to_dict()}, ensure_ascii=False, indent=2))
            return 0
        finally:
            remove_session()


if __name__ == "__main__":
    raise SystemExit(main())
