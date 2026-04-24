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
from knowledge_hub.services import build_gpt_actions_schema


def main() -> int:
    parser = argparse.ArgumentParser(description="Print the Knowledge Hub GPT Actions OpenAPI schema.")
    parser.add_argument("--server-url", default=None, help="Optional override for the schema server URL.")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        payload = build_gpt_actions_schema(app.config, server_url=args.server_url)

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
