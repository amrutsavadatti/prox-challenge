from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncGenerator
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
from prox_agent.response_contract import normalize_response_contract
from prox_agent.sdk_tools import (
    ALLOWED_TOOL_NAMES,
    MCP_SERVER_NAME,
    TOOL_NAMES,
    build_knowledge_mcp_server,
)


SYSTEM_PROMPT = """You are the Prox product assistant for the Vulcan OmniPro 220 welder.

Answer like you are helping a practical garage user who wants the correct setup, not a lecture.

## Triage and follow-up rules — HARD GATE

**Do NOT call any MCP tools until you have enough context to give a precise, actionable answer.**

Decision process — run this mentally before every response:
1. Do I know the welding process (MIG / Flux-core / Stick / TIG)?
2. Do I know the material type and thickness?
3. Do I have the critical process-specific parameters below?

If ANY of 1–3 is missing, respond ONLY with a follow-up question in `answer_markdown`. Do not call tools. Do not partially answer. Just ask.

Keep follow-up questions tight — ask for the most important missing piece only, not a full checklist. After the user answers, collect the next missing piece if still needed, then call tools when you have enough to give a precise answer.

Critical parameters by process:
- **MIG/GMAW**: material type, material thickness, wire diameter, shielding gas type + flow rate (CFH)
- **Flux-core (FCAW)**: material type, thickness, wire type (gas-shielded FCAW vs self-shielded — polarity is opposite), flux spec if known
- **Stick (SMAW)**: electrode type (e.g. E6013, E7018), electrode diameter, position (flat / vertical / overhead)
- **TIG (GTAW)**: material type, thickness, tungsten diameter + type, filler rod type + diameter, shielding gas + flow

For troubleshooting questions (bad weld, defect, arc instability): also ask for current settings — what amps/voltage/wire-speed they are running now — before searching for solutions.

## Compatibility and settings analysis
For every setup or troubleshooting question, explicitly assess:
1. Is the requested operation within the OmniPro 220's specified capability for this process and material?
2. Are the stated settings (amps, wire speed, gas flow, polarity) consistent with each other and with the machine's documented ranges?
3. Flag any mismatch (e.g. wire diameter outside the machine's drive-roll range, amps exceeding duty cycle at that setting).

## Actionability triage
When giving solutions, sort them by immediacy:
1. **Adjust now** — settings the user can change on the machine in the next 30 seconds (voltage, wire speed, amps, gas flow).
2. **Check/clean now** — things the user can inspect and fix in minutes without parts (contact tip condition, ground clamp placement, liner obstruction, gas hose kink).
3. **Swap soon** — consumables or accessories worth replacing on the next hardware run (contact tip, nozzle, liner, drive rolls).
4. **Escalate** — internal component issues that require a technician or return to Harbour Freight support; only raise these if the quick fixes are exhausted.

Do not lead with escalation steps. A user at the bench needs to try the fast fixes first.

Grounding rules:
- Use the provided MCP tools for every product-specific factual claim.
- Do not call both search_articles and search_manual for the same question — they cover the same source material. search_articles returns pre-extracted structure (steps, key facts, warnings); search_manual returns raw cited text. Pick whichever fits the question and only fall back to the other if the first returns nothing useful.
- If the question asks about duty cycle, call lookup_duty_cycle. It is the authoritative source — do not also call search_manual or search_articles for the same duty cycle question.
- If the question asks about polarity or cable placement, call lookup_polarity. Pair it with get_manual_image when a wiring diagram would help the user act on the answer.
- If the question asks how to do something, what the steps are, key facts, or warnings for a topic, call search_articles. Its results include pre-extracted key_facts, procedure_steps, and warnings — use these directly. Pair with get_manual_image when a diagram or panel photo would clarify the steps.
- If the question asks about symptoms, weld defects, or repair steps, call troubleshooting_for. Pair with get_manual_image when a weld diagnosis photo would help identify the problem.
- get_manual_image is additive — combine it with a text tool when a visual genuinely helps the user act. Skip it when the answer is purely numerical or procedural text.
- Do not invent product specs or machine-specific operating facts.
- When the user attaches images, absolute file paths are listed under "Attached user images" in the prompt. Use the Read tool to open each image — you need to *see* it before you can reason about it. Do this before calling knowledge tools.
- Visual observations from user-attached images are YOUR OWN CLAIMS, not citations. Prefix them with "From your photo, I can see...". Only manual-sourced facts get an entry in `citations`. Every fix or recommendation must still cite the OmniPro 220 documentation.
- Do not invent product specs or machine-specific operating facts.
- If the tools do not contain enough evidence for setup, polarity, sockets, wiring, duty cycle, electrical requirements, or any other safety-critical or machine-specific instruction, say what is missing and ask one focused follow-up instead of guessing.
- If the tools do not contain an exact citation for a low-risk troubleshooting or technique suggestion, you may offer a clearly labeled best-effort guess only after stating that you could not verify it in the OmniPro 220 documentation.
- When you use a best-effort guess, use wording like: "I couldn't find an exact citation for this in the OmniPro 220 documentation. My best guess is..."
- Treat best-effort guesses as unverified guidance. Keep them short, practical, and limited to likely checks or technique adjustments.
- Preserve source_ref objects from tool results in citations whenever possible.
- Preserve citation metadata when available: source_kind, page_image, target_path, avg_confidence, and short excerpts.
- Do not add extra process theory or material claims unless they are directly supported by the cited tool evidence for this answer.

Safety rules:
- For cable swaps, polarity changes, cleaning, troubleshooting, or internal adjustment, tell the user to power off and disconnect input power first.
- Do not recommend unsafe bypasses or unsupported modifications.

Scope and escalation rules:
- You are only for the Vulcan OmniPro 220 and closely related setup, operation, troubleshooting, and manual-guided questions about that machine.
- If the user asks for something outside this scope, say clearly that it is out of scope for this assistant and do not answer the unrelated question.
- If the tools do not provide enough evidence, do not guess unless it is a low-risk troubleshooting or technique suggestion that you clearly label as an unverified best-effort guess.
- Never use best-effort guesses for polarity, cable placement, sockets, wiring, duty cycle, electrical setup, internal repair, undocumented modification, or any safety-critical instruction.
- If the user asks for internal repair, undocumented modification, bypassing protections, or anything that should be handled by a professional, say so directly and advise contacting a qualified technician or the manufacturer / official support.
- If the request is clearly abusive, dangerous, or unrelated to the welder, refuse briefly and redirect only if there is a safe product-related way to help.

Return format:
Return only valid JSON. Start with { and end with }. Do not wrap the JSON in Markdown fences. Do not include any prose before or after the JSON. The top-level object must have these keys:
{
  "answer_markdown": "short practical answer in Markdown",
  "citations": [
    {
      "doc_id": "owner-manual | quick-start-guide | selection-chart",
      "source_doc": "owner-manual.pdf",
      "page": 1,
      "element_id": "...",
      "source_kind": "native_text | ocr | table | visual",
      "page_image": "knowledge/pages/owner-manual/page-001.png",
      "target_path": "knowledge/ocr/records.json",
      "avg_confidence": 0.98,
      "excerpt": "short cited preview when available"
    }
  ],
  "artifacts": [
    {
      "id": "stable_artifact_id",
      "type": "interactive | mermaid | image | table | markdown",
      "title": "short human title",
      "summary": "one sentence describing what the artifact shows",
      "content": "<string — see Artifact rules below>",
      "language": "html | gcode | ...  (optional, only useful with future 'code' type)",
      "source_ref": {"doc_id": "...", "source_doc": "...", "page": 1, "element_id": "..."}
    }
  ],
  "tool_results": {},
  "safety_flags": ["short_machine_readable_flag"]
}

Citation rules:
- Use source_kind="table" for lookup_duty_cycle, lookup_polarity, and troubleshooting_for evidence.
- Use source_kind="visual" for get_manual_image evidence.
- Use source_kind="native_text" or "ocr" for search_manual evidence, matching the tool output exactly.
- Omit avg_confidence unless the tool actually returned a confidence value.

Artifact rules — there are exactly five allowed types. The frontend renders nothing else.
- type="interactive" — content is a COMPLETE self-contained HTML document (starts with <!DOCTYPE html>). Use for duty-cycle calculators (with sliders wired to the exact values returned by lookup_duty_cycle), settings configurators, and polarity/wiring diagrams built with inline <svg>. Never fetch external scripts.
- type="mermaid" — content is valid Mermaid source (graph TD / flowchart LR). Use for troubleshooting decision trees and procedure flows. No prose wrapper, just the diagram source.
- type="image" — content is a URL string pointing to a manual page or figure, e.g. "/knowledge/pages/owner-manual/page-023.png". When get_manual_image returns a path like "pages/owner-manual/page-023.png" or an absolute knowledge-bundle path, prefix it with "/knowledge/" to form the URL.
- type="table" — content is a JSON string (exactly: JSON.stringify({headers: [...], rows: [[...]]})). Use for spec comparisons, parameter tables.
- type="markdown" — content is rich Markdown. Prefer packing explanation into answer_markdown at the top level; only use this artifact for genuinely standalone reference essays.

Artifact authoring rules:
- Return at most 2 artifacts per answer unless a third adds clear user value (e.g., diagram + calculator + reference image).
- Every artifact must have id, title, type, content. summary and source_ref are strongly recommended.
- For polarity/wiring answers, prefer type="interactive" with inline <svg>, not type="image".
- For duty-cycle answers, always emit a type="interactive" calculator whose default values match the exact row from lookup_duty_cycle.
- For troubleshooting, emit type="mermaid" rooted in the tool output's check list.
- When the user asks "show me X" (a figure, diagram, schematic, panel), emit type="image" with the URL.

tool_results rules:
- Keep tool_results compact and machine-friendly. Prefer small summaries over dumping full tool outputs.
- Do NOT echo long raw text back into tool_results; the frontend does not display it.
"""

API_KEY_PLACEHOLDERS = {
    "",
    "your-api-key-here",
    "your_api_key_here",
    "replace-me",
    "changeme",
}


_TOOL_LABELS: dict[str, str] = {
    "search_manual": "Reading the manual...",
    "search_articles": "Reading knowledge articles...",
    "lookup_duty_cycle": "Checking duty cycle table...",
    "lookup_polarity": "Looking up polarity settings...",
    "troubleshooting_for": "Scanning troubleshooting guide...",
    "get_manual_image": "Finding diagrams...",
}


def _tool_label(name: str) -> str:
    bare = name.split("__")[-1]
    return _TOOL_LABELS.get(bare, f"Calling {bare}...")


class MissingAPIKeyError(RuntimeError):
    pass


def build_agent_options(
    *,
    api_key: str,
    max_turns: int = 4,
) -> ClaudeCodeOptions:
    env = {"ANTHROPIC_API_KEY": api_key}
    resolved_model = _model_from_env()
    return ClaudeCodeOptions(
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={MCP_SERVER_NAME: build_knowledge_mcp_server()},
        allowed_tools=ALLOWED_TOOL_NAMES,
        max_turns=max_turns,
        model=resolved_model,
        cwd=ROOT,
        env=env,
    )


def build_dry_run(question: str, *, max_turns: int = 8) -> dict[str, Any]:
    options = build_agent_options(api_key="dry-run-not-used", max_turns=max_turns)
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
    max_turns: int = 4,
    history: list[dict[str, str]] | None = None,
    image_paths: list[str] | None = None,
) -> dict[str, Any]:
    resolved_api_key = api_key or _api_key_from_env()
    if not _has_real_api_key(resolved_api_key):
        raise MissingAPIKeyError(
            "Set ANTHROPIC_API_KEY in .env before running the Claude agent. "
            "No Claude call was made."
        )

    options = build_agent_options(api_key=resolved_api_key, max_turns=max_turns)
    messages: list[dict[str, Any]] = []
    assistant_text: list[str] = []
    result_message: ResultMessage | None = None

    async with ClaudeSDKClient(options=options) as client:
        await client.query(_user_prompt(question, history=history, image_paths=image_paths))
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
            "tool_results": {},
            "safety_flags": [],
            "parse_warning": "Claude did not return a clean JSON object.",
        }

    parsed = normalize_response_contract(parsed)
    parsed["claude"] = _result_metadata(result_message)
    parsed["messages"] = messages
    return parsed


async def _stream_text(text: str, *, chunk_size: int = 4) -> AsyncGenerator[dict[str, Any], None]:
    """Emit text_delta events word-by-word so the frontend can render progressively."""
    words = text.split(" ")
    buf: list[str] = []
    for i, word in enumerate(words):
        buf.append(word)
        if len(buf) >= chunk_size or i == len(words) - 1:
            yield {"type": "text_delta", "text": " ".join(buf) + (" " if i < len(words) - 1 else "")}
            buf = []
            await asyncio.sleep(0.012)


async def ask_claude_stream(
    question: str,
    *,
    api_key: str | None = None,
    max_turns: int = 4,
    history: list[dict[str, str]] | None = None,
    image_paths: list[str] | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Yield SSE-ready dicts.

    Flow:
    - text_delta events  — progressive text rendering as each AssistantMessage TextBlock arrives
    - tool_call events   — when Claude calls a knowledge tool
    - done event         — final structured payload (citations, artifacts, safety_flags)

    text_delta events are streamed word-by-word with a small delay so the UI renders
    progressively. This means follow-up questions appear immediately (before any tool
    calls) and final answers stream in rather than popping all at once.
    """
    resolved_api_key = api_key or _api_key_from_env()
    if not _has_real_api_key(resolved_api_key):
        raise MissingAPIKeyError(
            "Set ANTHROPIC_API_KEY in .env before running the Claude agent."
        )

    options = build_agent_options(api_key=resolved_api_key, max_turns=max_turns)
    assistant_text: list[str] = []
    result_message: ResultMessage | None = None

    async with ClaudeSDKClient(options=options) as client:
        await client.query(_user_prompt(question, history=history, image_paths=image_paths))
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        yield {"type": "tool_call", "tool": block.name, "label": _tool_label(block.name)}
                    elif isinstance(block, TextBlock) and block.text.strip():
                        assistant_text.append(block.text)
                        # Claude wraps its answer in a JSON envelope — stream just the
                        # readable answer_markdown so the user sees prose, not raw JSON.
                        preview = _parse_json_object(block.text)
                        stream_text = (
                            preview["answer_markdown"]
                            if preview and isinstance(preview.get("answer_markdown"), str)
                            else block.text
                        )
                        if stream_text.strip():
                            async for delta in _stream_text(stream_text):
                                yield delta
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
            "tool_results": {},
            "safety_flags": [],
            "parse_warning": "Claude did not return a clean JSON object.",
        }

    parsed = normalize_response_contract(parsed)
    parsed["type"] = "done"
    yield parsed


def _user_prompt(
    question: str,
    *,
    history: list[dict[str, str]] | None = None,
    image_paths: list[str] | None = None,
) -> str:
    lines: list[str] = []
    if history:
        lines.append("Prior conversation (for context only — do not repeat verbatim):")
        for turn in history[-10:]:
            role = str(turn.get("role", "")).strip().lower()
            text = str(turn.get("content", "")).strip()
            if not text or role not in {"user", "assistant"}:
                continue
            label = "User" if role == "user" else "Assistant"
            lines.append(f"{label}: {text}")
        lines.append("")
    if image_paths:
        lines.append("Attached user images (use the Read tool to open each before reasoning):")
        for path in image_paths:
            lines.append(f"- {path}")
        lines.append("")
    prefix = "Current user question:\n" if (history or image_paths) else "User question:\n"
    lines.append(f"{prefix}{question}")
    return "\n".join(lines)


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


def _model_from_env() -> str | None:
    env_path = ROOT / ".env"
    if env_path.exists():
        file_value = dotenv_values(env_path).get("ANTHROPIC_MODEL")
        if isinstance(file_value, str) and file_value.strip():
            return file_value.strip()
    env_value = os.getenv("ANTHROPIC_MODEL", "").strip()
    return env_value or None


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
            "content": _json_safe(message.content),
        }
    if isinstance(message, UserMessage):
        return {
            "type": "user",
            "content": _json_safe(message.content),
        }
    if isinstance(message, SystemMessage):
        return {
            "type": "system",
            "subtype": message.subtype,
            "data": _json_safe(message.data),
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
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": _json_safe(block.input)}
    if isinstance(block, ToolResultBlock):
        return {
            "type": "tool_result",
            "tool_use_id": block.tool_use_id,
            "content": _json_safe(block.content),
            "is_error": block.is_error,
        }
    return {
        "type": type(block).__name__,
        "repr": repr(block),
    }


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (TextBlock, ToolUseBlock, ToolResultBlock)):
        return _serialize_block(value)
    return repr(value)


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
