"""Generate eval questions for the Prox agent by expanding concept specs via Claude Haiku.

Reads:   eval/concepts.json
Writes:  eval/questions.jsonl  (append, resume-safe by concept_id)
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time

from anthropic import Anthropic
from dotenv import load_dotenv

REPO = pathlib.Path(__file__).resolve().parents[1]
CONCEPTS_PATH = REPO / "eval" / "concepts.json"
OUT_PATH = REPO / "eval" / "questions.jsonl"
MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You generate test questions for a multimodal agent that answers questions about the Vulcan OmniPro 220 welder using only three source PDFs: owner-manual.pdf (48 pages), quick-start-guide.pdf (2 pages), and selection-chart.pdf (1 page, image-only, OCR-backed).

Your output is machine-consumed. Emit ONLY valid JSONL — one JSON object per line, no prose, no markdown, no code fences.

Each line must follow this schema exactly:
{"concept_id": str, "n": int, "question": str, "axes": {...}, "expected_artifact": str, "expected_citations": [str, ...], "expected_behavior": "answer" | "clarify" | "refuse" | "correct-premise", "notes": str}

Hard rules:
- Every question must be answerable ONLY by consulting the specified corpus. No general welding trivia.
- Do not invent product variants (OmniPro 180/300, etc.) unless the concept explicitly calls for it (C6.3).
- `expected_citations` entries use the form "doc_id:page" with doc_id in {owner-manual, quick-start-guide, selection-chart}. These are best-guess targets; they will be verified downstream.
- If the concept is ambiguity/clarification, expected_behavior must be "clarify".
- If the concept is false-premise, expected_behavior must be "correct-premise" or "refuse".
- Vary phrasing: half garage-hobbyist voice ("my MIG keeps porositying out"), half precise technical voice.
- For multimodal concepts, include a [image: short description] placeholder inside the question text.
- Keep each question under 60 words.
- Do not repeat phrasings within a batch.
"""


def build_user_prompt(concept: dict, n: int) -> str:
    return f"""Generate {n} distinct test questions for this concept.

CONCEPT_ID: {concept['id']}
NAME: {concept['name']}
TIER: {concept['tier']}
WHAT_IT_TESTS: {concept['tests']}
REQUIRED_CROSS_REFS: {concept['cross_refs']}
EXPECTED_ARTIFACT: {concept['artifact']}
EXPECTED_BEHAVIOR: {concept['expected_behavior']}
VARIATION_AXES: {concept['axes']}
EVAL_RUBRIC: {concept['rubric']}
SEED_EXAMPLES:
{json.dumps(concept['seeds'], indent=2)}

Set "n" on each output line to the 1-indexed sequence number within this batch (1..{n}).
Set "concept_id" to exactly "{concept['id']}".
"""


def parse_jsonl(text: str) -> list[dict]:
    rows: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def load_done(out_path: pathlib.Path) -> set[str]:
    if not out_path.exists():
        return set()
    done: set[str] = set()
    for line in out_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            done.add(json.loads(line)["concept_id"])
        except (json.JSONDecodeError, KeyError):
            continue
    return done


def generate_for(client: Anthropic, concept: dict, n: int) -> list[dict]:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": build_user_prompt(concept, n)}],
    )
    text = resp.content[0].text if resp.content else ""
    rows = parse_jsonl(text)
    for row in rows:
        row.setdefault("concept_id", concept["id"])
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=15, help="questions per concept")
    parser.add_argument("--only", type=str, default=None, help="comma-separated concept_ids to run")
    parser.add_argument("--reset", action="store_true", help="truncate questions.jsonl before running")
    parser.add_argument("--dry-run", action="store_true", help="print plan without calling the API")
    args = parser.parse_args()

    load_dotenv(REPO / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: ANTHROPIC_API_KEY not set (checked repo .env)", file=sys.stderr)
        return 1

    concepts = json.loads(CONCEPTS_PATH.read_text())
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        concepts = [c for c in concepts if c["id"] in wanted]

    OUT_PATH.parent.mkdir(exist_ok=True)
    if args.reset and OUT_PATH.exists():
        OUT_PATH.unlink()
    done = load_done(OUT_PATH)

    to_run = [c for c in concepts if c["id"] not in done]
    print(f"concepts total: {len(concepts)}  already done: {len(done)}  to run: {len(to_run)}  n per concept: {args.n}")

    if args.dry_run:
        for c in to_run:
            print(f"  - {c['id']}  {c['name']}")
        return 0

    client = Anthropic()
    total_rows = 0
    with OUT_PATH.open("a") as f:
        for i, concept in enumerate(to_run, 1):
            print(f"[{i}/{len(to_run)}] {concept['id']}  {concept['name']}")
            try:
                rows = generate_for(client, concept, args.n)
            except Exception as e:
                print(f"  ! failed: {e}", file=sys.stderr)
                continue
            if not rows:
                print("  ! no valid rows parsed, skipping", file=sys.stderr)
                continue
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            total_rows += len(rows)
            print(f"  ok  {len(rows)} rows  (running total: {total_rows})")
            time.sleep(0.3)

    print(f"done. wrote {total_rows} new rows to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
