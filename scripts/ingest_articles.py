"""
Ingest owner-manual sections into structured article JSON files via Claude Sonnet.

Usage:
    uv run python scripts/ingest_articles.py
    uv run python scripts/ingest_articles.py --dry-run
    uv run python scripts/ingest_articles.py --show-clusters
    uv run python scripts/ingest_articles.py --limit 3
    uv run python scripts/ingest_articles.py --cluster safety-precautions
"""

import argparse
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent
SECTIONS_FILE = PROJECT_ROOT / "products/vulcan-omnipro-220/knowledge/sections/owner-manual.json"
ARTICLES_DIR = PROJECT_ROOT / "products/vulcan-omnipro-220/knowledge/articles"

SECTION_KEYWORDS = {
    "SECTION", "CHAPTER", "SAFETY", "INSTALLATION", "OPERATION",
    "MAINTENANCE", "TROUBLESHOOTING", "SPECIFICATIONS", "WARRANTY",
}

# Inline safety callouts that appear mid-procedure — never start a new cluster
INLINE_CALLOUTS = {"IMPORTANT", "DANGER", "WARNING", "NOTE", "CAUTION"}

MAX_CLUSTER_WORDS = 600
MAX_CLUSTER_PAGES = 5

SONNET_INPUT_COST_PER_M = 3.00
SONNET_OUTPUT_COST_PER_M = 15.00

SYSTEM_PROMPT = (
    "You are extracting structured knowledge from a Vulcan OmniPro 220 \n"
    "industrial welder owner manual.\n"
    "Return ONLY valid JSON, no markdown fences, no explanation.\n"
    "Only include facts explicitly stated in the source text.\n"
    "Do not infer, embellish, or add knowledge from outside this manual.\n"
    "If a step has a safety requirement, include it verbatim."
)

USER_PROMPT_TEMPLATE = """\
Extract a structured knowledge article from these manual pages.
Return JSON with exactly these fields:
{{
  article_id: slugified title string,
  title: clear descriptive title for this topic max 8 words,
  summary: 2-3 sentences explaining what this section covers,
  key_facts: [
    array of single-sentence facts explicitly stated in the text,
    max 15 words each, max 12 facts
  ],
  procedure_steps: [
    numbered steps if this section describes a procedure,
    empty array if not procedural content
  ],
  warnings: [
    any safety warnings or cautions stated verbatim,
    empty array if none
  ],
  related_topics: [
    2-4 topic slugs this article connects to,
    e.g. mig-polarity-setup, duty-cycle-specs
  ],
  source_refs: [
    {{ doc_id: owner-manual, page: N, element_id: ... }}
    for each page in the cluster
  ],
  query_terms: [
    8-12 terms or phrases a user would type to find this topic
  ]
}}

Source pages:
{page_text}"""


def _first_line(page: dict) -> str:
    block_text = page["blocks"][0]["text"] if page["blocks"] else page["text"]
    return block_text.split("\n")[0].strip()


def is_continuation(first_line: str) -> bool:
    """True when this line is a mid-document continuation, not a new section."""
    # Numbered step: "27. To check...", "4.  Turn..."
    if re.match(r"^\d+[\.\)]\s", first_line):
        return True
    # Lettered sub-step: "d. Optional settings", "e. Optional..."
    if re.match(r"^[a-z][\.\)]\s", first_line):
        return True
    # Inline safety callout (standalone or leading): "DANGER", "IMPORTANT Securely hold..."
    if re.match(r"^(IMPORTANT|DANGER|WARNING|NOTE|CAUTION)\b", first_line):
        return True
    # Non-word / trademark first character: "®", "©", "™"
    if re.match(r"^[®©™\W\d]", first_line):
        return True
    return False


def is_major_heading(first_line: str) -> bool:
    """True when this line signals a genuine top-level section break."""
    if not first_line or is_continuation(first_line):
        return False
    # All-caps section title (e.g. "SPECIFICATIONS", "MAINTENANCE")
    if first_line.isupper():
        return True
    # Contains a known major-section keyword
    if any(kw in first_line.upper() for kw in SECTION_KEYWORDS):
        return True
    return False


def make_slug(pages: list[dict]) -> str:
    """Derive slug from the first non-continuation heading in the cluster."""
    for page in pages:
        block_text = page["blocks"][0]["text"] if page["blocks"] else page["text"]
        lines = [l.strip() for l in block_text.split("\n") if l.strip()]
        for line in lines:
            if is_continuation(line):
                break  # rest of this page is also continuation content
            # Strip parentheticals and apostrophes, then take first 4 words
            cleaned = re.sub(r"\([^)]*\)", "", line)
            cleaned = re.sub(r"[\u2018\u2019\u02bc']", "", cleaned)
            words = re.sub(r"[^a-zA-Z0-9\s]", " ", cleaned).split()
            if len(words) < 2 and len(lines) > 1:
                # Single-word heading — grab next line too for a richer slug
                next_cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", lines[1]).split()
                words = (words + next_cleaned)[:4]
            else:
                words = words[:4]
            slug = "-".join(w.lower() for w in words if w)
            if slug:
                return slug
    return f"page-{pages[0]['page']}"


def cluster_pages(pages: list[dict]) -> list[dict]:
    """Return list of cluster dicts with keys: pages, slug, total_words."""
    clusters: list[list[dict]] = []
    current: list[dict] = []
    current_words = 0

    for page in pages:
        line = _first_line(page)
        cont = is_continuation(line)

        if current and not cont:
            # Only non-continuation pages can trigger a cluster break
            hit_heading = is_major_heading(line)
            hit_word_limit = (current_words + page["word_count"]) > MAX_CLUSTER_WORDS
            hit_page_limit = len(current) >= MAX_CLUSTER_PAGES

            if hit_heading or hit_word_limit or hit_page_limit:
                clusters.append(current)
                current = []
                current_words = 0

        # Continuation pages always attach to whatever is current (even if it tips
        # over the word limit), so they never become orphan single-page clusters.
        current.append(page)
        current_words += page["word_count"]

    if current:
        clusters.append(current)

    result = []
    seen_slugs: dict[str, int] = {}
    for group in clusters:
        slug = make_slug(group)
        if slug in seen_slugs:
            seen_slugs[slug] += 1
            slug = f"{slug}-{seen_slugs[slug]}"
        else:
            seen_slugs[slug] = 1
        total_words = sum(p["word_count"] for p in group)
        result.append({"pages": group, "slug": slug, "total_words": total_words})

    return result


def format_page_text(pages: list[dict]) -> str:
    parts = []
    for page in pages:
        parts.append(f"=== PAGE {page['page']} ===\n{page['text']}")
    return "\n\n".join(parts)


def build_user_prompt(pages: list[dict]) -> str:
    return USER_PROMPT_TEMPLATE.format(page_text=format_page_text(pages))


def print_cluster_plan(clusters: list[dict]) -> None:
    for i, cl in enumerate(clusters, 1):
        pages = cl["pages"]
        page_range = (
            f"page {pages[0]['page']}"
            if len(pages) == 1
            else f"pages {pages[0]['page']}-{pages[-1]['page']}"
        )
        exists_mark = " [exists]" if (ARTICLES_DIR / f"{cl['slug']}.json").exists() else ""
        print(f"Cluster {i:2d}: {page_range} ({cl['total_words']} words) → {cl['slug']}.json{exists_mark}")


def call_sonnet(client, pages: list[dict]) -> tuple[dict, int, int]:
    user_prompt = build_user_prompt(pages)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw).strip()
    parsed = json.loads(raw)
    return parsed, response.usage.input_tokens, response.usage.output_tokens


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest owner manual into article JSONs via Sonnet")
    parser.add_argument("--dry-run", action="store_true", help="Print plan + prompt for cluster 1; no API calls")
    parser.add_argument("--show-clusters", action="store_true", help="Print cluster plan only; no API calls")
    parser.add_argument("--limit", type=int, default=None, metavar="N", help="Process only first N clusters")
    parser.add_argument("--cluster", type=str, default=None, metavar="SLUG", help="Process one cluster by slug")
    args = parser.parse_args()

    pages: list[dict] = json.loads(SECTIONS_FILE.read_text())
    clusters = cluster_pages(pages)

    if args.show_clusters:
        print_cluster_plan(clusters)
        return

    if args.dry_run:
        print_cluster_plan(clusters)
        print()
        if clusters:
            first = clusters[0]
            print(f"--- Prompt for cluster 1 ({first['slug']}) ---")
            print(f"SYSTEM:\n{SYSTEM_PROMPT}\n")
            print(f"USER:\n{build_user_prompt(first['pages'])}")
        return

    # Filter to a single cluster if requested
    if args.cluster:
        target = [cl for cl in clusters if cl["slug"] == args.cluster]
        if not target:
            available = ", ".join(cl["slug"] for cl in clusters)
            sys.exit(f"Cluster '{args.cluster}' not found.\nAvailable: {available}")
        clusters = target

    # Apply --limit
    if args.limit is not None:
        clusters = clusters[: args.limit]

    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)

    print_cluster_plan(clusters)
    print()

    import anthropic
    client = anthropic.Anthropic()

    skipped = processed = written = 0
    total_input_tokens = total_output_tokens = 0
    errors = 0

    for i, cl in enumerate(clusters, 1):
        out_path = ARTICLES_DIR / f"{cl['slug']}.json"
        page_nums = [p["page"] for p in cl["pages"]]
        label = f"[{i}/{len(clusters)}] {cl['slug']} (pages {page_nums[0]}–{page_nums[-1]})"

        if out_path.exists():
            print(f"{label} — SKIP (exists)")
            skipped += 1
            continue

        print(f"{label} ...", end=" ", flush=True)
        processed += 1
        try:
            article, inp, out = call_sonnet(client, cl["pages"])
            out_path.write_text(json.dumps(article, indent=2, ensure_ascii=False))
            total_input_tokens += inp
            total_output_tokens += out
            written += 1
            print(f"OK  ({inp}in/{out}out)")
        except json.JSONDecodeError as e:
            print(f"PARSE ERROR: {e}")
            errors += 1
        except Exception as e:
            print(f"ERROR: {e}")
            errors += 1

    cost = (
        total_input_tokens / 1_000_000 * SONNET_INPUT_COST_PER_M
        + total_output_tokens / 1_000_000 * SONNET_OUTPUT_COST_PER_M
    )

    print()
    print(f"Clusters skipped (already exist): {skipped}")
    print(f"Clusters processed:               {processed}  (errors: {errors})")
    print(f"Articles written:                 {written}")
    print(f"Total tokens:                     {total_input_tokens:,} input, {total_output_tokens:,} output")
    print(f"Estimated cost:                   ${cost:.4f}")
    print(f"Output:                           {ARTICLES_DIR.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
