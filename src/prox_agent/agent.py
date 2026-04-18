from __future__ import annotations

import base64
import json
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic
from dotenv import dotenv_values

from prox_agent.knowledge import ROOT, KnowledgeBase
from prox_agent.local_answer import answer_local
from prox_agent.response_contract import normalize_response_contract
from prox_agent.sdk_tools import (
    DUTY_CYCLE_SCHEMA,
    MANUAL_IMAGE_SCHEMA,
    POLARITY_SCHEMA,
    SEARCH_ARTICLES_SCHEMA,
    SEARCH_MANUAL_SCHEMA,
    TROUBLESHOOTING_SCHEMA,
)

_KB = KnowledgeBase()

# Separator between streamed prose and JSON metadata in Claude's response.
METADATA_MARKER = "<<METADATA>>"

ANTHROPIC_TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_manual",
        "description": "Search extracted text from the Vulcan OmniPro 220 manual and guides. Returns cited snippets and page images.",
        "input_schema": SEARCH_MANUAL_SCHEMA,
    },
    {
        "name": "search_articles",
        "description": "Search structured knowledge articles extracted from the owner manual. Returns full article objects with key_facts, procedure_steps, warnings, and source_refs. Use for setup procedures, how-to questions, section overviews, and safety information.",
        "input_schema": SEARCH_ARTICLES_SCHEMA,
    },
    {
        "name": "lookup_duty_cycle",
        "description": "Look up a verified duty-cycle row by process, input voltage, and amperage.",
        "input_schema": DUTY_CYCLE_SCHEMA,
    },
    {
        "name": "lookup_polarity",
        "description": "Look up the verified polarity setup and socket placement for a welding process.",
        "input_schema": POLARITY_SCHEMA,
    },
    {
        "name": "troubleshooting_for",
        "description": "Find verified troubleshooting checks for a symptom, optionally scoped to a welding process.",
        "input_schema": TROUBLESHOOTING_SCHEMA,
    },
    {
        "name": "get_manual_image",
        "description": "Find relevant manual page images, diagrams, charts, or product photos to surface as visual artifacts.",
        "input_schema": MANUAL_IMAGE_SCHEMA,
    },
]

SYSTEM_PROMPT = """You are the Prox product assistant for the Vulcan OmniPro 220 welder.

Answer like you are helping a practical garage user who wants the correct setup, not a lecture.

## Triage and follow-up rules — HARD GATE

**Do NOT call any tools until you have enough context to give a precise, actionable answer.**

Decision process — run this mentally before every response:
1. Do I know the welding process (MIG / Flux-core / Stick / TIG)?
2. Do I know the material type and thickness?
3. Do I have the critical process-specific parameters below?

If ANY of 1–3 is missing, respond ONLY with a follow-up question in your answer. Do not call tools. Do not partially answer. Just ask.

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
- Use the provided tools for every product-specific factual claim.
- Do not call both search_articles and search_manual for the same question — they cover the same source material. search_articles returns pre-extracted structure (steps, key facts, warnings); search_manual returns raw cited text. Pick whichever fits the question and only fall back to the other if the first returns nothing useful.
- If the question asks about duty cycle, call lookup_duty_cycle. It is the authoritative source — do not also call search_manual or search_articles for the same duty cycle question.
- If the question asks about polarity or cable placement, call lookup_polarity. Pair it with get_manual_image when a wiring diagram would help the user act on the answer.
- If the question asks how to do something, what the steps are, key facts, or warnings for a topic, call search_articles. Its results include pre-extracted key_facts, procedure_steps, and warnings — use these directly. Pair with get_manual_image when a diagram or panel photo would clarify the steps.
- If the question asks about symptoms, weld defects, or repair steps, call troubleshooting_for. Pair with get_manual_image when a weld diagnosis photo would help identify the problem.
- get_manual_image is additive — combine it with a text tool when a visual genuinely helps the user act. Skip it when the answer is purely numerical or procedural text.
- Do not invent product specs or machine-specific operating facts.
- When the user attaches images, they are already embedded in the message — reason about what you can see directly. Prefix visual observations with "From your photo, I can see...". Only manual-sourced facts go into citations.
- Visual observations from user-attached images are YOUR OWN CLAIMS, not citations. Only manual-sourced facts get an entry in citations.
- Do not invent product specs or machine-specific operating facts.
- If the tools do not contain enough evidence for setup, polarity, sockets, wiring, duty cycle, electrical requirements, or any other safety-critical or machine-specific instruction, say what is missing and ask one focused follow-up instead of guessing.
- If the tools do not contain an exact citation for a low-risk troubleshooting or technique suggestion, you may offer a clearly labeled best-effort guess only after stating that you could not verify it in the OmniPro 220 documentation.
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

## Return format — READ CAREFULLY

Output the answer as plain markdown prose FIRST. Do NOT wrap it in JSON or any other envelope.

After the complete answer text, output EXACTLY this line (copy verbatim, nothing else on the line):
<<METADATA>>

Then on the next line, output a single compact JSON object with ONLY these keys:
{"citations": [...], "artifacts": [...], "tool_results": {}, "safety_flags": [...]}

### Example

MIG welding on 1/8" mild steel typically runs at 130–160A on the OmniPro 220...

<<METADATA>>
{"citations": [{"source_doc": "owner-manual.pdf", "page": 14, "excerpt": "..."}], "artifacts": [], "tool_results": {}, "safety_flags": []}

---

Citation rules (for the citations array in the JSON):
- Use source_kind="table" for lookup_duty_cycle, lookup_polarity, and troubleshooting_for evidence.
- Use source_kind="visual" for get_manual_image evidence.
- Use source_kind="native_text" or "ocr" for search_manual evidence, matching the tool output exactly.
- Omit avg_confidence unless the tool actually returned a confidence value.
- Include: doc_id, source_doc, page, element_id, source_kind, page_image, target_path, excerpt where available.

Artifact rules — there are exactly five allowed types. The frontend renders nothing else.
- type="interactive" — content is a COMPLETE self-contained HTML document (starts with <!DOCTYPE html>). Use for duty-cycle calculators (with sliders wired to the exact values returned by lookup_duty_cycle), settings configurators, and polarity/wiring diagrams built with inline <svg>. Never fetch external scripts.
- type="mermaid" — content is valid Mermaid source (graph TD / flowchart LR). Use for troubleshooting decision trees and procedure flows. No prose wrapper, just the diagram source.
- type="image" — content is a URL string pointing to a manual page or figure, e.g. "/knowledge/pages/owner-manual/page-023.png". When get_manual_image returns a path like "pages/owner-manual/page-023.png" or an absolute knowledge-bundle path, prefix it with "/knowledge/" to form the URL.
- type="table" — content is a JSON string (exactly: JSON.stringify({headers: [...], rows: [[...]]})). Use for spec comparisons, parameter tables.
- type="markdown" — content is rich Markdown. Prefer packing explanation into the answer prose; only use this artifact for genuinely standalone reference essays.

Artifact authoring rules:
- Return at most 2 artifacts per answer unless a third adds clear user value.
- Every artifact must have id, title, type, content. summary and source_ref are strongly recommended.
- For polarity/wiring answers, prefer type="interactive" with inline <svg>, not type="image".
- For duty-cycle answers, always emit a type="interactive" calculator whose default values match the exact row from lookup_duty_cycle.
- For troubleshooting, emit type="mermaid" rooted in the tool output's check list.
- When the user asks "show me X" (a figure, diagram, schematic, panel), emit type="image" with the URL.

safety_flags rules:
- Short machine-readable strings, e.g. "power_off_before_cable_swap".
- Only include when the answer involves a genuinely hazardous operation.
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
    return _TOOL_LABELS.get(name, f"Calling {name}...")


class MissingAPIKeyError(RuntimeError):
    pass


async def _dispatch_tool(name: str, tool_input: dict[str, Any]) -> str:
    try:
        if name == "search_manual":
            result = _KB.search_manual(
                query=str(tool_input["query"]),
                limit=int(tool_input.get("limit", 5)),
            )
            return json.dumps({"query": tool_input["query"], "results": result})

        if name == "search_articles":
            result = _KB.search_articles(
                query=str(tool_input["query"]),
                limit=int(tool_input.get("limit", 3)),
            )
            return json.dumps({"query": tool_input["query"], "results": result})

        if name == "lookup_duty_cycle":
            result = _KB.lookup_duty_cycle(
                process=str(tool_input["process"]),
                input_voltage=str(tool_input["input_voltage"]),
                amperage=int(tool_input["amperage"]),
            )
            return json.dumps({"result": result, "found": result is not None})

        if name == "lookup_polarity":
            result = _KB.lookup_polarity(process=str(tool_input["process"]))
            return json.dumps({"result": result, "found": result is not None})

        if name == "troubleshooting_for":
            result = _KB.troubleshooting_for(
                symptom=str(tool_input["symptom"]),
                process=str(tool_input["process"]) if tool_input.get("process") else None,
            )
            return json.dumps({"results": result, "found": bool(result)})

        if name == "get_manual_image":
            result = _KB.get_manual_image(
                query=str(tool_input["query"]),
                limit=int(tool_input.get("limit", 3)),
            )
            return json.dumps({"query": tool_input["query"], "results": result})

        return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _build_api_messages(
    question: str,
    *,
    history: list[dict[str, str]] | None = None,
    image_paths: list[str] | None = None,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []

    if history:
        for turn in history[-10:]:
            role = str(turn.get("role", "")).strip().lower()
            content = str(turn.get("content", "")).strip()
            if not content or role not in {"user", "assistant"}:
                continue
            messages.append({"role": role, "content": content})

    user_content: list[dict[str, Any]] = []

    if image_paths:
        for path in image_paths:
            try:
                with open(path, "rb") as fh:
                    img_data = base64.standard_b64encode(fh.read()).decode("utf-8")
                ext = Path(path).suffix.lower()
                media_type = {
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png",
                    ".gif": "image/gif",
                    ".webp": "image/webp",
                }.get(ext, "image/jpeg")
                user_content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": img_data},
                })
            except Exception:
                pass

    user_content.append({"type": "text", "text": question})
    messages.append({"role": "user", "content": user_content})
    return messages


def _parse_response(accumulated_text: str) -> dict[str, Any]:
    """Split accumulated text on <<METADATA>> and return a normalized dict."""
    if METADATA_MARKER in accumulated_text:
        parts = accumulated_text.split(METADATA_MARKER, 1)
        answer_markdown = parts[0].strip()
        metadata_raw = parts[1].strip()
        metadata = _parse_json_object(metadata_raw) or {}
    else:
        # Fallback: try old pure-JSON format
        parsed = _parse_json_object(accumulated_text)
        if parsed:
            return parsed
        answer_markdown = accumulated_text.strip()
        metadata = {}

    return {
        "answer_markdown": answer_markdown,
        "citations": metadata.get("citations", []),
        "artifacts": metadata.get("artifacts", []),
        "tool_results": metadata.get("tool_results", {}),
        "safety_flags": metadata.get("safety_flags", []),
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
            "Set ANTHROPIC_API_KEY in .env before running the Claude agent."
        )

    accumulated: list[str] = []
    done_event: dict[str, Any] | None = None

    async for event in ask_claude_stream(
        question,
        api_key=resolved_api_key,
        max_turns=max_turns,
        history=history,
        image_paths=image_paths,
    ):
        if event.get("type") == "text_delta":
            accumulated.append(str(event.get("text", "")))
        elif event.get("type") == "done":
            done_event = event

    if done_event:
        return {k: v for k, v in done_event.items() if k != "type"}

    parsed = _parse_response("".join(accumulated))
    return normalize_response_contract(parsed)


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
    - tool_call events  — when Claude calls a knowledge tool (label shown in UI)
    - text_delta events — real tokens from Claude's answer, streamed as they arrive
    - tts_start event   — pre-computed speech text for parallel TTS (voice path only)
    - done event        — final structured payload (citations, artifacts, safety_flags)
    """
    resolved_api_key = api_key or _api_key_from_env()
    if not _has_real_api_key(resolved_api_key):
        raise MissingAPIKeyError(
            "Set ANTHROPIC_API_KEY in .env before running the Claude agent."
        )

    model = _model_from_env() or "claude-sonnet-4-6"
    client = AsyncAnthropic(api_key=resolved_api_key)
    messages = _build_api_messages(question, history=history, image_paths=image_paths)

    # Buffer to avoid emitting partial <<METADATA>> markers.
    # We hold back the last (marker_len - 1) chars until we know they're safe.
    marker_len = len(METADATA_MARKER)
    token_buffer = ""
    streamed_up_to = 0
    metadata_found = False
    full_text = ""

    for _turn in range(max_turns):
        async with client.messages.stream(
            model=model,
            system=SYSTEM_PROMPT,
            tools=ANTHROPIC_TOOLS,  # type: ignore[arg-type]
            messages=messages,  # type: ignore[arg-type]
            max_tokens=8192,
        ) as stream:
            async for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        yield {
                            "type": "tool_call",
                            "tool": block.name,
                            "label": _tool_label(block.name),
                        }

                elif event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta" and not metadata_found:
                        token = delta.text
                        token_buffer += token
                        full_text += token

                        # Flush safe portion (can't be start of a partial marker)
                        safe_end = len(token_buffer) - marker_len + 1

                        # Check if the marker has appeared in the buffered text
                        marker_idx = token_buffer.find(METADATA_MARKER)
                        if marker_idx != -1:
                            # Emit everything before the marker
                            to_emit = token_buffer[:marker_idx]
                            if to_emit:
                                yield {"type": "text_delta", "text": to_emit}
                            metadata_found = True
                            token_buffer = ""
                            streamed_up_to = 0
                        elif safe_end > streamed_up_to:
                            to_emit = token_buffer[streamed_up_to:safe_end]
                            if to_emit:
                                yield {"type": "text_delta", "text": to_emit}
                            streamed_up_to = safe_end

                    elif delta.type == "text_delta" and metadata_found:
                        full_text += delta.text

            final_msg = await stream.get_final_message()

        if final_msg.stop_reason == "end_turn":
            # Flush any remaining buffer (no marker found — emit the rest)
            if not metadata_found and token_buffer[streamed_up_to:]:
                remaining = token_buffer[streamed_up_to:]
                if remaining:
                    yield {"type": "text_delta", "text": remaining}
            break

        if final_msg.stop_reason == "tool_use":
            # Flush safe buffer before tool calls (no metadata mid-answer)
            if not metadata_found and token_buffer[streamed_up_to:]:
                remaining = token_buffer[streamed_up_to:]
                if remaining:
                    yield {"type": "text_delta", "text": remaining}
            token_buffer = ""
            streamed_up_to = 0

            # Serialize assistant turn and execute tools
            assistant_content = _blocks_to_api(final_msg.content)
            messages.append({"role": "assistant", "content": assistant_content})

            tool_results = []
            for block in final_msg.content:
                if block.type == "tool_use":
                    result_text = await _dispatch_tool(block.name, block.input)  # type: ignore[arg-type]
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                    })

            messages.append({"role": "user", "content": tool_results})
        else:
            break

    parsed = _parse_response(full_text)
    parsed = normalize_response_contract(parsed)

    # Emit tts_start before done so voice endpoint can start TTS in parallel.
    answer_md = str(parsed.get("answer_markdown") or "")
    safety_flags = list(parsed.get("safety_flags") or [])
    if answer_md.strip():
        from prox_agent.voice import prepare_for_speech
        spoken, instructions = prepare_for_speech(answer_md, safety_flags)
        if spoken.strip():
            yield {"type": "tts_start", "spoken": spoken, "instructions": instructions}

    parsed["type"] = "done"
    yield parsed


def _blocks_to_api(content: list[Any]) -> list[dict[str, Any]]:
    """Convert Anthropic SDK content blocks to plain dicts for the messages API."""
    result = []
    for block in content:
        if block.type == "text":
            result.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            result.append({
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            })
    return result


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
            value = json.loads(text[start: end + 1])
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None
