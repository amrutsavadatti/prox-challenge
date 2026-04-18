"""Voice helpers: STT, TTS, and markdown→speech preparation.

Providers are chosen by env vars. Both STT and TTS are plain HTTP calls via
anthropic's transitive httpx dependency, so no new packages.

  VOICE_STT_PROVIDER = openai   (default) | deepgram
  VOICE_TTS_PROVIDER = openai   (default) | elevenlabs
"""
from __future__ import annotations

import os
import re
from collections.abc import AsyncGenerator
from pathlib import Path

import httpx
from dotenv import dotenv_values

_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def _env(key: str, default: str = "") -> str:
    """Read env var, falling back to `.env` file at repo root.

    Matches `agent.py`'s pattern so voice config lives in the same `.env`
    the rest of the app already uses — no separate `load_dotenv()` call
    required at startup.
    """
    if _ENV_PATH.exists():
        file_value = dotenv_values(_ENV_PATH).get(key)
        if isinstance(file_value, str) and file_value.strip():
            return file_value.strip()
    return os.getenv(key, default)


class VoiceConfigError(RuntimeError):
    """Raised when a provider is selected but its API key is missing."""


# ---------------------------------------------------------------------------
# STT
# ---------------------------------------------------------------------------

async def transcribe(audio_bytes: bytes, mime: str = "audio/webm") -> str:
    if not audio_bytes:
        return ""
    provider = _env("VOICE_STT_PROVIDER", "openai").lower()
    if provider == "deepgram":
        return await _transcribe_deepgram(audio_bytes, mime)
    return await _transcribe_openai(audio_bytes, mime)


async def _transcribe_openai(audio_bytes: bytes, mime: str) -> str:
    api_key = _env("OPENAI_API_KEY")
    if not api_key:
        raise VoiceConfigError("OPENAI_API_KEY not set for STT")
    model = _env("OPENAI_STT_MODEL", "whisper-1")
    ext = _ext_from_mime(mime)
    files = {"file": (f"audio.{ext}", audio_bytes, mime)}
    data = {"model": model, "response_format": "json"}
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files=files,
            data=data,
        )
        r.raise_for_status()
        return (r.json().get("text") or "").strip()


async def _transcribe_deepgram(audio_bytes: bytes, mime: str) -> str:
    api_key = _env("DEEPGRAM_API_KEY")
    if not api_key:
        raise VoiceConfigError("DEEPGRAM_API_KEY not set for STT")
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true",
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type": mime,
            },
            content=audio_bytes,
        )
        r.raise_for_status()
        data = r.json()
        return (
            data.get("results", {})
            .get("channels", [{}])[0]
            .get("alternatives", [{}])[0]
            .get("transcript", "")
            .strip()
        )


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------

async def synthesize_stream(
    text: str, *, instructions: str | None = None
) -> AsyncGenerator[bytes, None]:
    """Stream MP3 bytes for `text`. `instructions` shapes tone (OpenAI only)."""
    if not text.strip():
        return
    provider = _env("VOICE_TTS_PROVIDER", "openai").lower()
    if provider == "elevenlabs":
        async for chunk in _tts_elevenlabs(text):
            yield chunk
    else:
        async for chunk in _tts_openai(text, instructions):
            yield chunk


async def _tts_openai(
    text: str, instructions: str | None
) -> AsyncGenerator[bytes, None]:
    api_key = _env("OPENAI_API_KEY")
    if not api_key:
        raise VoiceConfigError("OPENAI_API_KEY not set for TTS")
    model = _env("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
    voice = _env("OPENAI_TTS_VOICE", "ash")
    payload: dict = {
        "model": model,
        "voice": voice,
        "input": text,
        "response_format": "mp3",
    }
    if instructions and model.startswith("gpt-4o"):
        payload["instructions"] = instructions

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        ) as r:
            if r.status_code >= 400:
                body = await r.aread()
                raise VoiceConfigError(
                    f"OpenAI TTS {r.status_code}: {body.decode('utf-8', errors='replace')}"
                )
            async for chunk in r.aiter_bytes(chunk_size=4096):
                if chunk:
                    yield chunk


async def _tts_elevenlabs(text: str) -> AsyncGenerator[bytes, None]:
    api_key = _env("ELEVENLABS_API_KEY")
    voice_id = _env("ELEVENLABS_VOICE_ID")
    model_id = _env("ELEVENLABS_MODEL", "eleven_turbo_v2_5")
    if not api_key or not voice_id:
        raise VoiceConfigError(
            "ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID required for TTS"
        )
    url = (
        f"https://api.elevenlabs.io/v1/text-to-speech/"
        f"{voice_id}/stream?output_format=mp3_44100_128"
    )
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.75, "style": 0.35},
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            url,
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json=payload,
        ) as r:
            r.raise_for_status()
            async for chunk in r.aiter_bytes(chunk_size=4096):
                if chunk:
                    yield chunk


# ---------------------------------------------------------------------------
# Markdown → speech preparation
# ---------------------------------------------------------------------------

_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_MD_CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_MD_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_MD_HEADING_RE = re.compile(r"^#+\s*", re.MULTILINE)
_MD_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_MD_ITAL_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_MD_BULLET_RE = re.compile(r"^\s*[-*]\s+", re.MULTILINE)
_TABLE_LINE_RE = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)

_UNIT_MAP = [
    (re.compile(r"(\d)\s*A\b"), r"\1 amps"),
    (re.compile(r"(\d)\s*V\b"), r"\1 volts"),
    (re.compile(r"(\d)\s*Hz\b"), r"\1 hertz"),
    (re.compile(r"(\d)\s*°F\b"), r"\1 degrees Fahrenheit"),
    (re.compile(r"(\d)\s*°C\b"), r"\1 degrees Celsius"),
    (re.compile(r"\bDCEP\b"), "D C E P, electrode positive"),
    (re.compile(r"\bDCEN\b"), "D C E N, electrode negative"),
    (re.compile(r"\bAC\b"), "A C"),
    (re.compile(r"\bMIG\b"), "MIG"),
    (re.compile(r"\bTIG\b"), "TIG"),
    (re.compile(r"\bFCAW\b"), "flux core"),
]


def prepare_for_speech(
    answer_markdown: str, safety_flags: list[str] | None = None
) -> tuple[str, str]:
    """Return (speakable_text, voice_instructions).

    Strips markdown that reads badly, replaces tables with a pointer to the
    on-screen artifact, normalizes welding unit abbreviations, and prepends
    safety flags with a short pause cue. `voice_instructions` is used by
    OpenAI `gpt-4o-mini-tts` to shape tone; ignored elsewhere.
    """
    text = answer_markdown or ""

    # Replace tables with a pointer — they read terribly aloud.
    if _TABLE_LINE_RE.search(text):
        text = _TABLE_LINE_RE.sub("", text)
        text = text.rstrip() + "\n\nThe full table is shown on screen."

    text = _MD_CODE_BLOCK_RE.sub("(code shown on screen)", text)
    text = _MD_IMAGE_RE.sub("", text)
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _MD_INLINE_CODE_RE.sub(r"\1", text)
    text = _MD_HEADING_RE.sub("", text)
    text = _MD_BOLD_RE.sub(r"\1", text)
    text = _MD_ITAL_RE.sub(r"\1", text)
    text = _MD_BULLET_RE.sub("", text)

    for pat, repl in _UNIT_MAP:
        text = pat.sub(repl, text)

    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    text = _sanitize_for_tts(text)

    has_safety = bool(safety_flags)
    if has_safety:
        flags_text = " ".join(s.rstrip(".") + "." for s in safety_flags)
        text = f"Safety first. {flags_text}\n\n{text}"

    instructions = _voice_instructions(has_safety=has_safety)
    return text, instructions


_CURLY_QUOTES = str.maketrans({
    "\u2018": "'", "\u2019": "'",   # '' → '
    "\u201c": '"', "\u201d": '"',   # "" → "
    "\u2014": " - ",                 # em-dash → spaced hyphen
    "\u2013": " to ",               # en-dash → "to"
    "\u2026": "...",                 # ellipsis
    "\u00a0": " ",                  # non-breaking space
})


def _sanitize_for_tts(text: str) -> str:
    """Replace characters that cause OpenAI TTS to return 'invalid characters'."""
    text = text.translate(_CURLY_QUOTES)
    # Collapse multiple spaces
    text = re.sub(r"  +", " ", text)
    # Strip any remaining control characters (except newline/tab)
    text = re.sub(r"[^\x09\x0a\x0d\x20-\x7e\u00a1-\uFFFF]", "", text)
    return text


def _voice_instructions(*, has_safety: bool) -> str:
    base = (
        "Speak as a calm, experienced welding technician. "
        "Measured pace. Clear enunciation of numbers and units. "
        "Slight pause before any numeric setting. "
        "Do not sound robotic; sound human and competent."
    )
    if has_safety:
        base += (
            " When you read the Safety section, slow down noticeably, lower "
            "your pitch, and carry real weight - this is a warning, not a "
            "footnote. Pause a beat before resuming the technical answer."
        )
    return base


def _ext_from_mime(mime: str) -> str:
    m = (mime or "").lower()
    if "webm" in m:
        return "webm"
    if "ogg" in m:
        return "ogg"
    if "mp4" in m or "m4a" in m:
        return "m4a"
    if "wav" in m:
        return "wav"
    if "mpeg" in m or "mp3" in m:
        return "mp3"
    return "webm"
