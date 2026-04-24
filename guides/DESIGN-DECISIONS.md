# Design Decisions

These are the main implementation choices behind the assistant.

## 1. Pay parsing cost offline, not at request time

The manuals are dense and image-heavy. I chose to materialize a local knowledge bundle ahead of time instead of parsing PDFs during every request.

This gives:

- lower runtime latency
- easier debugging
- a clearer separation between content quality and model behavior

## 2. Use deterministic structured data for safety-critical facts

For duty cycle, polarity, and core troubleshooting paths, I wanted exact machine-specific answers to come from structured verified data rather than from the model paraphrasing a page.

That improves:

- trustworthiness
- consistency
- debuggability

## 3. Prefer a tuned lexical retriever over embeddings

The corpus is small, static, and highly technical. BM25 plus fuzzy matching plus curated synonyms is simple, fast, and explainable.

For this use case, that was the right tradeoff.

## 4. Treat visual retrieval as first-class

The Vulcan OmniPro 220 manuals contain important information that is easier to act on visually than textually:

- cable setups
- the selection chart
- quick-start pages
- weld defect photos
- control labels

So I made image and page retrieval and artifact rendering part of the core answer path, not an afterthought.

## 5. Keep product knowledge separate from orchestration

I kept the product knowledge in local JSON plus a `KnowledgeBase` abstraction rather than encoding product behavior only in the prompt.

That gives:

- inspectable source data
- deterministic fallbacks
- reusable tools across CLI, API, and SDK-compatible paths
- a cleaner path to improving retrieval without changing the app surface
