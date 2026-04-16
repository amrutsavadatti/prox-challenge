from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prox_agent.local_answer import answer_local  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: uv run python scripts/ask_local.py "your question"')
        raise SystemExit(2)
    question = " ".join(sys.argv[1:])
    print(json.dumps(answer_local(question), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
