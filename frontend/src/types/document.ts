export type DocumentStatus = 'uploaded' | 'processing' | 'indexed' | 'failed';
export type DocumentFormat = 'pdf' | 'docx' | 'pptx' | 'html' | 'markdown' | 'metadata' | 'txt';
export type SourceType = 'uploaded_file' | 'web_page' | 'doi' | 'openalex' | 'crossref';
export type ContentLevel = 'full_text' | 'abstract' | 'metadata_only' | 'web_page' | 'user_document';

export interface Document {
  id: string;
  projectId?: string | null;
  name: string;
  type: DocumentFormat;
  mimeType: string;
  size: number;
  sourceType: SourceType;
  sourceUri: string | null;
  sourceUrl: string | null;
  contentLevel: ContentLevel;
  status: DocumentStatus;
  ingestionStatus: DocumentStatus;
  title?: string | null;
  authors?: string[] | null;
  abstract?: string | null;
  doi?: string | null;
  openalexId?: string | null;
  crossrefId?: string | null;
  publicationYear?: number | null;
  publishedAt?: string | null;
  canonicalMetadata?: Record<string, unknown> | null;
  metadataProvenance?: Record<string, string> | null;
  parserName?: string | null;
  parserVersion?: string | null;
  ingestionVersion?: string | null;
  pageCount?: number | null;
  uploadedAt: string;
  processingError?: string | null;
  chunkCount?: number;
  createdAt: string;
  updatedAt: string;
}

export interface DocumentListResponse {
  items: Document[];
  total: number;
  limit: number;
  offset: number;
}
