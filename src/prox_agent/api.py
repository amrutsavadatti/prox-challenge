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
    data_url: str | None = None
    server_url: str | None = None  # /uploads/... from POST /upload


class ChatRequest(BaseModel):
    question: str
    use_local: bool = False
    max_turns: int = 8
    history: list[HistoryTurn] = []
    images: list[ImageAttachment] = []


def _process_and_save_image(raw: bytes, target: Path) -> None:
    """Resize and save raw image bytes as JPEG to target path."""
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail=f"image exceeds {MAX_IMAGE_BYTES} bytes")
    try:
        with PILImage.open(io.BytesIO(raw)) as pil:
            pil = pil.convert("RGB")
            pil.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))
            pil.save(target, format="JPEG", quality=85, optimize=True)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"could not process image: {exc}") from exc


def _save_uploaded_images(images: list[ImageAttachment]) -> list[str]:
    if not images:
        return []
    saved: list[str] = []
    for i, img in enumerate(images):
        # Fast path: image was already uploaded via POST /upload
        if img.server_url:
            rel = img.server_url.removeprefix("/uploads/")
            candidate = (UPLOAD_ROOT / rel).resolve()
            if str(candidate).startswith(str(UPLOAD_ROOT)) and candidate.is_file():
                saved.append(str(candidate))
                continue
            raise HTTPException(status_code=400, detail=f"image {i} server_url not found")

        # Slow path: raw data_url sent inline (legacy / fallback)
        match = DATA_URL_RE.match(img.data_url or "")
        if not match:
            raise HTTPException(status_code=400, detail=f"image {i} needs data_url or server_url")
        try:
            raw = base64.b64decode(match.group("data"), validate=True)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"image {i} base64 decode failed: {exc}") from exc
        request_dir = UPLOAD_ROOT / uuid.uuid4().hex
        request_dir.mkdir(parents=True, exist_ok=True)
        target = request_dir / f"img_{i:02d}.jpg"
        _process_and_save_image(raw, target)
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

        async def _collect_tts(spoken: str, instructions: str | None) -> list[bytes]:
            chunks: list[bytes] = []
            async for chunk in synthesize_stream(spoken, instructions=instructions):
                chunks.append(chunk)
            return chunks

        def _sentence_end(text: str) -> int:
            """Return index after first sentence boundary (min 20 chars), or -1."""
            for i in range(20, len(text)):
                c = text[i]
                if c in ".!?" and (i + 1 >= len(text) or text[i + 1] in " \n"):
                    return i + 1
                if c == "\n" and i + 1 < len(text) and text[i + 1] == "\n":
                    return i + 2
            return -1

        # Sentence-level TTS: start a TTS task for each complete sentence as it
        # arrives so audio and text overlap. Tasks run concurrently; we drain
        # them in order after `done` to guarantee correct playback sequence.
        tts_tasks: list[asyncio.Task[list[bytes]]] = []
        tts_instructions: str | None = None
        sentence_buf = ""
        final: dict[str, Any] | None = None

        try:
            async for event in ask_claude_stream(
                transcript,
                max_turns=max_turns,
                history=history_turns,
            ):
                etype = event.get("type")

                if etype == "tts_start":
                    # Capture voice instructions; flush any remaining buffer as
                    # the last TTS chunk. Don't forward this internal event.
                    tts_instructions = event.get("instructions")
                    if sentence_buf.strip():
                        spoken, _ = prepare_for_speech(sentence_buf.strip(), [])
                        if spoken.strip():
                            tts_tasks.append(asyncio.create_task(
                                _collect_tts(spoken, tts_instructions)
                            ))
                        sentence_buf = ""
                    continue

                if etype == "text_delta":
                    sentence_buf += str(event.get("text", ""))
                    # Extract and enqueue complete sentences immediately.
                    while True:
                        idx = _sentence_end(sentence_buf)
                        if idx == -1:
                            break
                        sentence = sentence_buf[:idx].strip()
                        sentence_buf = sentence_buf[idx:].lstrip("\n ")
                        if sentence:
                            spoken, _ = prepare_for_speech(sentence, [])
                            if spoken.strip():
                                tts_tasks.append(asyncio.create_task(
                                    _collect_tts(spoken, tts_instructions)
                                ))

                yield f"data: {json.dumps(event)}\n\n"
                if etype == "done":
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

        # Fallback: if no sentence tasks were queued (e.g. local path), synthesise
        # the full answer in one shot.
        if not tts_tasks:
            spoken, instructions = prepare_for_speech(
                str(final.get("answer_markdown") or ""),
                list(final.get("safety_flags") or []),
            )
            if spoken.strip():
                tts_tasks.append(asyncio.create_task(_collect_tts(spoken, instructions)))

        # Drain tasks in submission order — guarantees sentences play in sequence.
        for task in tts_tasks:
            try:
                audio_chunks = await task
            except VoiceConfigError as exc:
                yield f"data: {json.dumps({'type': 'tts_error', 'message': str(exc)})}\n\n"
                return
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'tts_error', 'message': str(exc)})}\n\n"
                continue
            if audio_chunks:
                payload = {
                    "type": "audio_chunk",
                    "mime": "audio/mpeg",
                    "data_b64": base64.b64encode(b"".join(audio_chunks)).decode("ascii"),
                }
                yield f"data: {json.dumps(payload)}\n\n"

        yield f"data: {json.dumps({'type': 'audio_end'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/upload")
async def upload_image(image: UploadFile = File(...)) -> dict[str, Any]:
    data = await image.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    slot = uuid.uuid4().hex
    request_dir = UPLOAD_ROOT / slot
    request_dir.mkdir(parents=True, exist_ok=True)
    target = request_dir / "img.jpg"
    _process_and_save_image(data, target)
    return {"url": f"/uploads/{slot}/img.jpg"}


@app.get("/uploads/{path:path}")
def serve_upload(path: str) -> FileResponse:
    candidate = (UPLOAD_ROOT / path).resolve()
    if not str(candidate).startswith(str(UPLOAD_ROOT)):
        raise HTTPException(status_code=403, detail="forbidden")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(candidate)


@app.get("/knowledge/{path:path}")
def serve_knowledge(path: str) -> FileResponse:
    candidate = (KNOWLEDGE_ROOT / path).resolve()
    if not str(candidate).startswith(str(KNOWLEDGE_ROOT)):
        raise HTTPException(status_code=403, detail="forbidden")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(candidate)
