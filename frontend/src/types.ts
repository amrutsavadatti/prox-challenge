export type ArtifactType = 'code' | 'html' | 'markdown' | 'mermaid' | 'table' | 'json' | 'image' | 'interactive';

export interface Artifact {
  id: string;
  title: string;
  type: ArtifactType;
  content: string;
  language?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  artifacts?: Artifact[];
  timestamp: Date;
}

export interface Chat {
  id: string;
  title: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
}
