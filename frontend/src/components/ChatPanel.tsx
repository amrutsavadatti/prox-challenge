import { useState, useRef, useEffect } from 'react';
import { useStore } from '@/store';
import {
  Send,
  PanelLeft,
  Sparkles,
  User,
  Loader2,
  FileCode2,
} from 'lucide-react';
import type { Artifact, Citation } from '@/types';
import { AlertTriangle } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

function MessageBubble({
  role,
  content,
  artifacts,
  citations,
  safetyFlags,
  onArtifactClick,
}: {
  role: 'user' | 'assistant';
  content: string;
  artifacts?: Artifact[];
  citations?: Citation[];
  safetyFlags?: string[];
  onArtifactClick: (a: Artifact) => void;
}) {
  return (
    <div className={`flex gap-3 ${role === 'user' ? 'justify-end' : ''}`}>
      {role === 'assistant' && (
        <div className="shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-orange-400 to-amber-600 flex items-center justify-center mt-1">
          <Sparkles size={16} className="text-white" />
        </div>
      )}
      <div className={`max-w-[80%] space-y-2 ${role === 'user' ? 'order-first' : ''}`}>
        {role === 'assistant' && safetyFlags && safetyFlags.length > 0 && (
          <div className="flex items-start gap-2 px-3 py-2 rounded-xl border border-yellow-500/40 bg-yellow-500/10 text-xs text-yellow-200">
            <AlertTriangle size={14} className="shrink-0 mt-0.5" />
            <div className="space-y-0.5">
              {safetyFlags.map((flag) => (
                <p key={flag} className="leading-snug">{flag.replace(/_/g, ' ')}</p>
              ))}
            </div>
          </div>
        )}
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
            role === 'user'
              ? 'bg-primary text-primary-foreground rounded-br-md'
              : 'bg-muted text-foreground rounded-bl-md'
          }`}
        >
          {role === 'assistant' ? (
            <div className="prose prose-sm prose-invert max-w-none
              prose-p:my-1.5 prose-headings:mt-3 prose-headings:mb-1.5
              prose-ul:my-1.5 prose-ol:my-1.5 prose-li:my-0.5
              prose-hr:my-3 prose-table:my-2
              prose-th:border prose-th:border-border prose-th:px-2 prose-th:py-1 prose-th:bg-muted-foreground/10
              prose-td:border prose-td:border-border prose-td:px-2 prose-td:py-1
              prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:bg-muted-foreground/10 prose-code:before:content-none prose-code:after:content-none
              prose-strong:text-foreground">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
            </div>
          ) : (
            content.split('\n').map((line, i) => (
              <p key={i} className={line === '' ? 'h-2' : ''}>{line}</p>
            ))
          )}
        </div>

        {role === 'assistant' && citations && citations.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {citations.map((c, i) => {
              const label = c.source_doc
                ? `${c.source_doc}${c.page ? ` p.${c.page}` : ''}`
                : c.element_id ?? `source ${i + 1}`;
              return (
                <span
                  key={`${c.element_id ?? c.source_doc ?? 'cite'}-${i}`}
                  className="text-[11px] px-2 py-0.5 rounded-full border border-border bg-card text-muted-foreground"
                  title={c.excerpt}
                >
                  {label}
                </span>
              );
            })}
          </div>
        )}

        {/* Artifact cards */}
        {artifacts && artifacts.length > 0 && (
          <div className="space-y-1.5">
            {artifacts.map((artifact) => (
              <button
                key={artifact.id}
                onClick={() => onArtifactClick(artifact)}
                className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl border border-border bg-card hover:bg-accent transition-colors text-left group"
              >
                <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-purple-500/20 to-indigo-500/20 flex items-center justify-center shrink-0">
                  <FileCode2 size={18} className="text-purple-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate group-hover:text-purple-400 transition-colors">
                    {artifact.title}
                  </p>
                  <p className="text-xs text-muted-foreground capitalize">
                    {artifact.type === 'interactive' ? 'Interactive Widget' : artifact.type}
                  </p>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
      {role === 'user' && (
        <div className="shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-cyan-600 flex items-center justify-center mt-1">
          <User size={16} className="text-white" />
        </div>
      )}
    </div>
  );
}

const SUGGESTIONS = [
  'How do I wire a stepper motor?',
  'Help me configure print settings',
  'TIG welding parameters for aluminum',
  'Troubleshoot thermal runaway error',
  'Compare filament materials',
  'Show firmware configuration',
];

export function ChatPanel() {
  const { chats, activeChatId, sendMessage, isStreaming, sidebarOpen, toggleSidebar, setActiveArtifact } = useStore();
  const [input, setInput] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const activeChat = chats.find((c) => c.id === activeChatId);
  const messages = activeChat?.messages ?? [];

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages.length, isStreaming]);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    sendMessage(trimmed);
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleTextareaInput = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 200) + 'px';
    }
  };

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 h-14 border-b border-border shrink-0">
        {!sidebarOpen && (
          <button
            onClick={toggleSidebar}
            className="p-1.5 rounded-md hover:bg-accent transition-colors"
          >
            <PanelLeft size={18} />
          </button>
        )}
        <h1 className="text-sm font-semibold">
          {activeChat?.title ?? 'Product Assistant'}
        </h1>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto" ref={scrollRef}>
        <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center pt-20">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-orange-400 to-amber-600 flex items-center justify-center mb-6 shadow-lg">
                <Sparkles size={32} className="text-white" />
              </div>
              <h2 className="text-2xl font-semibold mb-2">How can I help?</h2>
              <p className="text-muted-foreground text-sm mb-8 text-center max-w-md">
                Ask me anything about your equipment — I'll provide interactive guides, wiring diagrams, and troubleshooting tools.
              </p>
              <div className="grid grid-cols-2 gap-2 w-full max-w-lg">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => {
                      setInput(s);
                      textareaRef.current?.focus();
                    }}
                    className="text-left text-sm px-4 py-3 rounded-xl border border-border hover:bg-accent hover:border-accent-foreground/20 transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              role={msg.role}
              content={msg.content}
              artifacts={msg.artifacts}
              citations={msg.citations}
              safetyFlags={msg.safetyFlags}
              onArtifactClick={(a) => setActiveArtifact(a)}
            />
          ))}

          {isStreaming && (
            <div className="flex gap-3">
              <div className="shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-orange-400 to-amber-600 flex items-center justify-center">
                <Sparkles size={16} className="text-white" />
              </div>
              <div className="bg-muted rounded-2xl rounded-bl-md px-4 py-3">
                <Loader2 size={18} className="animate-spin text-muted-foreground" />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Input bar */}
      <div className="border-t border-border p-4 shrink-0">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-end gap-2 rounded-2xl border border-border bg-card px-4 py-3 focus-within:ring-2 focus-within:ring-ring/30 focus-within:border-ring transition-all">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onInput={handleTextareaInput}
              onKeyDown={handleKeyDown}
              placeholder="Ask about your equipment..."
              rows={1}
              className="flex-1 resize-none bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none min-h-[24px] max-h-[200px]"
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || isStreaming}
              className="shrink-0 w-8 h-8 rounded-lg bg-primary text-primary-foreground flex items-center justify-center disabled:opacity-40 hover:bg-primary/90 transition-colors"
            >
              <Send size={16} />
            </button>
          </div>
          <p className="text-xs text-muted-foreground text-center mt-2">
            Press Enter to send, Shift+Enter for new line
          </p>
        </div>
      </div>
    </div>
  );
}
