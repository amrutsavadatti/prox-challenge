from __future__ import annotations

import base64
import io
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image as PILImage
from pydantic import BaseModel

from prox_agent.agent import ROOT, ask_claude, MissingAPIKeyError
from prox_agent.local_answer import answer_local

UPLOAD_ROOT = (ROOT / "uploads").resolve()
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
MAX_IMAGE_EDGE = 1024
MAX_IMAGE_BYTES = 10 * 1024 * 1024
DATA_URL_RE = re.compile(r"^data:(?P<mime>[\w.+-]+/[\w.+-]+);base64,(?P<data>.+)$", re.DOTALL)

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


class ImageAttachment(BaseModel):
    name: str | None = None
    mime_type: str | None = None
    data_url: str


class ChatRequest(BaseModel):
    question: str
    use_local: bool = False
    max_turns: int = 8
    history: list[HistoryTurn] = []
    images: list[ImageAttachment] = []


def _save_uploaded_images(images: list[ImageAttachment]) -> list[str]:
    if not images:
        return []
    request_dir = UPLOAD_ROOT / uuid.uuid4().hex
    request_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for i, img in enumerate(images):
        match = DATA_URL_RE.match(img.data_url or "")
        if not match:
            raise HTTPException(status_code=400, detail=f"image {i} is not a valid data URL")
        try:
            raw = base64.b64decode(match.group("data"), validate=True)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"image {i} base64 decode failed: {exc}") from exc
        if len(raw) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail=f"image {i} exceeds {MAX_IMAGE_BYTES} bytes")
        try:
            with PILImage.open(io.BytesIO(raw)) as pil:
                pil.verify()
            with PILImage.open(io.BytesIO(raw)) as pil:
                pil = pil.convert("RGB")
                pil.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))
                target = request_dir / f"img_{i:02d}.jpg"
                pil.save(target, format="JPEG", quality=85, optimize=True)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"image {i} could not be read: {exc}") from exc
        saved.append(str(target))
    return saved


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "knowledge_root": str(KNOWLEDGE_ROOT)}


@app.post("/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    image_paths = _save_uploaded_images(req.images)

    if req.use_local:
        result = answer_local(question)
        if image_paths:
            result["fallback_note"] = "local mode ignores attached images"
        return result

    history = [{"role": t.role, "content": t.content} for t in req.history]
    try:
        return await ask_claude(
            question,
            max_turns=req.max_turns,
            history=history,
            image_paths=image_paths,
        )
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
