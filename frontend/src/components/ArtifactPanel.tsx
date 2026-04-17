import { useEffect, useRef, useState } from 'react';
import { useStore } from '@/store';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  X,
  PanelRightClose,
  Copy,
  Check,
  Maximize2,
  Minimize2,
  Code2,
  FileText,
  Table2,
  Braces,
  Image,
  Workflow,
  Sliders,
} from 'lucide-react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import ReactMarkdown from 'react-markdown';
import type { Artifact } from '@/types';

function getArtifactIcon(type: string) {
  switch (type) {
    case 'code': return <Code2 size={14} />;
    case 'html':
    case 'interactive': return <Sliders size={14} />;
    case 'markdown': return <FileText size={14} />;
    case 'mermaid': return <Workflow size={14} />;
    case 'table': return <Table2 size={14} />;
    case 'json': return <Braces size={14} />;
    case 'image': return <Image size={14} />;
    default: return <Code2 size={14} />;
  }
}

function CodeViewer({ content, language }: { content: string; language?: string }) {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative h-full">
      <button
        onClick={copy}
        className="absolute top-3 right-3 z-10 p-1.5 rounded-md bg-white/10 hover:bg-white/20 transition-colors"
      >
        {copied ? <Check size={14} className="text-green-400" /> : <Copy size={14} className="text-gray-400" />}
      </button>
      <SyntaxHighlighter
        language={language ?? 'text'}
        style={oneDark}
        customStyle={{
          margin: 0,
          borderRadius: 0,
          height: '100%',
          fontSize: '13px',
          lineHeight: '1.6',
        }}
        showLineNumbers
      >
        {content}
      </SyntaxHighlighter>
    </div>
  );
}

function HtmlPreview({ content }: { content: string }) {
  const iframeRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    if (iframeRef.current) {
      const doc = iframeRef.current.contentDocument;
      if (doc) {
        doc.open();
        doc.write(content);
        doc.close();
      }
    }
  }, [content]);

  return (
    <iframe
      ref={iframeRef}
      className="w-full h-full border-0 bg-[#1a1a2e]"
      sandbox="allow-scripts allow-same-origin"
      title="Interactive Preview"
    />
  );
}

function MermaidViewer({ content }: { content: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState('');

  useEffect(() => {
    let cancelled = false;
    import('mermaid').then((mod) => {
      const mermaid = mod.default;
      mermaid.initialize({
        startOnLoad: false,
        theme: 'dark',
        themeVariables: {
          primaryColor: '#c084fc',
          primaryTextColor: '#fff',
          primaryBorderColor: '#8b5cf6',
          lineColor: '#6b7280',
          secondaryColor: '#1e293b',
          tertiaryColor: '#1e293b',
        },
      });
      mermaid.render('mermaid-' + Date.now(), content).then(({ svg }) => {
        if (!cancelled) setSvg(svg);
      }).catch(() => {
        if (!cancelled) setSvg('<p style="color:#ef4444;padding:20px;">Failed to render diagram. Check the Mermaid syntax.</p>');
      });
    });
    return () => { cancelled = true; };
  }, [content]);

  return (
    <div
      ref={containerRef}
      className="flex items-center justify-center h-full p-8 overflow-auto"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

function MarkdownViewer({ content }: { content: string }) {
  return (
    <ScrollArea className="h-full">
      <div className="p-6 prose prose-invert prose-sm max-w-none prose-headings:text-foreground prose-p:text-muted-foreground prose-strong:text-foreground prose-code:text-purple-400 prose-code:bg-muted prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:before:content-none prose-code:after:content-none prose-pre:bg-[#1e1e2e] prose-pre:border prose-pre:border-border prose-td:text-muted-foreground prose-th:text-foreground">
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>
    </ScrollArea>
  );
}

function TableViewer({ content }: { content: string }) {
  const data = JSON.parse(content) as { headers: string[]; rows: string[][] };

  return (
    <ScrollArea className="h-full">
      <div className="p-4">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              {data.headers.map((h, i) => (
                <th key={i} className="px-3 py-2.5 text-left font-semibold text-foreground whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, i) => (
              <tr key={i} className="border-b border-border/50 hover:bg-accent/50 transition-colors">
                {row.map((cell, j) => (
                  <td key={j} className="px-3 py-2.5 text-muted-foreground whitespace-nowrap">
                    {j === 0 ? <span className="font-medium text-foreground">{cell}</span> : cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ScrollArea>
  );
}

function JsonViewer({ content }: { content: string }) {
  return <CodeViewer content={content} language="json" />;
}

function renderArtifactContent(artifact: Artifact) {
  switch (artifact.type) {
    case 'code':
      return <CodeViewer content={artifact.content} language={artifact.language} />;
    case 'html':
    case 'interactive':
      return <HtmlPreview content={artifact.content} />;
    case 'markdown':
      return <MarkdownViewer content={artifact.content} />;
    case 'mermaid':
      return <MermaidViewer content={artifact.content} />;
    case 'table':
      return <TableViewer content={artifact.content} />;
    case 'json':
      return <JsonViewer content={artifact.content} />;
    case 'image': {
      const API_BASE = (import.meta as any).env?.VITE_API_BASE ?? 'http://localhost:8000';
      const src = /^https?:\/\//i.test(artifact.content)
        ? artifact.content
        : `${API_BASE}${artifact.content.startsWith('/') ? '' : '/'}${artifact.content}`;
      return (
        <div className="flex items-center justify-center h-full p-8">
          <img src={src} alt={artifact.title} className="max-w-full max-h-full object-contain rounded-lg" />
        </div>
      );
    }
    default:
      return <CodeViewer content={artifact.content} />;
  }
}

export function ArtifactPanel() {
  const { activeArtifact, openArtifacts, setActiveArtifact, closeArtifact, toggleArtifactPanel } = useStore();
  const [isFullscreen, setIsFullscreen] = useState(false);

  if (!activeArtifact) return null;

  return (
    <div className={`flex flex-col h-full bg-background border-l border-border ${isFullscreen ? 'fixed inset-0 z-50' : ''}`}>
      {/* Tabs */}
      <div className="flex items-center border-b border-border shrink-0 overflow-hidden">
        <ScrollArea className="flex-1">
          <div className="flex items-center h-11 px-1">
            {openArtifacts.map((artifact) => (
              <div
                key={artifact.id}
                role="button"
                tabIndex={0}
                onClick={() => setActiveArtifact(artifact)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setActiveArtifact(artifact);
                  }
                }}
                className={`group flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md mx-0.5 whitespace-nowrap transition-colors cursor-pointer ${
                  artifact.id === activeArtifact.id
                    ? 'bg-accent text-accent-foreground'
                    : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'
                }`}
              >
                {getArtifactIcon(artifact.type)}
                <span className="max-w-[120px] truncate">{artifact.title}</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    closeArtifact(artifact.id);
                  }}
                  className="ml-1 p-0.5 rounded opacity-0 group-hover:opacity-100 hover:bg-destructive/20 hover:text-destructive transition-all"
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        </ScrollArea>

        <div className="flex items-center gap-0.5 px-2 border-l border-border">
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            className="p-1.5 rounded-md hover:bg-accent transition-colors text-muted-foreground"
          >
            {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
          <button
            onClick={toggleArtifactPanel}
            className="p-1.5 rounded-md hover:bg-accent transition-colors text-muted-foreground"
          >
            <PanelRightClose size={14} />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {renderArtifactContent(activeArtifact)}
      </div>
    </div>
  );
}
