from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prox_agent.agent import build_agent_options  # noqa: E402
from prox_agent.sdk_tools import MCP_SERVER_NAME, TOOL_NAMES  # noqa: E402


def main() -> None:
    options = build_agent_options(api_key="dry-run-not-used")
    print(
        json.dumps(
            {
                "status": "ok",
                "sdk": "claude-code-sdk",
                "mcp_server": MCP_SERVER_NAME,
                "registered_tools": TOOL_NAMES,
                "allowed_tools": options.allowed_tools,
                "working_directory": str(options.cwd),
                "max_turns": options.max_turns,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
