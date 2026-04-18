# Voice Plan — Vulcan OmniPro 220 Agent

## Why voice here (not as a gimmick)

A welder in PPE — gloves, helmet down, arc striker in hand — cannot type. The existing text/image agent already answers the right questions; adding voice turns it into something a technician can actually use at the booth. That is the "expressive voice AI for complex physical products" story: voice is the interface that unlocks the knowledge base in the one environment where typing fails.

Two first-class moments where voice matters most:

1. **Mid-setup Q&A** — "what polarity for flux-core on 18-gauge?" → spoken answer + the wiring diagram pushed to the tablet.
2. **Safety callouts** — "power off the unit before swapping polarity" must *sound* like a warning, not a flat sentence. This is where expressive TTS (SSML pauses, emphasis, a lower register) earns its keep over a generic voice.

## Architecture

```
┌──────────────┐   audio    ┌──────────────┐   text    ┌──────────────┐
│  Browser     │ ─────────▶ │  FastAPI     │ ────────▶ │  ask_claude  │
│  MediaRec.   │            │  /voice/stt  │           │  (existing)  │
│  + mic UI    │ ◀───────── │  /voice/tts  │ ◀──────── │  structured  │
└──────────────┘  audio+SSE └──────────────┘   JSON    │  JSON        │
                                                      └──────────────┘
```

No new agent. Voice is a **transport layer** around the existing `ask_claude_stream` pipeline — same tools, same citations, same artifacts. The frontend still renders the diagram/table panel; voice only replaces the input textarea and the assistant bubble's rendering.

### Two phases, deliberately

- **Phase 1 — Push-to-talk (ship this week).** Hold-to-record → STT → existing `/chat/stream` → TTS streaming. Simple, demoable, and enough to prove the "hands-free at the booth" story. Works on any browser that supports `MediaRecorder`.
- **Phase 2 — Realtime / interruptible.** Swap to OpenAI `gpt-4o-realtime` or a WebRTC bridge so the user can barge in ("stop, just tell me the amperage"). Phase 1's endpoints stay — Phase 2 adds a `/voice/realtime` WebSocket beside them.

Ship Phase 1 end-to-end before touching Phase 2. Realtime voice is the kind of thing that eats a week of plumbing and shows nothing until the last day.

## Backend changes (`src/prox_agent/`)

### New module: `voice.py`

Thin wrappers, no business logic:

```python
async def transcribe(audio_bytes: bytes, mime: str) -> str: ...
async def synthesize_stream(
    text: str,
    *,
    ssml: bool = False,
    voice_id: str = "welder-calm",
) -> AsyncGenerator[bytes, None]: ...
```

Provider choice behind one env var (`VOICE_TTS_PROVIDER=elevenlabs|openai`). Default to ElevenLabs streaming for expressiveness; OpenAI TTS as the "works without a second account" fallback.

### New endpoints in `api.py`

```python
POST /voice/stt              # multipart audio → {text, confidence}
POST /voice/tts              # {text, ssml?, voice_id?} → audio/mpeg stream
POST /chat/voice/stream      # multipart audio → SSE (same shape as /chat/stream,
                             # plus a leading "transcript" event and a final
                             # "audio_url" or inline audio chunks)
```

`/chat/voice/stream` is the one the frontend actually calls in Phase 1. It:

1. Receives the recorded blob.
2. Runs STT → emits `{type: "transcript", text: "..."}` event so the UI can show what it heard.
3. Feeds the transcript into `ask_claude_stream(...)` — reusing the existing history/tool pipeline verbatim.
4. When the `done` event arrives, takes `answer_markdown`, runs it through `prepare_for_speech()` (see below), then emits a single `{type: "audio", mime, data_b64}` event with the full mp3. Chunked streaming playback is a Phase 1.5 refinement (see Risks).

Keeping it on the same SSE envelope means the frontend's streaming store (`store.ts`) gets one new event type (`audio`) and otherwise works unchanged.

### Expressiveness — tone instructions, not SSML

Original plan was SSML. Dropped it: OpenAI's TTS endpoint does not consume SSML, and ElevenLabs' SSML support is partial at best. What actually works on `gpt-4o-mini-tts` is the `instructions` field — free-text tone direction ("lower pitch and slow down for the Safety section"). That is where "expressive" lives now.

`prepare_for_speech(answer_markdown, safety_flags) -> (speakable_text, instructions)` in `src/prox_agent/voice.py`:

- Strips markdown headings, bold/italic, bullets, inline code, images, links.
- Replaces tables with "The full table is shown on screen." — tables read terribly aloud.
- Replaces code blocks with "(code shown on screen)".
- Normalizes welding units: `200A` → "200 amps", `24V` → "24 volts", `DCEP` → "D C E P, electrode positive", `DCEN` → "D C E N, electrode negative", etc.
- Prepends `Safety first. <flags>` when `safety_flags` is non-empty so the warning is spoken *before* the technical answer.
- Returns a tone-instruction string that is passed to OpenAI TTS via `instructions=`. When safety flags are present, the instruction explicitly tells the model to slow down, lower pitch, and pause before resuming.

This is the piece that differentiates from a Siri-grade demo — and it's the part a reviewer actually hears.

## Frontend changes (`frontend/src/`)

### Component: `VoiceButton.tsx` (shipped)

- Click-to-start / click-to-send mic button (not hold-to-talk — simpler, survives accidental mouseleave). `MediaRecorder` picks the first supported codec among `audio/webm;codecs=opus`, `audio/webm`, `audio/ogg;codecs=opus`, `audio/mp4`.
- Visual states: idle (mic icon) / recording (red pulsing square). Recording auto-stops the current audio playback before starting (barge-in).
- The optimistic user bubble shows `🎤 …` until the `transcript` event lands, then is replaced in-place with the recognized text.
- Future polish (not in Phase 1): animated waveform during recording, hold-to-talk + spacebar binding, voice selector dropdown.

### Store changes (`store.ts` — shipped)

- `sendVoiceMessage(blob, mime)` posts `multipart/form-data` (`audio` + `history` JSON) to `/chat/voice/stream` and reuses the existing SSE parsing loop.
- New event handlers:
  - `transcript` → replaces the `🎤 …` placeholder with the recognized text, sets chat title from the transcript if this was the first message.
  - `audio` → decodes base64 into a Blob and plays it via a singleton `HTMLAudioElement`. `stopPlayback()` action is exposed to `VoiceButton` for barge-in.
  - `tool_call` / `done` / `error` — reused unchanged.

### Nice touches — status

- **Barge-in:** ✅ shipped (`stopPlayback()` on new recording).
- **Voice selector:** deferred. Would need multiple `ELEVENLABS_VOICE_ID_*` env slots or mapping to OpenAI `voice` values; small but out of scope for Phase 1.
- **Captions:** ✅ already satisfied — the assistant text bubble renders regardless of whether audio played.

## Config / env (shipped)

All voice settings live in `.env` (see `.env.example` for the full list):

```bash
# Provider selection — both default to "openai"
VOICE_STT_PROVIDER=openai          # or deepgram
VOICE_TTS_PROVIDER=openai          # or elevenlabs

# OpenAI (used for STT and/or TTS depending on providers above)
OPENAI_API_KEY=sk-...
OPENAI_STT_MODEL=whisper-1
OPENAI_TTS_MODEL=gpt-4o-mini-tts   # required for `instructions` (expressive tone)
OPENAI_TTS_VOICE=ash               # any OpenAI voice: alloy, ash, ballad, coral, ...

# Alternatives
DEEPGRAM_API_KEY=
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
ELEVENLABS_MODEL=eleven_turbo_v2_5
```

Why `gpt-4o-mini-tts` as default: the older `tts-1` / `tts-1-hd` models ignore the `instructions` field, which is the entire mechanism our expressive-safety-warning behavior relies on. Override via `OPENAI_TTS_MODEL` if you want to trade expressiveness for raw latency.

Only one new Python dependency was added: `python-multipart` (required by FastAPI for `File`/`Form`). HTTP calls ride the existing `httpx` (transitive via `anthropic`). No WebSocket server needed in Phase 1.

## What "done" looks like for Phase 1

- Hold mic → speak "what polarity for stick on 3/32 E7018" → release.
- See "Heard: what polarity for stick on 3/32 E7018" within ~500ms.
- Hear a streamed answer starting within ~1.5s, with a clear pause + emphasized "power off the unit" before the polarity instruction.
- See the polarity table artifact appear in the right panel at the same time.
- Press mic mid-answer → audio stops instantly, new recording starts.

If all five of those work, the voice story for the JD is real, not aspirational.

## Phase 2 sketch (not now)

- `/voice/realtime` WebSocket that proxies to `gpt-4o-realtime` with the existing MCP tools registered as realtime tools. This is the path to true interruptibility and sub-500ms turn-taking.
- Wake-word ("hey vulcan") via `@picovoice/porcupine-web` for fully hands-free.
- Tool-call narration — speak "checking the duty cycle table..." while the tool runs, instead of a silent spinner. Uses the existing `tool_call` SSE events; just pipes them through TTS with a lighter voice profile.

## Risks / things to watch

- **TTS latency dominates perceived quality.** Measure first-byte-audio time; if ElevenLabs streaming isn't <600ms, switch default to OpenAI TTS and keep ElevenLabs for the "urgent/safety" voice only.
- **STT on noisy shop-floor audio.** Whisper struggles with angle-grinder background. Deepgram Nova-2 is noticeably better here and cheaper — worth A/B'ing before the demo.
- **Markdown → speech quality.** Tables and code blocks read terribly. `prepare_for_speech()` drops them and substitutes "The full table is shown on screen." / "(code shown on screen)". Verified on duty-cycle answers.
- **No chunked playback yet.** Phase 1 buffers the full mp3 server-side and emits one `audio` event at the end. Time-to-first-audio is dominated by TTS total time (~1.5–3s). Phase 1.5: switch to `{type: "audio_chunk", data_b64: ...}` + `{type: "audio_end"}` events and play via `MediaSource` so audio starts while TTS is still generating.
