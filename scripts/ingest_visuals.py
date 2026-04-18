"""
Ingest all manual page PNGs into visual_index_full.json using claude-haiku-4-5.

Usage:
    uv run python scripts/ingest_visuals.py
    uv run python scripts/ingest_visuals.py --dry-run
    uv run python scripts/ingest_visuals.py --limit 5
    uv run python scripts/ingest_visuals.py --page owner-manual/page-021.png
"""

import argparse
import base64
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent
PAGES_DIR = PROJECT_ROOT / "products/vulcan-omnipro-220/knowledge/pages"
INDEX_PATH = PROJECT_ROOT / "products/vulcan-omnipro-220/knowledge/images/visual_index.json"
OUTPUT_PATH = PROJECT_ROOT / "products/vulcan-omnipro-220/knowledge/images/visual_index_full.json"

DOC_ORDER = ["owner-manual", "quick-start-guide", "selection-chart"]

SYSTEM_PROMPT = (
    "You are extracting structured metadata from a welding machine manual page image.\n"
    "Return ONLY valid JSON, no markdown fences, no explanation.\n"
    "Only include text and facts visibly present in the image.\n"
    "Do not infer or add outside knowledge."
)

USER_PROMPT = (
    "Analyze this manual page and return JSON with exactly these fields:\n"
    "{\n"
    "  title: short descriptive title max 8 words,\n"
    "  description: 2-3 sentences describing what this page shows,\n"
    "  visible_text: array of important text strings visible in the image max 15 items,\n"
    "  query_terms: 6-10 terms a user would type to find this page\n"
    "}"
)

HAIKU_INPUT_COST_PER_M = 0.80
HAIKU_OUTPUT_COST_PER_M = 4.00


def collect_pngs() -> list[Path]:
    pngs: list[Path] = []
    for doc_id in DOC_ORDER:
        doc_dir = PAGES_DIR / doc_id
        if doc_dir.is_dir():
            pngs.extend(sorted(doc_dir.glob("*.png")))
    return pngs


def page_num_from_path(png: Path) -> int:
    m = re.search(r"(\d+)", png.stem)
    return int(m.group(1)) if m else 0


def build_entry(png: Path, claude_json: dict) -> dict:
    doc_id = png.parent.name
    page_num = page_num_from_path(png)
    visual_id = f"{doc_id}-page-{page_num:03d}"
    element_id = f"{doc_id}:page:{page_num:03d}"
    rel_path = png.relative_to(PROJECT_ROOT).as_posix()

    return {
        "visual_id": visual_id,
        "title": claude_json.get("title", ""),
        "description": claude_json.get("description", ""),
        "visible_text": claude_json.get("visible_text", []),
        "query_terms": claude_json.get("query_terms", []),
        "path": rel_path,
        "source_ref": {
            "doc_id": doc_id,
            "source_doc": f"{doc_id}.pdf",
            "page": page_num,
            "element_id": element_id,
        },
    }


def call_haiku(client, png: Path) -> tuple[dict, int, int]:
    image_b64 = base64.standard_b64encode(png.read_bytes()).decode()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": USER_PROMPT},
                ],
            }
        ],
    )
    raw = response.content[0].text.strip()
    # Strip markdown fences if the model ignores the no-fence instruction
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw).strip()
    parsed = json.loads(raw)
    return parsed, response.usage.input_tokens, response.usage.output_tokens


def sort_key(entry: dict) -> tuple[int, int]:
    doc_id = entry.get("source_ref", {}).get("doc_id", "")
    page = entry.get("source_ref", {}).get("page", 0)
    order = DOC_ORDER.index(doc_id) if doc_id in DOC_ORDER else 99
    return (order, page)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest manual PNGs into visual_index_full.json")
    parser.add_argument("--dry-run", action="store_true", help="Print paths/prompts, no API calls")
    parser.add_argument("--limit", type=int, default=None, metavar="N", help="Process at most N pages")
    parser.add_argument("--page", type=str, default=None, metavar="PATH", help="Process a single page, e.g. owner-manual/page-021.png")
    args = parser.parse_args()

    existing_index: list[dict] = json.loads(INDEX_PATH.read_text())
    existing_paths: set[str] = {e["path"] for e in existing_index}

    all_pngs = collect_pngs()

    if args.page:
        target = (PAGES_DIR / args.page).resolve()
        all_pngs = [p for p in all_pngs if p.resolve() == target]
        if not all_pngs:
            sys.exit(f"Page not found under pages/: {args.page}")

    to_process: list[Path] = [
        p for p in all_pngs
        if p.relative_to(PROJECT_ROOT).as_posix() not in existing_paths
    ]

    skipped = len(all_pngs) - len(to_process) if not args.page else 0

    if args.limit is not None:
        to_process = to_process[: args.limit]

    if args.dry_run:
        print(f"DRY RUN — {len(to_process)} pages would be processed\n")
        for png in to_process:
            rel = png.relative_to(PROJECT_ROOT).as_posix()
            print(f"  {rel}")
            print(f"  SYSTEM: {SYSTEM_PROMPT[:80]}...")
            print(f"  USER:   {USER_PROMPT[:80]}...")
            print()
        return

    if not to_process:
        print("Nothing to process — all pages already in index.")
        return

    import anthropic
    client = anthropic.Anthropic()

    new_entries: list[dict] = []
    total_input_tokens = 0
    total_output_tokens = 0
    errors = 0

    for i, png in enumerate(to_process, 1):
        rel = png.relative_to(PROJECT_ROOT).as_posix()
        print(f"[{i}/{len(to_process)}] {rel} ...", end=" ", flush=True)
        try:
            claude_json, inp, out = call_haiku(client, png)
            entry = build_entry(png, claude_json)
            new_entries.append(entry)
            total_input_tokens += inp
            total_output_tokens += out
            print(f"OK  ({inp}in/{out}out)")
        except json.JSONDecodeError as e:
            print(f"PARSE ERROR: {e}")
            errors += 1
        except Exception as e:
            print(f"ERROR: {e}")
            errors += 1

    merged = existing_index + new_entries
    merged.sort(key=sort_key)

    OUTPUT_PATH.write_text(json.dumps(merged, indent=2, ensure_ascii=False))

    cost = (
        total_input_tokens / 1_000_000 * HAIKU_INPUT_COST_PER_M
        + total_output_tokens / 1_000_000 * HAIKU_OUTPUT_COST_PER_M
    )

    print()
    print(f"Pages already in index (skipped): {skipped}")
    print(f"Pages processed:                  {len(new_entries)} (errors: {errors})")
    print(f"Total tokens used:                {total_input_tokens:,} input, {total_output_tokens:,} output")
    print(f"Estimated cost:                   ${cost:.4f}")
    print(f"Output written to:                {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
