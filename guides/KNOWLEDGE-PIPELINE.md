# Knowledge Pipeline

This document covers how the local knowledge bundle is built and how retrieval works at runtime.

## Knowledge Extraction and Representation

The local knowledge bundle lives under:

```text
products/vulcan-omnipro-220/knowledge/
```

It is built from:

- `files/owner-manual.pdf`
- `files/quick-start-guide.pdf`
- `files/selection-chart.pdf`
- product photos in the repo root

The bundle contains several layers.

### 1. Native page text

Stored in:

```text
knowledge/sections/*.json
```

Each page record contains page text, metadata, and block extraction data. Runtime manual search currently ranks at the page level.

### 2. Rasterized page images

Stored in:

```text
knowledge/pages/<doc_id>/page-XXX.png
```

These power:

- visual artifacts
- OCR
- image-based retrieval
- page display in the UI

### 3. Targeted OCR

Stored in:

```text
knowledge/ocr/targets.json
knowledge/ocr/records.json
```

I use targeted OCR rather than OCR over every page. The intention is to recover high-value visual text where native PDF extraction is weak, especially for:

- the selection chart
- quick-start pages
- front-panel labels
- important setup and troubleshooting visuals

### 4. Structured articles

Stored in:

```text
knowledge/articles/*.json
```

These are LLM-generated structured summaries built from clusters of owner-manual pages. They contain:

- summaries
- key facts
- procedure steps
- warnings
- source references
- search terms

These are used for procedural and explanatory questions where a structured answer is more useful than raw snippets.

### 5. Visual metadata

Stored in:

```text
knowledge/images/visual_index.json
knowledge/images/visual_index_full.json
```

This layer maps user intent like "show me the TIG polarity setup" to a relevant page or figure using titles, descriptions, visible text, and query terms.

### 6. Verified structured tables

Stored in:

```text
knowledge/tables/duty_cycles.json
knowledge/tables/polarity_setups.json
knowledge/tables/troubleshooting_guides.json
```

These are the most important structured facts in the system. They are used for the highest-stakes machine-specific answers.

## Retrieval and Reasoning Strategy

This project does not use embeddings. It uses a local lexical retrieval stack based on:

- BM25
- fuzzy matching
- domain-specific synonym expansion
- deterministic exact lookups for critical facts

### BM25

BM25 is the primary ranker for:

- native page text
- OCR records
- structured article search text

This fits the domain well because welding questions often rely on exact technical language:

- TIG
- MIG
- DCEP
- DCEN
- duty cycle
- porosity
- inductance
- wire feed

### Fuzzy matching

RapidFuzz is used as a side score to help with:

- partial phrase overlap
- different word order
- less exact user wording

### Synonym expansion

Before ranking, certain domain queries are expanded. Examples:

- `tig` -> `gtaw`, `tungsten`, `torch`
- `mig` -> `gmaw`, `solid core`, `gas shielded`
- `flux-cored` -> `fcaw`, `gasless`, `self-shielded`
- `ground` -> `work clamp`, `ground clamp`

That helps bridge the gap between user language and manual language without needing an embeddings system.
