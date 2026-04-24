# Architecture

This document explains how the assistant answers questions at runtime and how the frontend and backend share responsibility.

## How the Agent Works

The system has two phases:

1. Offline knowledge extraction into a local bundle.
2. Online question answering over that bundle.

## High-level architecture

<img src="../Prox-diagram.png" alt="High-level architecture" />

At runtime, the model does not read the whole manual. It chooses a narrow tool, the backend returns only the top local evidence for that question, and the model answers from that evidence.

The shipped web app uses Anthropic's streaming tool-use API directly for tight control over:

- streaming UX
- local tool execution
- artifact metadata
- voice playback timing

The same knowledge layer is also exposed through MCP-compatible tool wrappers in `src/prox_agent/sdk_tools.py`.

## How the Agent Decides What to Read

There are two levels of selection.

### 1. Tool selection

The model chooses among a small set of local tools:

- `search_manual`
- `search_articles`
- `lookup_duty_cycle`
- `lookup_polarity`
- `troubleshooting_for`
- `get_manual_image`

The system prompt strongly steers the model toward the narrowest evidence path:

- exact tables for duty cycle and polarity
- article retrieval for procedures and warnings
- raw manual search for cited snippets
- image retrieval when a diagram or page is more actionable than prose

### 2. Top-k retrieval inside the tool

The model does not get the whole corpus.

Instead:

- `search_manual` returns only top page and OCR snippets
- `search_articles` returns only top article objects
- `get_manual_image` returns only top visual matches
- exact lookups return one row or a small result set

So the server indexes the full knowledge bundle locally, but the model only reads the selected evidence for the current question.

## Chat History and Context

The frontend stores full chats in browser local storage and sends the full active conversation with each request.

The backend does not forward all of that to Anthropic. It trims the history to the last 10 messages before sending the model request.

That was a deliberate latency and cost tradeoff, but it means:

- the UI remembers more than the model does
- long troubleshooting sessions can lose older context
- there is no server-side long-term memory layer
- current-turn images are sent to the model, prior-turn images are not replayed

## Frontend Experience

The frontend is a React + Vite app with:

- persisted chats via Zustand
- streaming assistant responses
- artifact tabs
- markdown rendering
- image, table, Mermaid, and interactive HTML rendering
- optional voice capture and streamed playback

This matters because for this product, the right answer format often is not a paragraph. A polarity answer should show a diagram. A troubleshooting answer should often be a flow. A settings answer can be more useful as a structured artifact than as plain prose.
