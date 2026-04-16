from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prox_agent.agent import MissingAPIKeyError, ask_claude, build_dry_run  # noqa: E402


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask the Prox Claude SDK agent.")
    parser.add_argument("question", help="Question to ask about the Vulcan OmniPro 220.")
    parser.add_argument(
        "--use-api",
        action="store_true",
        help="Call Claude. Without this flag, the command stays in local dry-run mode.",
    )
    parser.add_argument("--model", help="Optional Claude model override.")
    parser.add_argument("--max-turns", type=int, default=8, help="Claude Code max turns.")
    args = parser.parse_args()

    if not args.use_api:
        print_json(build_dry_run(args.question, model=args.model, max_turns=args.max_turns))
        return 0

    try:
        result = asyncio.run(
            ask_claude(args.question, model=args.model, max_turns=args.max_turns)
        )
    except MissingAPIKeyError as exc:
        print(str(exc), file=sys.stderr)
        print(
            f'Try a safe local check: uv run python scripts/ask_agent.py "{args.question}"',
            file=sys.stderr,
        )
        return 2

    print_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
