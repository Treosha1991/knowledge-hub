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
from knowledge_hub.services import build_deploy_readiness, render_deploy_readiness_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Show the current deploy-readiness checklist.")
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        payload = build_deploy_readiness(app.config)

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_deploy_readiness_text(payload))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
