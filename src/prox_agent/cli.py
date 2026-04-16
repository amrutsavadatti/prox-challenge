from __future__ import annotations

import argparse
import json
from typing import Any

from prox_agent.knowledge import KnowledgeBase
from prox_agent.local_answer import answer_local


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def smoke() -> None:
    kb = KnowledgeBase()
    print("Knowledge bundle loaded")
    print_json(kb.manifest["counts"])

    duty = kb.lookup_duty_cycle("MIG", "240V", 200)
    assert duty is not None
    assert duty["duty_cycle_percent"] == 25
    print("\nDuty cycle smoke: MIG 200A on 240V")
    print_json(duty)

    polarity = kb.lookup_polarity("TIG")
    assert polarity is not None
    assert polarity["ground_clamp_socket"] == "Positive (+)"
    assert polarity["torch_or_wire_feed_socket"] == "Negative (-)"
    print("\nPolarity smoke: TIG")
    print_json(polarity)

    troubleshooting = kb.troubleshooting_for("porosity holes in flux cored weld", process="Flux-Cored")
    assert troubleshooting
    print("\nTroubleshooting smoke: porosity in flux-cored weld")
    print_json(troubleshooting[0])

    visuals = kb.get_manual_image("TIG polarity ground clamp socket")
    assert visuals
    print("\nVisual smoke: TIG polarity")
    print_json(visuals[0])

    search = kb.search_manual("porosity flux-cored polarity shielding gas", limit=3)
    assert search
    print("\nSearch smoke: porosity flux-cored")
    print_json(search)

    assert kb.ocr_records
    print("\nOCR smoke: records loaded")
    print_json(
        {
            "ocr_records": len(kb.ocr_records),
            "sample": kb.ocr_records[0],
        }
    )

    selection = kb.search_manual("how to choose welder selection chart", limit=5)
    assert selection
    assert any(result["doc_id"] == "selection-chart" for result in selection)
    print("\nOCR smoke: selection chart search")
    print_json(selection)

    quick_start = kb.search_manual("stick cable setup electrode holder positive terminal", limit=5)
    assert quick_start
    assert any(result["doc_id"] == "quick-start-guide" for result in quick_start)
    print("\nOCR smoke: quick-start cable setup search")
    print_json(quick_start)

    front_panel_visual = kb.get_manual_image("front panel spot timer inductance run in wfs")
    assert front_panel_visual
    assert front_panel_visual[0]["visual_id"] == "front-panel-controls"
    print("\nVisual smoke: front panel controls")
    print_json(front_panel_visual[0])

    wire_loading_visual = kb.get_manual_image("quick start wire spool loading feed guides")
    assert wire_loading_visual
    assert wire_loading_visual[0]["visual_id"] == "quick-start-wire-loading"
    print("\nVisual smoke: quick-start wire loading")
    print_json(wire_loading_visual[0])

    front_panel_ocr = kb.search_manual("spot timer", limit=5)
    assert front_panel_ocr
    assert any(
        result["doc_id"] == "owner-manual" and result["source_kind"] == "ocr" and result["page"] == 21
        for result in front_panel_ocr
    )
    print("\nOCR smoke: front panel embedded image labels")
    print_json(front_panel_ocr)

    spot_timer_answer = answer_local("What does spot timer do?")
    assert spot_timer_answer["citations"]
    assert any(citation["page"] == 21 for citation in spot_timer_answer["citations"])
    assert "timer for spot welding" in spot_timer_answer["answer_markdown"].lower()
    assert any(artifact["title"] == "Front Panel Controls" for artifact in spot_timer_answer["artifacts"])
    assert any(
        result["source_kind"] == "ocr" and result["page"] == 21
        for result in spot_timer_answer["tool_results"]["search_manual"]
    )
    print("\nLocal answer smoke: user-style controls question")
    print_json(spot_timer_answer)


def main() -> None:
    parser = argparse.ArgumentParser(description="Local knowledge tools for the Prox challenge.")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("smoke", help="Run deterministic smoke checks.")

    ask_parser = subparsers.add_parser("ask", help="Ask a question using local deterministic tools only.")
    ask_parser.add_argument("question")

    search_parser = subparsers.add_parser("search", help="Search manual pages.")
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=int, default=5)

    duty_parser = subparsers.add_parser("duty-cycle", help="Look up duty cycle.")
    duty_parser.add_argument("--process", required=True)
    duty_parser.add_argument("--voltage", required=True)
    duty_parser.add_argument("--amperage", required=True, type=int)

    polarity_parser = subparsers.add_parser("polarity", help="Look up process polarity.")
    polarity_parser.add_argument("--process", required=True)

    image_parser = subparsers.add_parser("image", help="Find relevant manual visuals.")
    image_parser.add_argument("query")
    image_parser.add_argument("--limit", type=int, default=3)

    args = parser.parse_args()
    kb = KnowledgeBase()

    if args.command == "smoke":
        smoke()
    elif args.command == "ask":
        print_json(answer_local(args.question))
    elif args.command == "search":
        print_json(kb.search_manual(args.query, limit=args.limit))
    elif args.command == "duty-cycle":
        print_json(kb.lookup_duty_cycle(args.process, args.voltage, args.amperage))
    elif args.command == "polarity":
        print_json(kb.lookup_polarity(args.process))
    elif args.command == "image":
        print_json(kb.get_manual_image(args.query, limit=args.limit))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
