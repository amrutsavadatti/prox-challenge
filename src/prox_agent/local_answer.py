from __future__ import annotations

import re
from typing import Any

from prox_agent.knowledge import KnowledgeBase
from prox_agent.response_contract import (
    citation_from_search_result,
    citation_from_source_ref,
    duty_cycle_artifact,
    manual_image_artifact as build_manual_image_artifact,
    normalize_response_contract,
)


PROCESS_PATTERNS = [
    ("Flux-Cored", re.compile(r"\b(flux[- ]?cored|fcaw|gasless)\b", re.IGNORECASE)),
    ("MIG", re.compile(r"\b(mig|gmaw|solid[- ]?core)\b", re.IGNORECASE)),
    ("TIG", re.compile(r"\b(tig|gtaw|tungsten)\b", re.IGNORECASE)),
    ("Stick", re.compile(r"\b(stick|smaw|electrode holder)\b", re.IGNORECASE)),
]

CONTROL_SETTING_PATTERNS = [
    (
        "spot_timer",
        re.compile(r"\bspot[- ]?timer\b", re.IGNORECASE),
        {
            "title": "Spot Timer",
            "answer_markdown": (
                "Spot Timer sets a timer for spot welding. It is one of the front-panel optional settings."
            ),
            "search_query": "spot timer front panel optional settings",
        },
    ),
    (
        "inductance",
        re.compile(r"\binductance\b", re.IGNORECASE),
        {
            "title": "Inductance",
            "answer_markdown": (
                "Inductance adjusts arc length behavior. Increase it for a more fluid puddle and flatter bead; "
                "decrease it for a colder puddle."
            ),
            "search_query": "inductance front panel optional settings",
        },
    ),
    (
        "run_in_wfs",
        re.compile(r"\brun[- ]?in\b.*\bwfs\b|\bwfs\b.*\brun[- ]?in\b", re.IGNORECASE),
        {
            "title": "Run-In WFS",
            "answer_markdown": (
                "Run-In WFS adjusts wire speed before the wire contacts the workpiece. It is set as a percentage "
                "of the pre-set wire feed speed."
            ),
            "search_query": "run in wfs front panel optional settings",
        },
    ),
]


def answer_local(question: str) -> dict[str, Any]:
    kb = KnowledgeBase()
    lowered = question.lower()
    response: dict[str, Any] = {
        "question": question,
        "answer_markdown": "",
        "citations": [],
        "artifacts": [],
        "tool_results": {},
        "safety_flags": [],
    }

    if "duty cycle" in lowered:
        duty = _answer_duty_cycle(kb, question)
        if duty:
            response.update(duty)
            return normalize_response_contract(response)

    if any(term in lowered for term in ["polarity", "socket", "ground clamp", "which socket", "cable"]):
        polarity = _answer_polarity(kb, question)
        if polarity:
            response.update(polarity)
            return normalize_response_contract(response)

    if any(term in lowered for term in ["porosity", "holes", "cavities", "troubleshoot", "spatter"]):
        troubleshooting = _answer_troubleshooting(kb, question)
        if troubleshooting:
            response.update(troubleshooting)
            return normalize_response_contract(response)

    controls = _answer_control_setting(kb, question)
    if controls:
        response.update(controls)
        return normalize_response_contract(response)

    search_results = kb.search_manual(question, limit=5)
    images = kb.get_manual_image(question, limit=3)
    response["answer_markdown"] = (
        "I found the most relevant manual evidence below. "
        "This local CLI does retrieval only; the Claude agent will turn these results into a conversational answer."
    )
    response["tool_results"] = {
        "search_manual": search_results,
        "get_manual_image": images,
    }
    response["citations"] = _citations_from_search(search_results)
    response["artifacts"] = [build_manual_image_artifact(image) for image in images]
    return normalize_response_contract(response)


def _answer_duty_cycle(kb: KnowledgeBase, question: str) -> dict[str, Any] | None:
    process = _extract_process(question)
    voltage = _extract_voltage(question)
    amperage = _extract_amperage(question)
    if not process or not voltage or amperage is None:
        return {
            "answer_markdown": (
                "I need the welding process, input voltage, and amperage to look up duty cycle. "
                "Example: `MIG at 200A on 240V`."
            ),
            "tool_results": {
                "search_manual": kb.search_manual(question, limit=5),
            },
        }

    result = kb.lookup_duty_cycle(process, voltage, amperage)
    if result is None:
        return {
            "answer_markdown": f"I could not find a duty-cycle row for {process} at {amperage}A on {voltage}.",
            "tool_results": {
                "search_manual": kb.search_manual(question, limit=5),
            },
        }

    source = result["source_ref"]
    minutes = ""
    if "minutes_welding_per_10" in result and "minutes_resting_per_10" in result:
        minutes = (
            f" That means {result['minutes_welding_per_10']} minutes welding and "
            f"{result['minutes_resting_per_10']} minutes resting in each 10-minute period."
        )
    match_note = ""
    if result.get("match_type") == "nearest_available_amperage":
        match_note = (
            f" I did not find an exact {result['requested_amperage']}A row, so this is the nearest "
            f"available row at {result['amperage']}A."
        )
    return {
        "answer_markdown": (
            f"{process} at {result['amperage']}A on {result['input_voltage']} is rated for "
            f"{result['duty_cycle_percent']}% duty cycle.{minutes}{match_note}"
        ),
        "citations": [citation_from_source_ref(source, source_kind="table")],
        "artifacts": [duty_cycle_artifact(result, process)],
        "tool_results": {
            "lookup_duty_cycle": result,
            "search_manual": kb.search_manual(question, limit=3),
        },
    }


def _answer_polarity(kb: KnowledgeBase, question: str) -> dict[str, Any] | None:
    process = _extract_process(question)
    if not process:
        return None
    result = kb.lookup_polarity(process)
    if result is None:
        return None
    images = kb.get_manual_image(f"{process} polarity ground clamp socket", limit=2)
    safety_flags = ["power_off_before_changing_leads"]
    return {
        "answer_markdown": (
            f"For {process}, use {result['polarity']} ({result['polarity_expanded']}). "
            f"Put the ground clamp cable in the {result['ground_clamp_socket']} socket and "
            f"the {result['wire_or_mode']} cable in the {result['torch_or_wire_feed_socket']} socket. "
            "Turn the welder off and unplug it before changing cable setup."
        ),
        "citations": [citation_from_source_ref(result["source_ref"], source_kind="table")],
        "artifacts": [build_manual_image_artifact(image) for image in images],
        "tool_results": {
            "lookup_polarity": result,
            "get_manual_image": images,
        },
        "safety_flags": safety_flags,
    }


def _answer_troubleshooting(kb: KnowledgeBase, question: str) -> dict[str, Any] | None:
    process = _extract_process(question)
    matches = kb.troubleshooting_for(question, process=process)
    if not matches:
        return None
    guide = matches[0]
    images = []
    for image_path, source_ref in zip(guide.get("page_images", []), guide.get("source_refs", []), strict=False):
        images.append(
            build_manual_image_artifact(
                {
                    "title": f"{source_ref['source_doc']} p.{source_ref['page']}",
                    "path": image_path,
                    "source_ref": source_ref,
                    "description": f"Relevant troubleshooting page from {source_ref['source_doc']} page {source_ref['page']}.",
                }
            )
        )
    checks = "\n".join(f"- {check['cause']}: {check['solution']}" for check in guide["checks"])
    return {
        "answer_markdown": (
            "For porosity, check these items first:\n"
            f"{checks}\n\n"
            "Turn the welder off and disconnect power before adjusting, cleaning, or repairing the unit."
        ),
        "citations": [citation_from_source_ref(source_ref, source_kind="table") for source_ref in guide["source_refs"]],
        "artifacts": images,
        "tool_results": {
            "troubleshooting_for": guide,
            "search_manual": kb.search_manual(question, limit=5),
        },
        "safety_flags": ["power_off_before_adjusting_cleaning_or_repairing"],
    }


def _answer_control_setting(kb: KnowledgeBase, question: str) -> dict[str, Any] | None:
    for _, pattern, config in CONTROL_SETTING_PATTERNS:
        if not pattern.search(question):
            continue

        primary_results = kb.search_manual(question, limit=5)
        support_results = kb.search_manual(config["search_query"], limit=5)
        search_results = _merge_search_results(primary_results, support_results)
        images = kb.get_manual_image(config["search_query"], limit=3)

        citations = _citations_from_search(search_results)
        if not citations:
            citations = [
                {
                    "doc_id": "owner-manual",
                    "source_doc": "owner-manual.pdf",
                    "page": 21,
                    "element_id": "owner-manual:page:021",
                }
            ]

        front_panel_images = [image for image in images if image.get("visual_id") == "front-panel-controls"]
        if front_panel_images:
            ordered_images = front_panel_images[:1]
        else:
            ordered_images = images[:1]

        return {
            "answer_markdown": config["answer_markdown"],
            "citations": citations,
            "artifacts": [build_manual_image_artifact(image) for image in ordered_images],
            "tool_results": {
                "search_manual": search_results,
                "get_manual_image": ordered_images,
            },
        }

    return None


def _merge_search_results(*result_sets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for results in result_sets:
        for result in results:
            key = (result["source_doc"], result["page"], result["element_id"])
            if key in seen:
                continue
            seen.add(key)
            merged.append(result)
    return sorted(
        merged,
        key=lambda result: (
            0 if result["page"] == 21 else 1,
            0 if result["source_kind"] == "native_text" else 1,
            -float(result["score"]),
        ),
    )[:5]


def _extract_process(question: str) -> str | None:
    for process, pattern in PROCESS_PATTERNS:
        if pattern.search(question):
            return process
    return None


def _extract_voltage(question: str) -> str | None:
    match = re.search(r"\b(120|240)\s*(v|vac|volt|volts)?\b", question, re.IGNORECASE)
    if not match:
        return None
    return f"{match.group(1)} VAC"


def _extract_amperage(question: str) -> int | None:
    match = re.search(r"\b(\d{2,3})\s*a\b", question, re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def _citations_from_search(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for result in results:
        key = (result["source_doc"], result["page"])
        if key in seen:
            continue
        seen.add(key)
        citations.append(citation_from_search_result(result))
    return citations
