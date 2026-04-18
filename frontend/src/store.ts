import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { Chat, Artifact, Citation, AttachedImage } from './types';

const API_BASE = (import.meta as any).env?.VITE_API_BASE ?? 'http://localhost:8000';

function parseArtifacts(raw: any[]): Artifact[] {
  return raw.map((a: any) => ({
    id: String(a.id ?? `artifact-${Math.random().toString(36).slice(2)}`),
    title: String(a.title ?? 'Artifact'),
    type: a.type,
    content: typeof a.content === 'string' ? a.content : JSON.stringify(a.content ?? ''),
    language: a.language,
  }));
}

interface AppState {
  chats: Chat[];
  activeChatId: string | null;
  activeArtifact: Artifact | null;
  openArtifacts: Artifact[];
  sidebarOpen: boolean;
  artifactPanelOpen: boolean;
  isStreaming: boolean;
  streamingStatus: string | null;
  streamingMessageId: string | null;
  isPlayingAudio: boolean;

  createChat: () => string;
  setActiveChat: (id: string) => void;
  deleteChat: (id: string) => void;
  sendMessage: (content: string, images?: AttachedImage[]) => void;
  sendVoiceMessage: (audio: Blob, mime: string) => void;
  unlockAudio: () => void;
  stopPlayback: () => void;
  setActiveArtifact: (artifact: Artifact | null) => void;
  closeArtifact: (id: string) => void;
  toggleSidebar: () => void;
  toggleArtifactPanel: () => void;
}

let nextId = 1;
const uid = () => `${Date.now()}-${nextId++}`;

// ---------------------------------------------------------------------------
// Audio playback — uses Web Audio API so the context can be unlocked during
// the mic button press (a user gesture) and stays unlocked for the async TTS
// response that arrives several seconds later.
// ---------------------------------------------------------------------------
let audioCtx: AudioContext | null = null;
let currentSource: AudioBufferSourceNode | null = null;
let onAudioEndCb: (() => void) | null = null;

function getAudioContext(): AudioContext {
  if (!audioCtx || audioCtx.state === 'closed') {
    audioCtx = new (window.AudioContext ?? (window as any).webkitAudioContext)();
  }
  return audioCtx;
}

export function unlockAudioContext() {
  const ctx = getAudioContext();
  if (ctx.state === 'suspended') ctx.resume();
}

function stopCurrentAudio() {
  try { currentSource?.stop(); } catch { /* already stopped */ }
  currentSource = null;
  onAudioEndCb = null;
}

function playAudioFromBase64(b64: string, _mime: string, onEnd?: () => void) {
  stopCurrentAudio();
  if (!b64) return;
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)).buffer;
  const ctx = getAudioContext();
  if (ctx.state === 'suspended') ctx.resume();
  ctx.decodeAudioData(bytes).then((buffer) => {
    stopCurrentAudio();
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(ctx.destination);
    src.onended = () => {
      currentSource = null;
      onEnd?.();
    };
    src.start(0);
    currentSource = src;
    onAudioEndCb = onEnd ?? null;
  }).catch((err) => {
    console.warn('Audio decode failed:', err);
    onEnd?.();
  });
}

export const useStore = create<AppState>()(persist((set, get) => ({
  chats: [],
  activeChatId: null,
  activeArtifact: null,
  openArtifacts: [],
  sidebarOpen: true,
  artifactPanelOpen: false,
  isStreaming: false,
  streamingStatus: null,
  streamingMessageId: null,
  isPlayingAudio: false,

  createChat: () => {
    const id = uid();
    const chat: Chat = {
      id,
      title: 'New Chat',
      messages: [],
      createdAt: new Date(),
      updatedAt: new Date(),
    };
    set((s) => ({
      chats: [chat, ...s.chats],
      activeChatId: id,
      activeArtifact: null,
      openArtifacts: [],
      artifactPanelOpen: false,
    }));
    return id;
  },

  setActiveChat: (id) => {
    const chat = get().chats.find((c) => c.id === id);
    const allArtifacts = chat?.messages.flatMap((m) => m.artifacts ?? []) ?? [];
    set({
      activeChatId: id,
      openArtifacts: allArtifacts,
      activeArtifact: allArtifacts.length > 0 ? allArtifacts[allArtifacts.length - 1] : null,
      artifactPanelOpen: allArtifacts.length > 0,
    });
  },

  deleteChat: (id) => {
    set((s) => {
      const chats = s.chats.filter((c) => c.id !== id);
      const activeChatId = s.activeChatId === id ? (chats[0]?.id ?? null) : s.activeChatId;
      return { chats, activeChatId };
    });
  },

  sendMessage: (content, images = []) => {
    const state = get();
    let chatId = state.activeChatId;

    if (!chatId) {
      chatId = get().createChat();
    }

    const userMsg = {
      id: uid(),
      role: 'user' as const,
      content,
      images: images.length > 0 ? images : undefined,
      timestamp: new Date(),
    };

    // Insert a streaming placeholder message immediately so text deltas have somewhere to land
    const streamingMsgId = uid();
    set((s) => ({
      chats: s.chats.map((c) =>
        c.id === chatId
          ? {
              ...c,
              title: c.messages.length === 0 ? content.slice(0, 40) : c.title,
              messages: [...c.messages, userMsg, {
                id: streamingMsgId,
                role: 'assistant' as const,
                content: '',
                timestamp: new Date(),
              }],
              updatedAt: new Date(),
            }
          : c
      ),
      isStreaming: true,
      streamingStatus: null,
      streamingMessageId: streamingMsgId,
    }));

    const priorMessages = state.chats.find((c) => c.id === chatId)?.messages ?? [];
    const history = priorMessages.map((m) => ({ role: m.role, content: m.content }));

    const body = JSON.stringify({
      question: content,
      history,
      images: images.map((img) => ({
        name: img.name,
        mime_type: img.mimeType,
        data_url: img.dataUrl,
      })),
    });

    (async () => {
      try {
        const res = await fetch(`${API_BASE}/chat/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body,
        });

        if (!res.ok || !res.body) {
          throw new Error(`chat request failed: ${res.status}`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const parts = buffer.split('\n\n');
          buffer = parts.pop() ?? '';

          for (const part of parts) {
            const dataLine = part.split('\n').find((l) => l.startsWith('data: '));
            if (!dataLine) continue;
            let event: any;
            try { event = JSON.parse(dataLine.slice(6)); } catch { continue; }

            if (event.type === 'text_delta') {
              set((s) => ({
                chats: s.chats.map((c) =>
                  c.id === chatId
                    ? {
                        ...c,
                        messages: c.messages.map((m) =>
                          m.id === streamingMsgId
                            ? { ...m, content: m.content + String(event.text ?? '') }
                            : m
                        ),
                      }
                    : c
                ),
                streamingStatus: null,
              }));
            } else if (event.type === 'tool_call') {
              set({ streamingStatus: event.label });
            } else if (event.type === 'done') {
              const artifacts = parseArtifacts(Array.isArray(event.artifacts) ? event.artifacts : []);
              // Finalize: replace streaming placeholder with full structured message
              set((s) => {
                const newOpenArtifacts = [...s.openArtifacts, ...artifacts];
                const latestArtifact = artifacts[artifacts.length - 1] ?? s.activeArtifact;
                const finalContent = String(event.answer_markdown ?? '');
                return {
                  chats: s.chats.map((c) =>
                    c.id === chatId
                      ? {
                          ...c,
                          messages: c.messages.map((m) =>
                            m.id === streamingMsgId
                              ? {
                                  ...m,
                                  // Use streamed text if it matches; fall back to JSON answer_markdown
                                  content: m.content || finalContent,
                                  artifacts,
                                  citations: Array.isArray(event.citations) ? event.citations as Citation[] : [],
                                  safetyFlags: Array.isArray(event.safety_flags) ? event.safety_flags as string[] : [],
                                }
                              : m
                          ),
                          updatedAt: new Date(),
                        }
                      : c
                  ),
                  isStreaming: false,
                  streamingStatus: null,
                  streamingMessageId: null,
                  openArtifacts: newOpenArtifacts,
                  activeArtifact: latestArtifact,
                  artifactPanelOpen: artifacts.length > 0 ? true : s.artifactPanelOpen,
                };
              });
            } else if (event.type === 'error') {
              throw new Error(event.message ?? 'Unknown stream error');
            }
          }
        }
      } catch (err: any) {
        const errContent = `Error: ${err?.message ?? 'Request failed'}`;
        set((s) => ({
          chats: s.chats.map((c) =>
            c.id === chatId
              ? {
                  ...c,
                  messages: c.messages.map((m) =>
                    m.id === streamingMsgId ? { ...m, content: errContent } : m
                  ),
                }
              : c
          ),
          isStreaming: false,
          streamingStatus: null,
          streamingMessageId: null,
        }));
      }
    })();
  },

  unlockAudio: () => unlockAudioContext(),

  stopPlayback: () => {
    stopCurrentAudio();
    set({ isPlayingAudio: false });
  },

  sendVoiceMessage: (audio, mime) => {
    const state = get();
    let chatId = state.activeChatId;
    if (!chatId) chatId = get().createChat();

    stopCurrentAudio();

    const placeholderId = uid();
    const userMsg = {
      id: placeholderId,
      role: 'user' as const,
      content: '🎤 …',
      timestamp: new Date(),
    };

    const streamingMsgId = uid();
    set((s) => ({
      chats: s.chats.map((c) =>
        c.id === chatId
          ? {
              ...c,
              messages: [...c.messages, userMsg],
              updatedAt: new Date(),
            }
          : c
      ),
      isStreaming: true,
      streamingStatus: 'Transcribing…',
      streamingMessageId: streamingMsgId,
    }));

    const priorMessages = state.chats.find((c) => c.id === chatId)?.messages ?? [];
    const history = priorMessages.map((m) => ({ role: m.role, content: m.content }));

    const form = new FormData();
    form.append('audio', audio, `recording.${mime.includes('webm') ? 'webm' : 'ogg'}`);
    form.append('history', JSON.stringify(history));

    (async () => {
      try {
        const res = await fetch(`${API_BASE}/chat/voice/stream`, {
          method: 'POST',
          body: form,
        });
        if (!res.ok || !res.body) throw new Error(`voice request failed: ${res.status}`);

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let answerReceived = false;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const parts = buffer.split('\n\n');
          buffer = parts.pop() ?? '';

          for (const part of parts) {
            const dataLine = part.split('\n').find((l) => l.startsWith('data: '));
            if (!dataLine) continue;
            let event: any;
            try { event = JSON.parse(dataLine.slice(6)); } catch { continue; }

            if (event.type === 'transcript') {
              const transcript = String(event.text ?? '').trim() || '(no speech detected)';
              // Insert the streaming assistant placeholder now that we have a transcript
              set((s) => ({
                chats: s.chats.map((c) =>
                  c.id === chatId
                    ? {
                        ...c,
                        title: c.messages.filter((m) => m.id !== placeholderId).length === 0
                          ? transcript.slice(0, 40)
                          : c.title,
                        messages: [
                          ...c.messages.map((m) =>
                            m.id === placeholderId ? { ...m, content: transcript } : m
                          ),
                          { id: streamingMsgId, role: 'assistant' as const, content: '', timestamp: new Date() },
                        ],
                      }
                    : c
                ),
                streamingStatus: null,
              }));
            } else if (event.type === 'text_delta') {
              set((s) => ({
                chats: s.chats.map((c) =>
                  c.id === chatId
                    ? {
                        ...c,
                        messages: c.messages.map((m) =>
                          m.id === streamingMsgId
                            ? { ...m, content: m.content + String(event.text ?? '') }
                            : m
                        ),
                      }
                    : c
                ),
              }));
            } else if (event.type === 'tool_call') {
              set({ streamingStatus: event.label });
            } else if (event.type === 'error' && answerReceived) {
              console.warn('Voice post-answer error (TTS?):', event.message);
            } else if (event.type === 'done') {
              answerReceived = true;
              const artifacts = parseArtifacts(Array.isArray(event.artifacts) ? event.artifacts : []);
              const finalContent = String(event.answer_markdown ?? '');
              set((s) => {
                const newOpenArtifacts = [...s.openArtifacts, ...artifacts];
                const latestArtifact = artifacts[artifacts.length - 1] ?? s.activeArtifact;
                return {
                  chats: s.chats.map((c) =>
                    c.id === chatId
                      ? {
                          ...c,
                          messages: c.messages.map((m) =>
                            m.id === streamingMsgId
                              ? {
                                  ...m,
                                  content: m.content || finalContent,
                                  artifacts,
                                  citations: Array.isArray(event.citations) ? event.citations as Citation[] : [],
                                  safetyFlags: Array.isArray(event.safety_flags) ? event.safety_flags as string[] : [],
                                }
                              : m
                          ),
                          updatedAt: new Date(),
                        }
                      : c
                  ),
                  isStreaming: false,
                  streamingStatus: null,
                  streamingMessageId: null,
                  openArtifacts: newOpenArtifacts,
                  activeArtifact: latestArtifact,
                  artifactPanelOpen: artifacts.length > 0 ? true : s.artifactPanelOpen,
                };
              });
            } else if (event.type === 'audio') {
              set({ isPlayingAudio: true });
              playAudioFromBase64(
                String(event.data_b64 ?? ''),
                String(event.mime ?? 'audio/mpeg'),
                () => set({ isPlayingAudio: false }),
              );
            } else if (event.type === 'tts_error') {
              console.warn('TTS failed:', event.message);
            } else if (event.type === 'error') {
              throw new Error(event.message ?? 'voice stream error');
            }
          }
        }
      } catch (err: any) {
        // Only overwrite message content if the answer hasn't arrived yet.
        // Post-answer errors (TTS failures) must not clobber already-rendered text.
        if (!answerReceived) {
          const errContent = `Error: ${err?.message ?? 'Voice request failed'}`;
          set((s) => ({
            chats: s.chats.map((c) =>
              c.id === chatId
                ? {
                    ...c,
                    messages: c.messages.map((m) =>
                      m.id === streamingMsgId ? { ...m, content: errContent } : m
                    ),
                  }
                : c
            ),
            isStreaming: false,
            streamingStatus: null,
            streamingMessageId: null,
          }));
        } else {
          set({ isStreaming: false, streamingStatus: null, streamingMessageId: null });
          console.warn('Voice post-answer error:', err?.message);
        }
      }
    })();
  },

  setActiveArtifact: (artifact) => set((s) => {
    if (!artifact) return { activeArtifact: null, artifactPanelOpen: false };
    const alreadyOpen = s.openArtifacts.some((a) => a.id === artifact.id);
    return {
      activeArtifact: artifact,
      artifactPanelOpen: true,
      openArtifacts: alreadyOpen ? s.openArtifacts : [...s.openArtifacts, artifact],
    };
  }),

  closeArtifact: (id) => {
    set((s) => {
      const openArtifacts = s.openArtifacts.filter((a) => a.id !== id);
      const activeArtifact =
        s.activeArtifact?.id === id
          ? openArtifacts[openArtifacts.length - 1] ?? null
          : s.activeArtifact;
      return {
        openArtifacts,
        activeArtifact,
        artifactPanelOpen: openArtifacts.length > 0,
      };
    });
  },

  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  toggleArtifactPanel: () => set((s) => ({ artifactPanelOpen: !s.artifactPanelOpen })),
}), {
  name: 'prox-chat-store-v1',
  storage: createJSONStorage(() => localStorage),
  partialize: (s) => ({
    chats: s.chats,
    activeChatId: s.activeChatId,
    sidebarOpen: s.sidebarOpen,
  }),
  onRehydrateStorage: () => (state) => {
    if (!state) return;
    state.chats = (state.chats ?? []).map((c) => ({
      ...c,
      createdAt: new Date(c.createdAt),
      updatedAt: new Date(c.updatedAt),
      messages: (c.messages ?? []).map((m) => ({
        ...m,
        timestamp: new Date(m.timestamp),
      })),
    }));
  },
}));
