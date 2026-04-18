from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi
from rapidfuzz import fuzz


ROOT = Path(__file__).resolve().parents[2]
PRODUCT_ID = "vulcan-omnipro-220"
KNOWLEDGE_DIR = ROOT / "products" / PRODUCT_ID / "knowledge"

SYNONYMS = {
    "tig": ["gtaw", "tungsten", "torch"],
    "gtaw": ["tig", "tungsten", "torch"],
    "mig": ["gmaw", "solid core", "gas shielded"],
    "gmaw": ["mig", "solid core", "gas shielded"],
    "flux": ["flux-cored", "fcaw", "gasless", "self-shielded"],
    "flux-cored": ["flux", "fcaw", "gasless", "self-shielded"],
    "fcaw": ["flux", "flux-cored", "gasless", "self-shielded"],
    "ground": ["work clamp", "ground clamp"],
    "clamp": ["work clamp", "ground clamp"],
    "work": ["work clamp", "ground clamp"],
    "stinger": ["electrode holder"],
    "holder": ["electrode holder", "stinger"],
    "120v": ["120 vac", "120 volt"],
    "240v": ["240 vac", "240 volt"],
    "holes": ["porosity", "cavities"],
    "cavities": ["porosity", "holes"],
}

HIGH_VALUE_TERMS = {
    "porosity",
    "duty",
    "cycle",
    "polarity",
    "tig",
    "gtaw",
    "mig",
    "gmaw",
    "flux",
    "flux-cored",
    "fcaw",
    "stick",
    "smaw",
    "ground",
    "clamp",
    "shielding",
    "gas",
}

ANCHOR_TERMS = {
    "porosity",
    "duty",
    "cycle",
    "troubleshooting",
    "schematic",
    "selection",
}

OCR_SEARCH_WEIGHT = 0.72


@dataclass(frozen=True)
class SearchResult:
    doc_id: str
    source_doc: str
    page: int
    element_id: str
    text: str
    page_image: str
    score: float
    source_kind: str = "native_text"
    target_path: str | None = None
    avg_confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "doc_id": self.doc_id,
            "source_doc": self.source_doc,
            "page": self.page,
            "element_id": self.element_id,
            "text": self.text,
            "page_image": self.page_image,
            "score": round(self.score, 3),
            "source_kind": self.source_kind,
        }
        if self.target_path:
            data["target_path"] = self.target_path
        if self.avg_confidence is not None:
            data["avg_confidence"] = self.avg_confidence
        return data


class KnowledgeBase:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ROOT
        self.knowledge_dir = self.root / "products" / PRODUCT_ID / "knowledge"
        self.manifest = self._load_json(self.knowledge_dir / "manifest.json")
        self.pages = self._load_pages()
        self.duty_cycles = self._load_json(self.knowledge_dir / "tables" / "duty_cycles.json")["rows"]
        self.polarity_setups = self._load_json(self.knowledge_dir / "tables" / "polarity_setups.json")["rows"]
        self.troubleshooting_guides = self._load_json(self.knowledge_dir / "tables" / "troubleshooting_guides.json")["rows"]
        self.visual_index = self._load_visual_index()
        self._page_image_map: dict[tuple[str, int], str] = {
            (e["source_ref"]["doc_id"], e["source_ref"]["page"]): e["path"]
            for e in self.visual_index
            if "source_ref" in e
        }
        self.articles = self._load_articles()
        self.ocr_records = self._load_ocr_records()
        self._search_tokens = [self._tokens(page["text"]) for page in self.pages]
        self._bm25 = BM25Okapi(self._search_tokens)
        self._ocr_tokens = [self._tokens(record["text"]) for record in self.ocr_records]
        self._ocr_bm25 = BM25Okapi(self._ocr_tokens) if self._ocr_tokens else None
        self._article_tokens = [self._tokens(self._article_search_text(a)) for a in self.articles]
        self._article_bm25 = BM25Okapi(self._article_tokens) if self._article_tokens else None

    def search_manual(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        expanded = self._expand_query(query)
        query_tokens = self._tokens(expanded)
        original_query_tokens = set(self._tokens(query))
        requested_anchor_terms = original_query_tokens & ANCHOR_TERMS
        results = self._search_records(
            records=self.pages,
            bm25=self._bm25,
            query=query,
            expanded=expanded,
            query_tokens=query_tokens,
            requested_anchor_terms=requested_anchor_terms,
            weight=1.0,
            source_kind="native_text",
        )
        if self.ocr_records and self._ocr_bm25 is not None:
            results.extend(
                self._search_records(
                    records=self.ocr_records,
                    bm25=self._ocr_bm25,
                    query=query,
                    expanded=expanded,
                    query_tokens=query_tokens,
                    requested_anchor_terms=requested_anchor_terms,
                    weight=OCR_SEARCH_WEIGHT,
                    source_kind="ocr",
                )
            )
        return [result.to_dict() for result in sorted(results, key=lambda item: item.score, reverse=True)[:limit]]

    def lookup_duty_cycle(self, process: str, input_voltage: str | int, amperage: int) -> dict[str, Any] | None:
        normalized_process = self._normalize_process(process)
        normalized_voltage = self._normalize_voltage(input_voltage)
        exact = [
            row
            for row in self.duty_cycles
            if row["process"].lower() == normalized_process
            and self._normalize_voltage(row["input_voltage"]) == normalized_voltage
            and int(row["amperage"]) == int(amperage)
        ]
        if exact:
            return exact[0]

        same_context = [
            row
            for row in self.duty_cycles
            if row["process"].lower() == normalized_process
            and self._normalize_voltage(row["input_voltage"]) == normalized_voltage
        ]
        if not same_context:
            return None

        nearest = min(same_context, key=lambda row: abs(int(row["amperage"]) - int(amperage)))
        return {
            **nearest,
            "match_type": "nearest_available_amperage",
            "requested_amperage": amperage,
        }

    def lookup_polarity(self, process: str) -> dict[str, Any] | None:
        normalized_process = self._normalize_process(process)
        for row in self.polarity_setups:
            if row["process"].lower() == normalized_process:
                return row
        return None

    def troubleshooting_for(self, symptom: str, process: str | None = None) -> list[dict[str, Any]]:
        query = self._expand_query(" ".join(part for part in [symptom, process or ""] if part))
        matches: list[tuple[float, dict[str, Any]]] = []
        for row in self.troubleshooting_guides:
            haystack = " ".join(
                [
                    row["symptom"],
                    " ".join(row.get("applies_to", [])),
                    " ".join(check["cause"] + " " + check["solution"] for check in row["checks"]),
                ]
            )
            score = fuzz.partial_ratio(query.lower(), haystack.lower())
            if score >= 40:
                matches.append((float(score), row))
        return [row for _, row in sorted(matches, key=lambda item: item[0], reverse=True)]

    def search_articles(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        if not self.articles or self._article_bm25 is None:
            return []
        expanded = self._expand_query(query)
        tokens = self._tokens(expanded)
        bm25_scores = self._article_bm25.get_scores(tokens)
        ranked: list[tuple[float, dict[str, Any]]] = []
        for i, article in enumerate(self.articles):
            fuzzy_score = fuzz.partial_ratio(
                expanded.lower(), self._article_search_text(article).lower()
            ) / 20.0
            final = float(bm25_scores[i]) + fuzzy_score
            if final > 0:
                ranked.append((final, article))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [self._inject_page_images(a) for _, a in ranked[:limit]]

    def _inject_page_images(self, article: dict[str, Any]) -> dict[str, Any]:
        import copy
        article = copy.deepcopy(article)
        for ref in article.get("source_refs", []):
            key = (ref.get("doc_id"), ref.get("page"))
            if key in self._page_image_map:
                ref["page_image"] = self._page_image_map[key]
        return article

    def get_manual_image(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        expanded = self._expand_query(query)
        results: list[tuple[float, dict[str, Any]]] = []
        for item in self.visual_index:
            haystack = " ".join([item["title"], item["description"], " ".join(item.get("query_terms", []))])
            score = fuzz.partial_ratio(expanded.lower(), haystack.lower())
            if score >= 35:
                results.append((float(score), item))
        return [item for _, item in sorted(results, key=lambda row: row[0], reverse=True)[:limit]]

    def _load_visual_index(self) -> list[dict[str, Any]]:
        full = self.knowledge_dir / "images" / "visual_index_full.json"
        fallback = self.knowledge_dir / "images" / "visual_index.json"
        return self._load_json(full if full.exists() else fallback)

    def _load_articles(self) -> list[dict[str, Any]]:
        articles_dir = self.knowledge_dir / "articles"
        if not articles_dir.exists():
            return []
        articles = []
        for path in sorted(articles_dir.glob("*.json")):
            try:
                articles.append(self._load_json(path))
            except Exception:
                pass
        return articles

    @staticmethod
    def _article_search_text(article: dict[str, Any]) -> str:
        return " ".join([
            article.get("title", ""),
            article.get("summary", ""),
            " ".join(article.get("key_facts", [])),
            " ".join(article.get("warnings", [])),
            " ".join(article.get("query_terms", [])),
        ])

    def _load_pages(self) -> list[dict[str, Any]]:
        pages: list[dict[str, Any]] = []
        for path in sorted((self.knowledge_dir / "sections").glob("*.json")):
            pages.extend(self._load_json(path))
        return pages

    def _load_ocr_records(self) -> list[dict[str, Any]]:
        path = self.knowledge_dir / "ocr" / "records.json"
        if not path.exists():
            return []
        return self._load_json(path)

    @staticmethod
    def _load_json(path: Path) -> Any:
        return json.loads(path.read_text())

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return re.findall(r"[a-z0-9]+", text.lower())

    @staticmethod
    def _normalize_voltage(value: str | int) -> str:
        digits = re.sub(r"\D", "", str(value))
        if digits in {"120", "240"}:
            return f"{digits} vac"
        return str(value).strip().lower()

    @staticmethod
    def _normalize_process(process: str) -> str:
        lowered = process.strip().lower()
        if lowered in {"gmaw", "solid core", "solid-core"}:
            return "mig"
        if lowered in {"flux", "fcaw", "flux cored", "flux-cored", "self shielded", "self-shielded"}:
            return "flux-cored"
        if lowered in {"gtaw"}:
            return "tig"
        if lowered in {"smaw"}:
            return "stick"
        return lowered

    def _expand_query(self, query: str) -> str:
        tokens = self._tokens(query)
        additions: list[str] = []
        lowered = query.lower()
        for token in tokens:
            additions.extend(SYNONYMS.get(token, []))
        for phrase, synonyms in SYNONYMS.items():
            if " " in phrase and phrase in lowered:
                additions.extend(synonyms)
        return " ".join([query, *additions])

    def _search_records(
        self,
        *,
        records: list[dict[str, Any]],
        bm25: BM25Okapi,
        query: str,
        expanded: str,
        query_tokens: list[str],
        requested_anchor_terms: set[str],
        weight: float,
        source_kind: str,
    ) -> list[SearchResult]:
        bm25_scores = bm25.get_scores(query_tokens)
        query_token_set = set(query_tokens)
        results: list[SearchResult] = []
        for index, record in enumerate(records):
            text = record["text"]
            if not text.strip():
                continue
            record_tokens = set(self._tokens(text))
            metadata_tokens = self._record_metadata_tokens(record)
            searchable_tokens = record_tokens | metadata_tokens
            exact_matches = query_token_set & searchable_tokens
            if not exact_matches:
                continue
            exact_score = len(exact_matches) * 2.0
            high_value_score = len(exact_matches & HIGH_VALUE_TERMS) * 4.0
            metadata_score = len(query_token_set & metadata_tokens) * 5.0
            anchor_score = 0.0
            if requested_anchor_terms:
                matched_anchors = requested_anchor_terms & searchable_tokens
                anchor_score += len(matched_anchors) * 15.0
                anchor_score -= len(requested_anchor_terms - matched_anchors) * 10.0
            fuzzy_score = fuzz.token_set_ratio(expanded.lower(), text.lower()) / 25.0 if len(query_token_set) > 2 else 0.0
            score = weight * (float(bm25_scores[index]) + exact_score + high_value_score + metadata_score + anchor_score + fuzzy_score)
            if score <= 0:
                continue
            results.append(
                SearchResult(
                    doc_id=record["doc_id"],
                    source_doc=record["source_doc"],
                    page=record["page"],
                    element_id=record["element_id"],
                    text=self._preview(text, query_tokens),
                    page_image=record["page_image"],
                    score=score,
                    source_kind=source_kind,
                    target_path=record.get("target_path"),
                    avg_confidence=record.get("avg_confidence"),
                )
            )
        return results

    def _record_metadata_tokens(self, record: dict[str, Any]) -> set[str]:
        metadata = " ".join(
            [
                str(record.get("doc_id", "")),
                str(record.get("source_doc", "")).replace(".pdf", ""),
                str(record.get("target_type", "")),
            ]
        )
        return set(self._tokens(metadata))

    @staticmethod
    def _preview(text: str, query_tokens: list[str], length: int = 700) -> str:
        compact = " ".join(text.split())
        if len(compact) <= length:
            return compact
        lowered = compact.lower()
        positions = [lowered.find(token) for token in query_tokens if lowered.find(token) >= 0]
        start = max(min(positions) - 160, 0) if positions else 0
        end = min(start + length, len(compact))
        prefix = "..." if start else ""
        suffix = "..." if end < len(compact) else ""
        return f"{prefix}{compact[start:end]}{suffix}"
