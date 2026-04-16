from __future__ import annotations

import json
import os
from typing import Any

from claude_code_sdk import (
    AssistantMessage,
    ClaudeCodeOptions,
    ClaudeSDKClient,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from dotenv import dotenv_values

from prox_agent.knowledge import ROOT
from prox_agent.local_answer import answer_local
from prox_agent.sdk_tools import (
    ALLOWED_TOOL_NAMES,
    MCP_SERVER_NAME,
    TOOL_NAMES,
    build_knowledge_mcp_server,
)


SYSTEM_PROMPT = """You are the Prox product assistant for the Vulcan OmniPro 220 welder.

Answer like you are helping a practical garage user who wants the correct setup, not a lecture.

Grounding rules:
- Use the provided MCP tools for every product-specific factual claim.
- If the question asks about duty cycle, call lookup_duty_cycle.
- If the question asks about polarity, cable placement, sockets, or setup, call lookup_polarity and get_manual_image.
- If the question asks about symptoms, weld defects, or repair steps, call troubleshooting_for and search_manual.
- If an answer would be clearer with a chart, diagram, setup image, or manual page, call get_manual_image and include it as an artifact.
- Do not invent product specs. If the tools do not contain enough evidence, say what is missing and ask a focused follow-up.
- Preserve source_ref objects from tool results in citations whenever possible.

Safety rules:
- For cable swaps, polarity changes, cleaning, troubleshooting, or internal adjustment, tell the user to power off and disconnect input power first.
- Do not recommend unsafe bypasses or unsupported modifications.

Return format:
Return only valid JSON. Do not wrap it in Markdown fences. The top-level object must have these keys:
{
  "answer_markdown": "short practical answer in Markdown",
  "citations": [
    {"doc_id": "...", "source_doc": "...", "page": 1, "element_id": "..."}
  ],
  "artifacts": [
    {
      "type": "manual_image | duty_cycle_result | troubleshooting_flow | setup_diagram",
      "title": "...",
      "path": "relative/path/when_available",
      "source_ref": {"doc_id": "...", "source_doc": "...", "page": 1, "element_id": "..."},
      "payload": {}
    }
  ],
  "safety_flags": ["short_machine_readable_flag"]
}
"""

API_KEY_PLACEHOLDERS = {
    "",
    "your-api-key-here",
    "your_api_key_here",
    "replace-me",
    "changeme",
}


class MissingAPIKeyError(RuntimeError):
    pass


def build_agent_options(
    *,
    api_key: str,
    model: str | None = None,
    max_turns: int = 8,
) -> ClaudeCodeOptions:
    env = {"ANTHROPIC_API_KEY": api_key}
    resolved_model = model or os.getenv("ANTHROPIC_MODEL") or None
    return ClaudeCodeOptions(
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={MCP_SERVER_NAME: build_knowledge_mcp_server()},
        allowed_tools=ALLOWED_TOOL_NAMES,
        max_turns=max_turns,
        model=resolved_model,
        cwd=ROOT,
        env=env,
    )


def build_dry_run(question: str, *, model: str | None = None, max_turns: int = 8) -> dict[str, Any]:
    options = build_agent_options(api_key="dry-run-not-used", model=model, max_turns=max_turns)
    return {
        "status": "ready_for_api_key",
        "will_call_claude": False,
        "sdk": "claude-code-sdk",
        "working_directory": str(ROOT),
        "mcp_server": MCP_SERVER_NAME,
        "registered_tools": TOOL_NAMES,
        "allowed_tools": options.allowed_tools,
        "max_turns": options.max_turns,
        "model": options.model,
        "question": question,
        "local_preview": answer_local(question),
    }


async def ask_claude(
    question: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    max_turns: int = 8,
) -> dict[str, Any]:
    resolved_api_key = api_key or _api_key_from_env()
    if not _has_real_api_key(resolved_api_key):
        raise MissingAPIKeyError(
            "Set ANTHROPIC_API_KEY in .env before running the Claude agent. "
            "No Claude call was made."
        )

    options = build_agent_options(api_key=resolved_api_key, model=model, max_turns=max_turns)
    messages: list[dict[str, Any]] = []
    assistant_text: list[str] = []
    result_message: ResultMessage | None = None

    async with ClaudeSDKClient(options=options) as client:
        await client.query(_user_prompt(question))
        async for message in client.receive_response():
            messages.append(_serialize_message(message))
            if isinstance(message, AssistantMessage):
                assistant_text.extend(
                    block.text for block in message.content if isinstance(block, TextBlock)
                )
            elif isinstance(message, ResultMessage):
                result_message = message

    raw_text = "\n".join(part for part in assistant_text if part).strip()
    if not raw_text and result_message and result_message.result:
        raw_text = result_message.result.strip()

    parsed = _parse_json_object(raw_text)
    if parsed is None:
        parsed = {
            "answer_markdown": raw_text,
            "citations": [],
            "artifacts": [],
            "safety_flags": [],
            "parse_warning": "Claude did not return a clean JSON object.",
        }

    parsed.setdefault("answer_markdown", "")
    parsed.setdefault("citations", [])
    parsed.setdefault("artifacts", [])
    parsed.setdefault("safety_flags", [])
    parsed["claude"] = _result_metadata(result_message)
    parsed["messages"] = messages
    return parsed


def _user_prompt(question: str) -> str:
    return f"User question:\n{question}"


def _has_real_api_key(value: str) -> bool:
    stripped = value.strip()
    if not stripped or stripped.lower() in API_KEY_PLACEHOLDERS:
        return False
    return stripped.startswith("sk-ant-")


def _api_key_from_env() -> str:
    env_path = ROOT / ".env"
    if env_path.exists():
        file_value = dotenv_values(env_path).get("ANTHROPIC_API_KEY")
        if isinstance(file_value, str):
            return file_value
    return os.getenv("ANTHROPIC_API_KEY", "")


def _parse_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def _serialize_message(message: Any) -> dict[str, Any]:
    if isinstance(message, AssistantMessage):
        return {
            "type": "assistant",
            "model": message.model,
            "content": [_serialize_block(block) for block in message.content],
        }
    if isinstance(message, UserMessage):
        return {
            "type": "user",
            "content": message.content,
        }
    if isinstance(message, SystemMessage):
        return {
            "type": "system",
            "subtype": message.subtype,
            "data": message.data,
        }
    if isinstance(message, ResultMessage):
        return {
            "type": "result",
            **_result_metadata(message),
        }
    return {
        "type": type(message).__name__,
        "repr": repr(message),
    }


def _serialize_block(block: Any) -> dict[str, Any]:
    if isinstance(block, TextBlock):
        return {"type": "text", "text": block.text}
    if isinstance(block, ToolUseBlock):
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    if isinstance(block, ToolResultBlock):
        return {
            "type": "tool_result",
            "tool_use_id": block.tool_use_id,
            "content": block.content,
            "is_error": block.is_error,
        }
    return {
        "type": type(block).__name__,
        "repr": repr(block),
    }


def _result_metadata(message: ResultMessage | None) -> dict[str, Any]:
    if message is None:
        return {}
    return {
        "subtype": message.subtype,
        "is_error": message.is_error,
        "num_turns": message.num_turns,
        "duration_ms": message.duration_ms,
        "duration_api_ms": message.duration_api_ms,
        "total_cost_usd": message.total_cost_usd,
        "usage": message.usage,
        "session_id": message.session_id,
    }
