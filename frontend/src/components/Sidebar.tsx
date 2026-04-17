import { useState } from "react";
import { useStore } from "@/store";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  MessageSquarePlus,
  Search,
  Trash2,
  PanelLeftClose,
} from "lucide-react";

export function Sidebar() {
  const {
    chats,
    activeChatId,
    createChat,
    setActiveChat,
    deleteChat,
    toggleSidebar,
  } = useStore();
  const [search, setSearch] = useState("");

  const filtered = chats.filter((c) =>
    c.title.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="flex flex-col h-full bg-sidebar text-sidebar-foreground">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-sidebar-border">
        <span className="text-sm font-semibold tracking-tight">Chats</span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => {
              const id = createChat();
              setActiveChat(id);
            }}
            className="p-1.5 rounded-md hover:bg-sidebar-accent transition-colors"
            title="New Chat"
          >
            <MessageSquarePlus size={18} />
          </button>
          <button
            onClick={toggleSidebar}
            className="p-1.5 rounded-md hover:bg-sidebar-accent transition-colors"
            title="Close sidebar"
          >
            <PanelLeftClose size={18} />
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="p-3">
        <div className="relative">
          <Search
            size={14}
            className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search chats..."
            className="w-full pl-8 pr-3 py-1.5 text-sm bg-sidebar-accent rounded-md border border-sidebar-border placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-sidebar-ring"
          />
        </div>
      </div>

      {/* Chat list */}
      <ScrollArea className="flex-1">
        <div className="px-2 pb-2 space-y-0.5">
          {filtered.length === 0 && (
            <p className="text-xs text-muted-foreground text-center py-8">
              {chats.length === 0
                ? "No chats yet. Start a new one!"
                : "No matching chats."}
            </p>
          )}
          {filtered.map((chat) => (
            <div
              key={chat.id}
              role="button"
              tabIndex={0}
              onClick={() => setActiveChat(chat.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") setActiveChat(chat.id);
              }}
              className={`group w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-sm transition-colors cursor-pointer ${
                chat.id === activeChatId
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "hover:bg-sidebar-accent/50 text-sidebar-foreground"
              }`}
            >
              <span className="flex-1 truncate">{chat.title}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  deleteChat(chat.id);
                }}
                className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-destructive/20 hover:text-destructive transition-all"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      </ScrollArea>

      {/* Footer */}
      <div className="p-3 border-t border-sidebar-border">
        <div className="flex items-center gap-2 px-2">
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center text-white text-xs font-bold">
            P
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">Product Assistant</p>
            <p className="text-xs text-muted-foreground">
              Made by Amrut with ❤️
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
