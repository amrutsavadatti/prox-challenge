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

  createChat: () => string;
  setActiveChat: (id: string) => void;
  deleteChat: (id: string) => void;
  sendMessage: (content: string, images?: AttachedImage[]) => void;
  setActiveArtifact: (artifact: Artifact | null) => void;
  closeArtifact: (id: string) => void;
  toggleSidebar: () => void;
  toggleArtifactPanel: () => void;
}

let nextId = 1;
const uid = () => `${Date.now()}-${nextId++}`;

export const useStore = create<AppState>()(persist((set, get) => ({
  chats: [],
  activeChatId: null,
  activeArtifact: null,
  openArtifacts: [],
  sidebarOpen: true,
  artifactPanelOpen: false,
  isStreaming: false,
  streamingStatus: null,

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

    set((s) => ({
      chats: s.chats.map((c) =>
        c.id === chatId
          ? {
              ...c,
              title: c.messages.length === 0 ? content.slice(0, 40) : c.title,
              messages: [...c.messages, userMsg],
              updatedAt: new Date(),
            }
          : c
      ),
      isStreaming: true,
      streamingStatus: null,
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

          // SSE events are separated by double newline
          const parts = buffer.split('\n\n');
          buffer = parts.pop() ?? '';

          for (const part of parts) {
            const dataLine = part.split('\n').find((l) => l.startsWith('data: '));
            if (!dataLine) continue;
            let event: any;
            try { event = JSON.parse(dataLine.slice(6)); } catch { continue; }

            if (event.type === 'tool_call') {
              set({ streamingStatus: event.label });
            } else if (event.type === 'done') {
              const artifacts = parseArtifacts(Array.isArray(event.artifacts) ? event.artifacts : []);
              const assistantMsg = {
                id: uid(),
                role: 'assistant' as const,
                content: String(event.answer_markdown ?? ''),
                artifacts,
                citations: Array.isArray(event.citations) ? event.citations as Citation[] : [],
                safetyFlags: Array.isArray(event.safety_flags) ? event.safety_flags as string[] : [],
                timestamp: new Date(),
              };
              set((s) => {
                const newOpenArtifacts = [...s.openArtifacts, ...artifacts];
                const latestArtifact = artifacts[artifacts.length - 1] ?? s.activeArtifact;
                return {
                  chats: s.chats.map((c) =>
                    c.id === chatId
                      ? { ...c, messages: [...c.messages, assistantMsg], updatedAt: new Date() }
                      : c
                  ),
                  isStreaming: false,
                  streamingStatus: null,
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
        const assistantMsg = {
          id: uid(),
          role: 'assistant' as const,
          content: `Error: ${err?.message ?? 'Request failed'}`,
          timestamp: new Date(),
        };
        set((s) => ({
          chats: s.chats.map((c) =>
            c.id === chatId
              ? { ...c, messages: [...c.messages, assistantMsg], updatedAt: new Date() }
              : c
          ),
          isStreaming: false,
          streamingStatus: null,
        }));
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
