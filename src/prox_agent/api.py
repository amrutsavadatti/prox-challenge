from __future__ import annotations

import asyncio
import base64
import io
import json
import re
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from PIL import Image as PILImage
from pydantic import BaseModel

from prox_agent.agent import ROOT, ask_claude, ask_claude_stream, MissingAPIKeyError
from prox_agent.local_answer import answer_local
from prox_agent.voice import (
    VoiceConfigError,
    prepare_for_speech,
    synthesize_stream,
    transcribe,
)

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


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    image_paths = _save_uploaded_images(req.images)
    history = [{"role": t.role, "content": t.content} for t in req.history]

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for event in ask_claude_stream(
                question,
                max_turns=req.max_turns,
                history=history,
                image_paths=image_paths,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except MissingAPIKeyError:
            result = answer_local(question)
            result["type"] = "done"
            result["fallback"] = "local (no API key)"
            yield f"data: {json.dumps(result)}\n\n"
        except Exception as exc:
            error_event = {"type": "error", "message": str(exc)}
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class TTSRequest(BaseModel):
    text: str
    safety_flags: list[str] = []


@app.post("/voice/stt")
async def voice_stt(audio: UploadFile = File(...)) -> dict[str, Any]:
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty audio upload")
    try:
        text = await transcribe(data, mime=audio.content_type or "audio/webm")
    except VoiceConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"text": text}


@app.post("/voice/tts")
async def voice_tts(req: TTSRequest) -> StreamingResponse:
    spoken, instructions = prepare_for_speech(req.text, req.safety_flags)

    async def audio_stream() -> AsyncGenerator[bytes, None]:
        try:
            async for chunk in synthesize_stream(spoken, instructions=instructions):
                yield chunk
        except VoiceConfigError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return StreamingResponse(audio_stream(), media_type="audio/mpeg")


@app.post("/chat/voice/stream")
async def chat_voice_stream(
    audio: UploadFile = File(...),
    history: str = Form("[]"),
    max_turns: int = Form(8),
) -> StreamingResponse:
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="empty audio upload")
    mime = audio.content_type or "audio/webm"

    try:
        history_turns = json.loads(history) if history else []
        if not isinstance(history_turns, list):
            history_turns = []
    except json.JSONDecodeError:
        history_turns = []

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            transcript = await transcribe(audio_bytes, mime=mime)
        except VoiceConfigError as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            return
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': f'STT failed: {exc}'})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'transcript', 'text': transcript})}\n\n"

        if not transcript.strip():
            yield f"data: {json.dumps({'type': 'error', 'message': 'empty transcript'})}\n\n"
            return

        # TTS runs in parallel with the final text_delta events.
        # ask_claude_stream emits a `tts_start` event before `done` — we kick off
        # TTS as an asyncio task at that point so it overlaps with the frontend
        # rendering the last word-chunks.
        tts_task: asyncio.Task[list[bytes]] | None = None

        async def _collect_tts(spoken: str, instructions: str | None) -> list[bytes]:
            chunks: list[bytes] = []
            async for chunk in synthesize_stream(spoken, instructions=instructions):
                chunks.append(chunk)
            return chunks

        final: dict[str, Any] | None = None
        try:
            async for event in ask_claude_stream(
                transcript,
                max_turns=max_turns,
                history=history_turns,
            ):
                if event.get("type") == "tts_start":
                    # Start TTS now — don't yield this internal event to the client.
                    tts_task = asyncio.create_task(
                        _collect_tts(event.get("spoken", ""), event.get("instructions"))
                    )
                else:
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") == "done":
                        final = event
        except MissingAPIKeyError:
            final = answer_local(transcript)
            final["type"] = "done"
            final["fallback"] = "local (no API key)"
            yield f"data: {json.dumps(final)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            return

        if not final:
            return

        # Await the TTS task (already running in parallel); fall back to a fresh
        # call if it wasn't started (e.g. local fallback path).
        try:
            if tts_task is not None:
                audio_chunks = await tts_task
            else:
                spoken, instructions = prepare_for_speech(
                    str(final.get("answer_markdown") or ""),
                    list(final.get("safety_flags") or []),
                )
                if not spoken.strip():
                    return
                audio_chunks = await _collect_tts(spoken, None)
        except VoiceConfigError as exc:
            yield f"data: {json.dumps({'type': 'tts_error', 'message': str(exc)})}\n\n"
            return
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'tts_error', 'message': str(exc)})}\n\n"
            return

        if not audio_chunks:
            return

        payload = {
            "type": "audio",
            "mime": "audio/mpeg",
            "data_b64": base64.b64encode(b"".join(audio_chunks)).decode("ascii"),
        }
        yield f"data: {json.dumps(payload)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/knowledge/{path:path}")
def serve_knowledge(path: str) -> FileResponse:
    candidate = (KNOWLEDGE_ROOT / path).resolve()
    if not str(candidate).startswith(str(KNOWLEDGE_ROOT)):
        raise HTTPException(status_code=403, detail="forbidden")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(candidate)
