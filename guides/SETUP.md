# Setup

This guide contains the full local setup flow for the Vulcan OmniPro 220 multimodal product agent.

## One-command setup

The repo includes bootstrap scripts that install the required toolchain, copy `.env.example` to `.env`, and install backend and frontend dependencies.

macOS/Linux:

```bash
./scripts/setup.sh
```

Windows CMD:

```bat
scripts\setup.bat
```

What the script sets up:

- `Python 3.12` via `uv`
- `Node 20.19.0` via `Volta`
- backend dependencies via `uv sync`
- frontend dependencies via `npm install`
- `.env` copied from `.env.example` if it does not already exist

After it finishes, open `.env` and add your API keys, then start the backend and frontend as shown below.

## Prerequisites

- Python 3.12+
- Node.js 20+
- `uv`
- `npm`

## 1. Configure environment

```bash
cp .env.example .env
```

Minimum required environment variables:

```env
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6
OPENAI_API_KEY=sk-...
VOICE_STT_PROVIDER=openai
VOICE_TTS_PROVIDER=openai
OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_TTS_VOICE=ash
```

## 2. Install dependencies

Backend:

```bash
uv sync
```

Frontend:

```bash
cd frontend
npm install
cd ..
```

## 3. Run the app

Start the backend:

```bash
PYTHONPATH=src uv run uvicorn prox_agent.api:app --port 8000 --reload
```

Start the frontend in a second terminal:

```bash
cd frontend
npm run dev
```

Open the Vite URL shown in the terminal, typically:

```text
http://localhost:5173
```

The frontend talks to `http://localhost:8000` by default. If your backend is elsewhere, set `VITE_API_BASE` in the frontend environment.

## 4. Optional smoke test

```bash
PYTHONPATH=src uv run python -m prox_agent.cli smoke
```

This validates the local knowledge bundle, deterministic lookups, OCR-backed retrieval, and image retrieval before using the full app.
