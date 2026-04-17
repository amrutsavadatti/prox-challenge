from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from prox_agent.agent import ROOT, ask_claude, MissingAPIKeyError
from prox_agent.local_answer import answer_local

KNOWLEDGE_ROOT = ROOT.resolve()

app = FastAPI(title="Prox Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class HistoryTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str
    use_local: bool = False
    max_turns: int = 8
    history: list[HistoryTurn] = []


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "knowledge_root": str(KNOWLEDGE_ROOT)}


@app.post("/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    if req.use_local:
        return answer_local(question)

    history = [{"role": t.role, "content": t.content} for t in req.history]
    try:
        return await ask_claude(question, max_turns=req.max_turns, history=history)
    except MissingAPIKeyError:
        result = answer_local(question)
        result["fallback"] = "local (no API key)"
        return result


@app.get("/knowledge/{path:path}")
def serve_knowledge(path: str) -> FileResponse:
    candidate = (KNOWLEDGE_ROOT / path).resolve()
    if not str(candidate).startswith(str(KNOWLEDGE_ROOT)):
        raise HTTPException(status_code=403, detail="forbidden")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(candidate)
