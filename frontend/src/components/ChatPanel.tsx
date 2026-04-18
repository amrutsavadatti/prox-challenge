import { useState, useRef, useEffect } from 'react';
import { useStore } from '@/store';
import {
  Send,
  PanelLeft,
  Sparkles,
  User,
  Loader2,
  FileCode2,
  Paperclip,
  X,
  Download,
  Volume2,
} from 'lucide-react';
import type { Artifact, Citation, AttachedImage } from '@/types';
import { AlertTriangle } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { VoiceButton } from './VoiceButton';

const API_BASE = (import.meta as any).env?.VITE_API_BASE ?? 'http://localhost:8000';

function getArtifactExtension(artifact: Artifact): string {
  switch (artifact.type) {
    case 'markdown': return 'md';
    case 'json':
    case 'table': return 'json';
    case 'html':
    case 'interactive': return 'html';
    case 'mermaid': return 'mmd';
    case 'image': {
      const ext = artifact.content.split('.').pop()?.split('?')[0]?.toLowerCase();
      return ext && ['png','jpg','jpeg','gif','webp','svg'].includes(ext) ? ext : 'png';
    }
    default:
      return artifact.language ?? 'txt';
  }
}

function getMimeType(artifact: Artifact): string {
  switch (artifact.type) {
    case 'markdown': return 'text/markdown';
    case 'json':
    case 'table': return 'application/json';
    case 'html':
    case 'interactive': return 'text/html';
    default: return 'text/plain';
  }
}

async function downloadArtifact(artifact: Artifact) {
  const filename = `${artifact.title.replace(/[^a-z0-9_\-. ]/gi, '_')}.${getArtifactExtension(artifact)}`;

  if (artifact.type === 'image') {
    const src = /^https?:\/\//i.test(artifact.content)
      ? artifact.content
      : `${API_BASE}${artifact.content.startsWith('/') ? '' : '/'}${artifact.content}`;
    const res = await fetch(src);
    const blob = await res.blob();
    triggerDownload(URL.createObjectURL(blob), filename);
    return;
  }

  const blob = new Blob([artifact.content], { type: getMimeType(artifact) });
  triggerDownload(URL.createObjectURL(blob), filename);
}

function triggerDownload(url: string, filename: string) {
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

function MessageBubble({
  role,
  content,
  artifacts,
  citations,
  safetyFlags,
  images,
  isStreaming,
  streamingStatus,
  onArtifactClick,
}: {
  role: 'user' | 'assistant';
  content: string;
  artifacts?: Artifact[];
  citations?: Citation[];
  safetyFlags?: string[];
  images?: AttachedImage[];
  isStreaming?: boolean;
  streamingStatus?: string | null;
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
        {role === 'user' && images && images.length > 0 && (
          <div className="flex flex-wrap gap-2 justify-end">
            {images.map((img) => (
              <img
                key={img.id}
                src={img.dataUrl}
                alt={img.name}
                className="max-h-48 max-w-[240px] rounded-xl border border-border object-cover"
              />
            ))}
          </div>
        )}
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
            isStreaming && !content ? (
              <div className="flex items-center gap-2.5">
                <div className="flex gap-1 items-center">
                  <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:0ms]" />
                  <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:150ms]" />
                  <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:300ms]" />
                </div>
                {streamingStatus && (
                  <span className="text-xs text-muted-foreground animate-pulse">{streamingStatus}</span>
                )}
              </div>
            ) : (
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
            )
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
              <div key={artifact.id} className="flex items-center gap-1">
                <button
                  onClick={() => onArtifactClick(artifact)}
                  className="flex-1 flex items-center gap-3 px-3 py-2.5 rounded-xl border border-border bg-card hover:bg-accent transition-colors text-left group min-w-0"
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
                <button
                  onClick={() => void downloadArtifact(artifact)}
                  className="shrink-0 p-2 rounded-xl border border-border bg-card hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
                  title={`Download ${artifact.title}`}
                >
                  <Download size={15} />
                </button>
              </div>
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
  'How do I set up the Vulcan OmniPro 220 for MIG welding?',
  'What are the duty cycle limits at 200A on 240V?',
  'Show me the polarity settings for flux-core wire',
  'Help me troubleshoot poor arc stability',
  'What TIG settings should I use for 1/8" aluminum?',
  'Show me the wiring diagram for the work clamp',
];

const MAX_IMAGE_BYTES = 8 * 1024 * 1024;

function readImageAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ''));
    reader.onerror = () => reject(reader.error ?? new Error('read failed'));
    reader.readAsDataURL(file);
  });
}

export function ChatPanel() {
  const { chats, activeChatId, sendMessage, isStreaming, streamingStatus, streamingMessageId, isPlayingAudio, stopPlayback, sidebarOpen, toggleSidebar, setActiveArtifact } = useStore();
  const [input, setInput] = useState('');
  const [pendingImages, setPendingImages] = useState<AttachedImage[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [attachError, setAttachError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const attachFiles = async (fileList: FileList | File[] | null | undefined) => {
    if (!fileList) return;
    const files = Array.from(fileList).filter((f) => f.type.startsWith('image/'));
    if (files.length === 0) {
      setAttachError('Only image files are supported.');
      return;
    }
    const next: AttachedImage[] = [];
    for (const file of files) {
      if (file.size > MAX_IMAGE_BYTES) {
        setAttachError(`${file.name} is larger than 8 MB.`);
        continue;
      }
      try {
        const dataUrl = await readImageAsDataUrl(file);
        next.push({
          id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
          name: file.name,
          mimeType: file.type,
          dataUrl,
        });
      } catch {
        setAttachError(`Could not read ${file.name}.`);
      }
    }
    if (next.length > 0) {
      setPendingImages((cur) => [...cur, ...next]);
      setAttachError(null);
    }
  };

  const removePendingImage = (id: string) => {
    setPendingImages((cur) => cur.filter((img) => img.id !== id));
  };

  const activeChat = chats.find((c) => c.id === activeChatId);
  const messages = activeChat?.messages ?? [];

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages.length, isStreaming]);

  useEffect(() => {
    if (activeChatId && messages.length === 0) {
      textareaRef.current?.focus();
    }
  }, [activeChatId]);

  const handleSend = () => {
    const trimmed = input.trim();
    if ((!trimmed && pendingImages.length === 0) || isStreaming) return;
    sendMessage(trimmed || '(image attached)', pendingImages);
    setInput('');
    setPendingImages([]);
    setAttachError(null);
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
    <div
      className={`relative flex flex-col h-full bg-background ${isDragging ? 'ring-2 ring-primary/60' : ''}`}
      onDragOver={(e) => {
        if (Array.from(e.dataTransfer.items).some((i) => i.kind === 'file')) {
          e.preventDefault();
          setIsDragging(true);
        }
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target) setIsDragging(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setIsDragging(false);
        void attachFiles(e.dataTransfer.files);
      }}
    >
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
              images={msg.images}
              isStreaming={isStreaming && msg.id === streamingMessageId}
              streamingStatus={isStreaming && msg.id === streamingMessageId ? streamingStatus : null}
              onArtifactClick={(a) => setActiveArtifact(a)}
            />
          ))}

        </div>
      </div>

      {/* Input bar */}
      <div className="border-t border-border p-4 shrink-0">
        <div className="max-w-3xl mx-auto">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={(e) => {
              void attachFiles(e.target.files);
              if (fileInputRef.current) fileInputRef.current.value = '';
            }}
          />

          {pendingImages.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-2">
              {pendingImages.map((img) => (
                <div key={img.id} className="relative group">
                  <img
                    src={img.dataUrl}
                    alt={img.name}
                    className="h-16 w-16 rounded-lg border border-border object-cover"
                  />
                  <button
                    onClick={() => removePendingImage(img.id)}
                    className="absolute -top-1.5 -right-1.5 p-0.5 rounded-full bg-background border border-border opacity-80 hover:opacity-100 hover:bg-destructive hover:text-destructive-foreground transition"
                    aria-label={`Remove ${img.name}`}
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {attachError && (
            <p className="text-xs text-destructive mb-2">{attachError}</p>
          )}

          <div className="flex items-end gap-2 rounded-2xl border border-border bg-card px-4 py-3 focus-within:ring-2 focus-within:ring-ring/30 focus-within:border-ring transition-all">
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isStreaming}
              className="shrink-0 w-8 h-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent flex items-center justify-center disabled:opacity-40 transition-colors"
              aria-label="Attach image"
              title="Attach image"
            >
              <Paperclip size={16} />
            </button>
            <VoiceButton disabled={isStreaming} />
            {isPlayingAudio && (
              <button
                onClick={stopPlayback}
                title="Stop audio"
                className="shrink-0 w-8 h-8 rounded-lg bg-orange-500/20 text-orange-400 flex items-center justify-center hover:bg-orange-500/30 transition-colors"
              >
                <Volume2 size={16} className="animate-pulse" />
              </button>
            )}
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onInput={handleTextareaInput}
              onKeyDown={handleKeyDown}
              onPaste={(e) => {
                const imgs = Array.from(e.clipboardData.files).filter((f) => f.type.startsWith('image/'));
                if (imgs.length > 0) {
                  e.preventDefault();
                  void attachFiles(imgs);
                }
              }}
              placeholder="Ask about your equipment (or drop an image)..."
              rows={1}
              className="flex-1 resize-none bg-transparent text-sm placeholder:text-muted-foreground focus:outline-none min-h-[24px] max-h-[200px]"
            />
            <button
              onClick={handleSend}
              disabled={(!input.trim() && pendingImages.length === 0) || isStreaming}
              className="shrink-0 w-8 h-8 rounded-lg bg-primary text-primary-foreground flex items-center justify-center disabled:opacity-40 hover:bg-primary/90 transition-colors"
            >
              <Send size={16} />
            </button>
          </div>
          <p className="text-xs text-muted-foreground text-center mt-2">
            Press Enter to send, Shift+Enter for new line. Paste or drop images to attach.
          </p>
        </div>
      </div>

      {isDragging && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-primary/5 border-2 border-dashed border-primary/60 rounded-lg">
          <p className="text-sm font-medium text-primary">Drop image to attach</p>
        </div>
      )}
    </div>
  );
}
