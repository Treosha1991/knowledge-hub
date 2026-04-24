from __future__ import annotations

import argparse
from datetime import datetime, timezone
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
from knowledge_hub.db import get_session
from knowledge_hub.services import get_mail_status, safe_record_automation_event, send_email


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a test email through the configured Knowledge Hub mail backend.")
    parser.add_argument("to_email", help="Recipient email address.")
    parser.add_argument(
        "--subject",
        default="Knowledge Hub mail backend test",
        help="Message subject.",
    )
    parser.add_argument(
        "--body",
        default=None,
        help="Optional plain-text body. A default body is used when omitted.",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        db_session = get_session()
        body = args.body or _default_body()
        try:
            delivery = send_email(
                app.config,
                to_email=args.to_email,
                subject=args.subject,
                text_body=body,
                metadata={"kind": "mail_test"},
            )
            safe_record_automation_event(
                db_session,
                event_type="mail_test_send",
                source="cli",
                message=f"Sent test email to {args.to_email} via {delivery.backend}.",
                details=delivery.to_dict(),
            )
        except ValueError as exc:
            safe_record_automation_event(
                db_session,
                event_type="mail_test_send",
                source="cli",
                status="error",
                message=f"Mail test failed for {args.to_email}.",
                details={"error": str(exc), "mail_backend": app.config.get("MAIL_BACKEND")},
            )
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
            return 1

        print(
            json.dumps(
                {
                    "ok": True,
                    "delivery": delivery.to_dict(),
                    "mail_status": get_mail_status(app.config, limit=1),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


def _default_body() -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    return "\n".join(
        [
            "This is a Knowledge Hub test email.",
            "",
            f"Generated at: {generated_at}",
            "",
            "If you received this message, the configured mail backend is working.",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
