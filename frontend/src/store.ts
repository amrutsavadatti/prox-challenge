import { create } from 'zustand';
import type { Chat, Artifact } from './types';
import { generateMockResponse } from './mock-data';

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
  sendMessage: (content: string) => void;
  setActiveArtifact: (artifact: Artifact | null) => void;
  closeArtifact: (id: string) => void;
  toggleSidebar: () => void;
  toggleArtifactPanel: () => void;
}

let nextId = 1;
const uid = () => `${Date.now()}-${nextId++}`;

export const useStore = create<AppState>((set, get) => ({
  chats: [],
  activeChatId: null,
  activeArtifact: null,
  openArtifacts: [],
  sidebarOpen: true,
  artifactPanelOpen: false,
  isStreaming: false,

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

  sendMessage: (content) => {
    const state = get();
    let chatId = state.activeChatId;

    if (!chatId) {
      chatId = get().createChat();
    }

    const userMsg = {
      id: uid(),
      role: 'user' as const,
      content,
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

    // Simulate response delay
    setTimeout(() => {
      const mockResponse = generateMockResponse(content);
      const assistantMsg = {
        id: uid(),
        role: 'assistant' as const,
        content: mockResponse.text,
        artifacts: mockResponse.artifacts,
        timestamp: new Date(),
      };

      set((s) => {
        const newOpenArtifacts = [
          ...s.openArtifacts,
          ...(mockResponse.artifacts ?? []),
        ];
        const latestArtifact = mockResponse.artifacts?.[mockResponse.artifacts.length - 1] ?? s.activeArtifact;
        return {
          chats: s.chats.map((c) =>
            c.id === chatId
              ? {
                  ...c,
                  messages: [...c.messages, assistantMsg],
                  updatedAt: new Date(),
                }
              : c
          ),
          isStreaming: false,
          openArtifacts: newOpenArtifacts,
          activeArtifact: latestArtifact,
          artifactPanelOpen: mockResponse.artifacts ? mockResponse.artifacts.length > 0 : s.artifactPanelOpen,
        };
      });
    }, 800 + Math.random() * 1200);
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
}));
