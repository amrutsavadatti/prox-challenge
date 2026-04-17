import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { Chat, Artifact, Citation, AttachedImage } from './types';

const API_BASE = (import.meta as any).env?.VITE_API_BASE ?? 'http://localhost:8000';

async function fetchChat(
  question: string,
  history: { role: 'user' | 'assistant'; content: string }[],
  images: AttachedImage[],
): Promise<{
  text: string;
  artifacts: Artifact[];
  citations: Citation[];
  safetyFlags: string[];
}> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      history,
      images: images.map((img) => ({
        name: img.name,
        mime_type: img.mimeType,
        data_url: img.dataUrl,
      })),
    }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`chat request failed: ${res.status} ${detail}`);
  }
  const data = await res.json();
  const rawArtifacts = Array.isArray(data.artifacts) ? data.artifacts : [];
  const artifacts: Artifact[] = rawArtifacts.map((a: any) => ({
    id: String(a.id ?? `artifact-${Math.random().toString(36).slice(2)}`),
    title: String(a.title ?? 'Artifact'),
    type: a.type,
    content: typeof a.content === 'string' ? a.content : JSON.stringify(a.content ?? ''),
    language: a.language,
  }));
  return {
    text: String(data.answer_markdown ?? ''),
    artifacts,
    citations: Array.isArray(data.citations) ? data.citations : [],
    safetyFlags: Array.isArray(data.safety_flags) ? data.safety_flags : [],
  };
}

interface AppState {
  chats: Chat[];
  activeChatId: string | null;
  activeArtifact: Artifact | null;
  openArtifacts: Artifact[];
  sidebarOpen: boolean;
  artifactPanelOpen: boolean;
  isStreaming: boolean;

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

  createChat: () => {
    const state = get();
    const active = state.chats.find((c) => c.id === state.activeChatId);
    if (active && active.messages.length === 0) {
      set({
        activeArtifact: null,
        openArtifacts: [],
        artifactPanelOpen: false,
      });
      return active.id;
    }
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
    }));

    const priorMessages = state.chats.find((c) => c.id === chatId)?.messages ?? [];
    const history = priorMessages.map((m) => ({ role: m.role, content: m.content }));

    fetchChat(content, history, images)
      .then((response) => {
        const assistantMsg = {
          id: uid(),
          role: 'assistant' as const,
          content: response.text,
          artifacts: response.artifacts,
          citations: response.citations,
          safetyFlags: response.safetyFlags,
          timestamp: new Date(),
        };
        set((s) => {
          const newOpenArtifacts = [...s.openArtifacts, ...response.artifacts];
          const latestArtifact = response.artifacts[response.artifacts.length - 1] ?? s.activeArtifact;
          return {
            chats: s.chats.map((c) =>
              c.id === chatId
                ? { ...c, messages: [...c.messages, assistantMsg], updatedAt: new Date() }
                : c
            ),
            isStreaming: false,
            openArtifacts: newOpenArtifacts,
            activeArtifact: latestArtifact,
            artifactPanelOpen: response.artifacts.length > 0 ? true : s.artifactPanelOpen,
          };
        });
      })
      .catch((err: Error) => {
        const assistantMsg = {
          id: uid(),
          role: 'assistant' as const,
          content: `Error: ${err.message}`,
          timestamp: new Date(),
        };
        set((s) => ({
          chats: s.chats.map((c) =>
            c.id === chatId
              ? { ...c, messages: [...c.messages, assistantMsg], updatedAt: new Date() }
              : c
          ),
          isStreaming: false,
        }));
      });
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
