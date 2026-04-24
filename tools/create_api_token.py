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
from knowledge_hub.models import User
from knowledge_hub.services import issue_api_token, serialize_api_token


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a Knowledge Hub API token for chat integrations.")
    parser.add_argument("--email", help="Target user email. Defaults to KH_DEFAULT_OWNER_EMAIL.")
    parser.add_argument("--label", default="Chat Integration Token", help="Human-readable token label.")
    parser.add_argument("--expires-in-days", type=int, default=90, help="Token lifetime in days.")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format.")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        create_all(app)
        db_session = get_session()
        target_email = (args.email or app.config["DEFAULT_OWNER_EMAIL"]).strip().lower()
        user = db_session.scalar(select(User).where(User.email == target_email))
        if user is None:
            print(f"User '{target_email}' was not found.", file=sys.stderr)
            return 1

        issued = issue_api_token(
            db_session,
            user=user,
            label=args.label,
            expires_in_days=args.expires_in_days,
            commit=True,
        )
        payload = {
            "ok": True,
            "user_email": user.email,
            "token": issued.plaintext_token,
            "token_record": serialize_api_token(issued.record),
            "usage": {
                "authorization_header": f"Bearer {issued.plaintext_token}",
                "context_endpoint": "/api/projects/<project-slug>/ready-for-next-chat",
                "chat_ingest_endpoint": "/api/chat-ingest/session",
            },
        }

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"User: {payload['user_email']}")
        print(f"Token: {payload['token']}")
        print(f"Authorization: {payload['usage']['authorization_header']}")
        print(f"Context endpoint: {payload['usage']['context_endpoint']}")
        print(f"Chat ingest endpoint: {payload['usage']['chat_ingest_endpoint']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
