from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prox_agent.cli import smoke  # noqa: E402


if __name__ == "__main__":
    smoke()
