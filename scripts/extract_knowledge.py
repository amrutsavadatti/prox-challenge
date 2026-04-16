from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import fitz
from PIL import Image
from pydantic import BaseModel, Field
from rapidocr_onnxruntime import RapidOCR


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_ID = "vulcan-omnipro-220"
PRODUCT_DIR = ROOT / "products" / PRODUCT_ID
KNOWLEDGE_DIR = PRODUCT_DIR / "knowledge"

SOURCE_DOCS = [
    {
        "doc_id": "owner-manual",
        "source_doc": "owner-manual.pdf",
        "path": ROOT / "files" / "owner-manual.pdf",
    },
    {
        "doc_id": "quick-start-guide",
        "source_doc": "quick-start-guide.pdf",
        "path": ROOT / "files" / "quick-start-guide.pdf",
    },
    {
        "doc_id": "selection-chart",
        "source_doc": "selection-chart.pdf",
        "path": ROOT / "files" / "selection-chart.pdf",
    },
]

PRODUCT_IMAGES = [
    {
        "image_id": "product-exterior",
        "source_file": "product.webp",
        "path": ROOT / "product.webp",
        "caption": "Vulcan OmniPro 220 exterior product photo.",
    },
    {
        "image_id": "product-inside-panel",
        "source_file": "product-inside.webp",
        "path": ROOT / "product-inside.webp",
        "caption": "Vulcan OmniPro 220 inside panel product photo.",
    },
]

TABLE_CANDIDATE_TERMS = {
    "duty_cycle": ["duty cycle", "200a", "240v", "120v"],
    "polarity": ["polarity", "dcen", "dcep", "electrode negative", "work clamp"],
    "troubleshooting": ["troubleshooting", "porosity", "spatter", "diagnosis", "weld"],
    "settings": ["selection", "chart", "wire speed", "thickness", "voltage"],
    "parts": ["parts list", "parts", "assembly diagram"],
}

OCR_PAGE_TARGETS = {
    "selection-chart": {1},
    "quick-start-guide": {1, 2},
}

OCR_IMAGE_PAGE_TARGETS = {
    "owner-manual": {20, 21, 24, 27},
}

MIN_OCR_CONFIDENCE = 0.45

VISUAL_INDEX = [
    {
        "visual_id": "selection-chart-overview",
        "title": "Selection Chart Overview",
        "description": "Full-page selection chart for choosing process, setup direction, and baseline settings.",
        "path": "products/vulcan-omnipro-220/knowledge/pages/selection-chart/page-001.png",
        "source_ref": {
            "doc_id": "selection-chart",
            "source_doc": "selection-chart.pdf",
            "page": 1,
            "element_id": "selection-chart:page:001",
        },
        "query_terms": [
            "selection chart",
            "how to choose",
            "settings chart",
            "material thickness",
            "wire speed",
            "voltage",
            "process",
        ],
    },
    {
        "visual_id": "quick-start-wire-loading",
        "title": "Quick Start Wire Loading",
        "description": "Quick-start page showing wire spool loading, feed path, and cold wire feed steps.",
        "path": "products/vulcan-omnipro-220/knowledge/pages/quick-start-guide/page-001.png",
        "source_ref": {
            "doc_id": "quick-start-guide",
            "source_doc": "quick-start-guide.pdf",
            "page": 1,
            "element_id": "quick-start-guide:page:001",
        },
        "query_terms": [
            "quick start",
            "wire spool",
            "feed mechanism",
            "wire loading",
            "cold wire feed",
            "guide",
        ],
    },
    {
        "visual_id": "quick-start-cable-setup",
        "title": "Quick Start Cable Setup",
        "description": "Quick-start page showing STICK, MIG, Flux-Cored, and TIG cable setup guidance.",
        "path": "products/vulcan-omnipro-220/knowledge/pages/quick-start-guide/page-002.png",
        "source_ref": {
            "doc_id": "quick-start-guide",
            "source_doc": "quick-start-guide.pdf",
            "page": 2,
            "element_id": "quick-start-guide:page:002",
        },
        "query_terms": [
            "quick start",
            "stick cable setup",
            "mig cable setup",
            "flux cable setup",
            "tig cable setup",
            "positive terminal",
            "negative terminal",
        ],
    },
    {
        "visual_id": "front-panel-controls",
        "title": "Front Panel Controls",
        "description": "Controls page with front-panel setting labels such as Spot Timer and Run-In WFS.",
        "path": "products/vulcan-omnipro-220/knowledge/pages/owner-manual/page-021.png",
        "source_ref": {
            "doc_id": "owner-manual",
            "source_doc": "owner-manual.pdf",
            "page": 21,
            "element_id": "owner-manual:page:021",
        },
        "query_terms": [
            "front panel",
            "control panel",
            "spot timer",
            "run-in wfs",
            "settings",
            "controls",
        ],
    },
    {
        "visual_id": "tig-polarity-setup",
        "title": "TIG Polarity Setup",
        "description": "TIG setup diagram showing ground clamp cable in the positive socket and TIG torch cable in the negative socket.",
        "path": "products/vulcan-omnipro-220/knowledge/pages/owner-manual/page-024.png",
        "source_ref": {
            "doc_id": "owner-manual",
            "source_doc": "owner-manual.pdf",
            "page": 24,
            "element_id": "owner-manual:page:024",
        },
        "query_terms": [
            "tig",
            "gtaw",
            "polarity",
            "ground clamp",
            "positive socket",
            "negative socket",
            "torch cable",
            "dcen",
        ],
    },
    {
        "visual_id": "stick-polarity-setup",
        "title": "Stick Polarity Setup",
        "description": "Stick setup diagram showing ground clamp cable in the negative socket and electrode holder cable in the positive socket.",
        "path": "products/vulcan-omnipro-220/knowledge/pages/owner-manual/page-027.png",
        "source_ref": {
            "doc_id": "owner-manual",
            "source_doc": "owner-manual.pdf",
            "page": 27,
            "element_id": "owner-manual:page:027",
        },
        "query_terms": [
            "stick",
            "smaw",
            "polarity",
            "ground clamp",
            "electrode holder",
            "positive socket",
            "negative socket",
        ],
    },
    {
        "visual_id": "porosity-diagnosis",
        "title": "Wire Weld Porosity Diagnosis",
        "description": "Diagnosis page showing porosity examples and likely causes for wire welding.",
        "path": "products/vulcan-omnipro-220/knowledge/pages/owner-manual/page-037.png",
        "source_ref": {
            "doc_id": "owner-manual",
            "source_doc": "owner-manual.pdf",
            "page": 37,
            "element_id": "owner-manual:page:037",
        },
        "query_terms": [
            "porosity",
            "weld defect",
            "wire weld",
            "mig",
            "flux-cored",
            "diagnosis",
        ],
    },
    {
        "visual_id": "mig-flux-troubleshooting",
        "title": "MIG and Flux-Cored Troubleshooting",
        "description": "Troubleshooting table for wire feed issues, unstable arc, weak arc strength, and related welding faults.",
        "path": "products/vulcan-omnipro-220/knowledge/pages/owner-manual/page-042.png",
        "source_ref": {
            "doc_id": "owner-manual",
            "source_doc": "owner-manual.pdf",
            "page": 42,
            "element_id": "owner-manual:page:042",
        },
        "query_terms": [
            "troubleshooting",
            "wire feed",
            "arc not stable",
            "weak arc",
            "mig troubleshooting",
            "flux-cored troubleshooting",
        ],
    },
    {
        "visual_id": "porosity-troubleshooting",
        "title": "Porosity Troubleshooting",
        "description": "Troubleshooting page that includes Porosity in the Weld Metal causes and remedies.",
        "path": "products/vulcan-omnipro-220/knowledge/pages/owner-manual/page-043.png",
        "source_ref": {
            "doc_id": "owner-manual",
            "source_doc": "owner-manual.pdf",
            "page": 43,
            "element_id": "owner-manual:page:043",
        },
        "query_terms": [
            "porosity troubleshooting",
            "weld metal",
            "gas coverage",
            "dirty workpiece",
            "dcep",
            "dcen",
        ],
    },
]


class SourceDocument(BaseModel):
    doc_id: str
    source_doc: str
    relative_path: str
    sha256: str
    bytes: int
    page_count: int


class PageRecord(BaseModel):
    doc_id: str
    source_doc: str
    page: int
    element_id: str
    element_type: str = "page_text"
    text: str
    word_count: int
    page_image: str
    blocks: list[dict[str, Any]] = Field(default_factory=list)


class ImageRecord(BaseModel):
    image_id: str
    doc_id: str
    source_doc: str
    page: int | None
    element_id: str
    element_type: str
    path: str
    caption: str
    bbox: list[list[float]] = Field(default_factory=list)
    width: int | None = None
    height: int | None = None
    needs_caption: bool = False


class OCRTargetRecord(BaseModel):
    target_id: str
    doc_id: str
    source_doc: str
    page: int
    source_element_id: str
    target_type: str
    target_path: str
    page_image: str
    word_count_native: int
    extracted_blocks: int
    extracted_words: int
    avg_confidence: float | None = None


class OCRRecord(BaseModel):
    ocr_id: str
    doc_id: str
    source_doc: str
    page: int
    source_element_id: str
    element_id: str
    element_type: str = "ocr_text"
    target_type: str
    target_path: str
    page_image: str
    text: str
    word_count: int
    avg_confidence: float | None = None
    blocks: list[dict[str, Any]] = Field(default_factory=list)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_dirs() -> None:
    for directory in [
        KNOWLEDGE_DIR / "sections",
        KNOWLEDGE_DIR / "tables",
        KNOWLEDGE_DIR / "images",
        KNOWLEDGE_DIR / "pages",
        KNOWLEDGE_DIR / "ocr",
    ]:
        directory.mkdir(parents=True, exist_ok=True)


def clean_generated() -> None:
    for directory in [
        KNOWLEDGE_DIR / "sections",
        KNOWLEDGE_DIR / "images",
        KNOWLEDGE_DIR / "pages",
        KNOWLEDGE_DIR / "ocr",
    ]:
        if directory.exists():
            shutil.rmtree(directory)
    table_candidates = KNOWLEDGE_DIR / "tables" / "table_candidates.json"
    if table_candidates.exists():
        table_candidates.unlink()
    for path in [KNOWLEDGE_DIR / "manifest.json", PRODUCT_DIR / "product.json"]:
        if path.exists():
            path.unlink()
    ensure_dirs()


def image_size(path: Path) -> tuple[int | None, int | None]:
    try:
        with Image.open(path) as image:
            return image.size
    except Exception:
        return None, None


def ocr_sort_key(block: dict[str, Any]) -> tuple[float, float]:
    xs = [point[0] for point in block["bbox"]]
    ys = [point[1] for point in block["bbox"]]
    return (min(ys), min(xs))


def normalize_ocr_result(raw_result: list[list[Any | str]] | None) -> tuple[list[dict[str, Any]], str, float | None]:
    blocks: list[dict[str, Any]] = []
    for item in raw_result or []:
        if len(item) < 3:
            continue
        bbox, text, confidence = item
        compact = " ".join(str(text).split()).strip()
        score = float(confidence)
        if not compact or score < MIN_OCR_CONFIDENCE:
            continue
        normalized_bbox = [
            [round(float(point[0]), 2), round(float(point[1]), 2)]
            for point in bbox
        ]
        blocks.append(
            {
                "bbox": normalized_bbox,
                "text": compact,
                "confidence": round(score, 3),
            }
        )

    blocks.sort(key=ocr_sort_key)
    merged_text = "\n".join(block["text"] for block in blocks)
    if not blocks:
        return blocks, merged_text, None
    average_confidence = round(sum(block["confidence"] for block in blocks) / len(blocks), 3)
    return blocks, merged_text, average_confidence


def extract_targeted_ocr(pages: list[PageRecord], images: list[ImageRecord]) -> tuple[list[OCRTargetRecord], list[OCRRecord]]:
    ocr_engine = RapidOCR()
    page_lookup = {(page.doc_id, page.page): page for page in pages}

    targets: list[dict[str, Any]] = []
    for page in pages:
        if page.doc_id in OCR_PAGE_TARGETS and page.page in OCR_PAGE_TARGETS[page.doc_id]:
            targets.append(
                {
                    "target_id": f"{page.element_id}:ocr:page",
                    "doc_id": page.doc_id,
                    "source_doc": page.source_doc,
                    "page": page.page,
                    "source_element_id": page.element_id,
                    "target_type": "page_image",
                    "target_path": page.page_image,
                    "page_image": page.page_image,
                    "word_count_native": page.word_count,
                }
            )

    for image in images:
        if image.element_type != "embedded_image" or image.page is None:
            continue
        target_pages = OCR_IMAGE_PAGE_TARGETS.get(image.doc_id)
        if not target_pages or image.page not in target_pages:
            continue
        page = page_lookup.get((image.doc_id, image.page))
        if page is None:
            continue
        targets.append(
            {
                "target_id": f"{image.element_id}:ocr:image",
                "doc_id": image.doc_id,
                "source_doc": image.source_doc,
                "page": image.page,
                "source_element_id": image.element_id,
                "target_type": "embedded_image",
                "target_path": image.path,
                "page_image": page.page_image,
                "word_count_native": page.word_count,
            }
        )

    target_records: list[OCRTargetRecord] = []
    ocr_records: list[OCRRecord] = []

    for target in targets:
        raw_result, _ = ocr_engine(ROOT / target["target_path"])
        blocks, merged_text, average_confidence = normalize_ocr_result(raw_result)
        extracted_words = len(merged_text.split())
        target_records.append(
            OCRTargetRecord(
                **target,
                extracted_blocks=len(blocks),
                extracted_words=extracted_words,
                avg_confidence=average_confidence,
            )
        )
        if not merged_text:
            continue
        ocr_records.append(
            OCRRecord(
                ocr_id=target["target_id"],
                doc_id=target["doc_id"],
                source_doc=target["source_doc"],
                page=target["page"],
                source_element_id=target["source_element_id"],
                element_id=f"{target['source_element_id']}:ocr",
                target_type=target["target_type"],
                target_path=target["target_path"],
                page_image=target["page_image"],
                text=merged_text,
                word_count=extracted_words,
                avg_confidence=average_confidence,
                blocks=blocks,
            )
        )

    return target_records, ocr_records


def extract_text_blocks(page: fitz.Page) -> list[dict[str, Any]]:
    page_dict = page.get_text("dict", sort=True)
    blocks: list[dict[str, Any]] = []
    for block_index, block in enumerate(page_dict.get("blocks", []), start=1):
        if block.get("type") != 0:
            continue
        lines: list[str] = []
        for line in block.get("lines", []):
            spans = [span.get("text", "") for span in line.get("spans", [])]
            line_text = "".join(spans).strip()
            if line_text:
                lines.append(line_text)
        text = "\n".join(lines).strip()
        if not text:
            continue
        blocks.append(
            {
                "block_id": f"block-{block_index:03}",
                "bbox": [round(float(value), 2) for value in block.get("bbox", [])],
                "text": text,
            }
        )
    return blocks


def matched_candidate_terms(text: str) -> dict[str, list[str]]:
    lowered = text.lower()
    matches: dict[str, list[str]] = {}
    for group, terms in TABLE_CANDIDATE_TERMS.items():
        found = [term for term in terms if term in lowered]
        if found:
            matches[group] = found
    return matches


def extract_document(doc_spec: dict[str, Any], dpi: int) -> tuple[SourceDocument, list[PageRecord], list[ImageRecord], list[dict[str, Any]]]:
    source_path = doc_spec["path"]
    if not source_path.exists():
        raise FileNotFoundError(source_path)

    doc_id = doc_spec["doc_id"]
    source_doc = doc_spec["source_doc"]
    page_output_dir = KNOWLEDGE_DIR / "pages" / doc_id
    page_output_dir.mkdir(parents=True, exist_ok=True)
    images_output_dir = KNOWLEDGE_DIR / "images"

    pages: list[PageRecord] = []
    images: list[ImageRecord] = []
    candidates: list[dict[str, Any]] = []

    with fitz.open(source_path) as document:
        source = SourceDocument(
            doc_id=doc_id,
            source_doc=source_doc,
            relative_path=rel(source_path),
            sha256=sha256_file(source_path),
            bytes=source_path.stat().st_size,
            page_count=document.page_count,
        )

        saved_xrefs: dict[int, Path] = {}
        for page_index in range(document.page_count):
            page_num = page_index + 1
            page = document.load_page(page_index)
            page_image = page_output_dir / f"page-{page_num:03}.png"
            page.get_pixmap(dpi=dpi, alpha=False).save(page_image)

            text = page.get_text("text", sort=True).strip()
            blocks = extract_text_blocks(page)
            record = PageRecord(
                doc_id=doc_id,
                source_doc=source_doc,
                page=page_num,
                element_id=f"{doc_id}:page:{page_num:03}",
                text=text,
                word_count=len(text.split()),
                page_image=rel(page_image),
                blocks=blocks,
            )
            pages.append(record)

            matches = matched_candidate_terms(text)
            if matches:
                candidates.append(
                    {
                        "doc_id": doc_id,
                        "source_doc": source_doc,
                        "page": page_num,
                        "element_id": record.element_id,
                        "matched_terms": matches,
                        "text_preview": " ".join(text.split())[:900],
                        "page_image": rel(page_image),
                    }
                )

            for image_index, image_info in enumerate(page.get_images(full=True), start=1):
                xref = int(image_info[0])
                if xref not in saved_xrefs:
                    extracted = document.extract_image(xref)
                    extension = extracted.get("ext", "png")
                    image_path = images_output_dir / f"{doc_id}-p{page_num:03}-img{image_index:02}-xref{xref}.{extension}"
                    image_path.write_bytes(extracted["image"])
                    saved_xrefs[xref] = image_path
                image_path = saved_xrefs[xref]
                width, height = image_size(image_path)
                rects = [
                    [round(float(value), 2) for value in rect]
                    for rect in page.get_image_rects(xref)
                ]
                images.append(
                    ImageRecord(
                        image_id=f"{doc_id}:image:xref:{xref}",
                        doc_id=doc_id,
                        source_doc=source_doc,
                        page=page_num,
                        element_id=f"{doc_id}:page:{page_num:03}:image:xref:{xref}",
                        element_type="embedded_image",
                        path=rel(image_path),
                        caption="",
                        bbox=rects,
                        width=width,
                        height=height,
                        needs_caption=True,
                    )
                )

    return source, pages, images, candidates


def copy_product_images() -> list[ImageRecord]:
    records: list[ImageRecord] = []
    output_dir = KNOWLEDGE_DIR / "images"
    output_dir.mkdir(parents=True, exist_ok=True)
    for spec in PRODUCT_IMAGES:
        source = spec["path"]
        if not source.exists():
            continue
        target = output_dir / spec["source_file"]
        shutil.copy2(source, target)
        width, height = image_size(target)
        records.append(
            ImageRecord(
                image_id=spec["image_id"],
                doc_id="product-photos",
                source_doc=spec["source_file"],
                page=None,
                element_id=f"product-photos:{spec['image_id']}",
                element_type="product_photo",
                path=rel(target),
                caption=spec["caption"],
                width=width,
                height=height,
                needs_caption=False,
            )
        )
    return records


def write_visual_index() -> None:
    write_json(KNOWLEDGE_DIR / "images" / "visual_index.json", VISUAL_INDEX)


def write_product_file(source_docs: list[SourceDocument], product_images: list[ImageRecord]) -> None:
    write_json(
        PRODUCT_DIR / "product.json",
        {
            "product_id": PRODUCT_ID,
            "name": "Vulcan OmniPro 220",
            "brand": "Vulcan",
            "category": "multiprocess welder",
            "source_documents": [doc.model_dump(mode="json") for doc in source_docs],
            "source_images": [image.model_dump(mode="json") for image in product_images],
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract the Vulcan OmniPro 220 knowledge bundle.")
    parser.add_argument("--dpi", type=int, default=144, help="DPI for rendered manual pages.")
    parser.add_argument("--clean", action="store_true", help="Clear generated knowledge outputs before extracting.")
    args = parser.parse_args()

    if args.clean:
        clean_generated()
    else:
        ensure_dirs()

    all_sources: list[SourceDocument] = []
    all_pages: list[PageRecord] = []
    all_images: list[ImageRecord] = []
    all_candidates: list[dict[str, Any]] = []

    for doc_spec in SOURCE_DOCS:
        source, pages, images, candidates = extract_document(doc_spec, dpi=args.dpi)
        all_sources.append(source)
        all_pages.extend(pages)
        all_images.extend(images)
        all_candidates.extend(candidates)
        write_json(
            KNOWLEDGE_DIR / "sections" / f"{source.doc_id}.json",
            [page.model_dump(mode="json") for page in pages],
        )

    product_image_records = copy_product_images()
    all_images.extend(product_image_records)
    write_visual_index()
    ocr_targets, ocr_records = extract_targeted_ocr(all_pages, all_images)

    write_json(KNOWLEDGE_DIR / "images" / "metadata.json", [image.model_dump(mode="json") for image in all_images])
    write_json(KNOWLEDGE_DIR / "ocr" / "targets.json", [target.model_dump(mode="json") for target in ocr_targets])
    write_json(KNOWLEDGE_DIR / "ocr" / "records.json", [record.model_dump(mode="json") for record in ocr_records])
    write_json(KNOWLEDGE_DIR / "tables" / "table_candidates.json", all_candidates)
    write_json(
        KNOWLEDGE_DIR / "manifest.json",
        {
            "product_id": PRODUCT_ID,
            "source_documents": [source.model_dump(mode="json") for source in all_sources],
            "verified_tables": sorted(
                path.name
                for path in (KNOWLEDGE_DIR / "tables").glob("*.json")
                if path.name != "table_candidates.json"
            ),
            "counts": {
                "source_documents": len(all_sources),
                "pages": len(all_pages),
                "text_blocks": sum(len(page.blocks) for page in all_pages),
                "images": len(all_images),
                "ocr_targets": len(ocr_targets),
                "ocr_records": len(ocr_records),
                "ocr_blocks": sum(len(record.blocks) for record in ocr_records),
                "table_candidate_pages": len(all_candidates),
                "verified_tables": len(
                    [
                        path
                        for path in (KNOWLEDGE_DIR / "tables").glob("*.json")
                        if path.name != "table_candidates.json"
                    ]
                ),
            },
            "paths": {
                "sections": rel(KNOWLEDGE_DIR / "sections"),
                "tables": rel(KNOWLEDGE_DIR / "tables"),
                "images": rel(KNOWLEDGE_DIR / "images"),
                "pages": rel(KNOWLEDGE_DIR / "pages"),
                "ocr": rel(KNOWLEDGE_DIR / "ocr"),
            },
        },
    )
    write_product_file(all_sources, product_image_records)

    print("Extracted knowledge bundle")
    print(f"  product: {PRODUCT_ID}")
    print(f"  source documents: {len(all_sources)}")
    print(f"  pages: {len(all_pages)}")
    print(f"  text blocks: {sum(len(page.blocks) for page in all_pages)}")
    print(f"  images: {len(all_images)}")
    print(f"  ocr targets: {len(ocr_targets)}")
    print(f"  ocr records: {len(ocr_records)}")
    print(f"  table candidate pages: {len(all_candidates)}")
    print(f"  manifest: {rel(KNOWLEDGE_DIR / 'manifest.json')}")


if __name__ == "__main__":
    main()
