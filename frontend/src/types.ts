export type ArtifactType = 'code' | 'html' | 'markdown' | 'mermaid' | 'table' | 'json' | 'image' | 'interactive';

export interface Artifact {
  id: string;
  title: string;
  type: ArtifactType;
  content: string;
  language?: string;
}

export interface Citation {
  doc_id?: string;
  source_doc?: string;
  page?: number;
  element_id?: string;
  source_kind?: string;
  page_image?: string;
  excerpt?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  artifacts?: Artifact[];
  citations?: Citation[];
  safetyFlags?: string[];
  timestamp: Date;
}

export interface Chat {
  id: string;
  title: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
}
