from __future__ import annotations

import json
from typing import Any

from claude_code_sdk import create_sdk_mcp_server, tool

from prox_agent.knowledge import KnowledgeBase


MCP_SERVER_NAME = "prox_knowledge"

SEARCH_MANUAL_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Natural-language search query for the extracted manual text.",
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of results to return.",
            "minimum": 1,
            "maximum": 10,
            "default": 5,
        },
    },
    "required": ["query"],
}

DUTY_CYCLE_SCHEMA = {
    "type": "object",
    "properties": {
        "process": {
            "type": "string",
            "description": "Welding process, such as MIG, Flux-Cored, TIG, or Stick.",
        },
        "input_voltage": {
            "type": "string",
            "description": "Input voltage, normally 120V or 240V.",
        },
        "amperage": {
            "type": "integer",
            "description": "Requested output amperage.",
        },
    },
    "required": ["process", "input_voltage", "amperage"],
}

POLARITY_SCHEMA = {
    "type": "object",
    "properties": {
        "process": {
            "type": "string",
            "description": "Welding process, such as MIG, Flux-Cored, TIG, or Stick.",
        },
    },
    "required": ["process"],
}

TROUBLESHOOTING_SCHEMA = {
    "type": "object",
    "properties": {
        "symptom": {
            "type": "string",
            "description": "Observed welding problem or user description.",
        },
        "process": {
            "type": "string",
            "description": "Optional process context, such as MIG or Flux-Cored.",
        },
    },
    "required": ["symptom"],
}

MANUAL_IMAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Visual topic to locate, such as TIG polarity, wire feed, or porosity diagnosis.",
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of visual artifacts to return.",
            "minimum": 1,
            "maximum": 6,
            "default": 3,
        },
    },
    "required": ["query"],
}

_KB = KnowledgeBase()


def _text_response(payload: Any) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, indent=2, sort_keys=True),
            }
        ]
    }


def _limit(args: dict[str, Any], default: int, maximum: int) -> int:
    raw_value = args.get("limit", default)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = default
    return min(max(value, 1), maximum)


@tool(
    "search_manual",
    "Search extracted text from the Vulcan OmniPro 220 manual and guides. Returns cited snippets and page images.",
    SEARCH_MANUAL_SCHEMA,
)
async def search_manual_tool(args: dict[str, Any]) -> dict[str, Any]:
    query = str(args["query"])
    return _text_response(
        {
            "query": query,
            "results": _KB.search_manual(query, limit=_limit(args, default=5, maximum=10)),
        }
    )


@tool(
    "lookup_duty_cycle",
    "Look up a verified duty-cycle row by process, input voltage, and amperage.",
    DUTY_CYCLE_SCHEMA,
)
async def lookup_duty_cycle_tool(args: dict[str, Any]) -> dict[str, Any]:
    result = _KB.lookup_duty_cycle(
        process=str(args["process"]),
        input_voltage=str(args["input_voltage"]),
        amperage=int(args["amperage"]),
    )
    return _text_response(
        {
            "result": result,
            "found": result is not None,
        }
    )


@tool(
    "lookup_polarity",
    "Look up the verified polarity setup and socket placement for a welding process.",
    POLARITY_SCHEMA,
)
async def lookup_polarity_tool(args: dict[str, Any]) -> dict[str, Any]:
    result = _KB.lookup_polarity(str(args["process"]))
    return _text_response(
        {
            "result": result,
            "found": result is not None,
        }
    )


@tool(
    "troubleshooting_for",
    "Find verified troubleshooting checks for a symptom, optionally scoped to a welding process.",
    TROUBLESHOOTING_SCHEMA,
)
async def troubleshooting_for_tool(args: dict[str, Any]) -> dict[str, Any]:
    result = _KB.troubleshooting_for(
        symptom=str(args["symptom"]),
        process=str(args["process"]) if args.get("process") else None,
    )
    return _text_response(
        {
            "results": result,
            "found": bool(result),
        }
    )


@tool(
    "get_manual_image",
    "Find relevant manual page images, diagrams, charts, or product photos to surface as visual artifacts.",
    MANUAL_IMAGE_SCHEMA,
)
async def get_manual_image_tool(args: dict[str, Any]) -> dict[str, Any]:
    query = str(args["query"])
    return _text_response(
        {
            "query": query,
            "results": _KB.get_manual_image(query, limit=_limit(args, default=3, maximum=6)),
        }
    )


KNOWLEDGE_TOOLS = [
    search_manual_tool,
    lookup_duty_cycle_tool,
    lookup_polarity_tool,
    troubleshooting_for_tool,
    get_manual_image_tool,
]

TOOL_NAMES = [sdk_tool.name for sdk_tool in KNOWLEDGE_TOOLS]
ALLOWED_TOOL_NAMES = [
    *TOOL_NAMES,
    *(f"mcp__{MCP_SERVER_NAME}__{name}" for name in TOOL_NAMES),
    "Read",
]


def build_knowledge_mcp_server() -> dict[str, Any]:
    return create_sdk_mcp_server(MCP_SERVER_NAME, version="0.1.0", tools=KNOWLEDGE_TOOLS)
