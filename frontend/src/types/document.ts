export type DocumentStatus = 'uploaded' | 'processing' | 'indexed' | 'failed';
export type DocumentFormat =
  | 'pdf'
  | 'docx'
  | 'txt'
  | 'pptx'
  | 'xlsx'
  | 'html'
  | 'audio'
  | 'video'
  | 'image'
  | 'youtube'
  | 'web';
export type SourceType =
  | 'uploaded_file'
  | 'web_page'
  | 'doi'
  | 'openalex'
  | 'crossref'
  | 'youtube_video'
  | 'audio_file'
  | 'video_file'
  | 'image_file'
  | 'youtube_transcript'
  | 'audio_transcript'
  | 'video_transcript'
  | 'user_byok';
export type ContentLevel =
  | 'full_text'
  | 'abstract'
  | 'metadata_only'
  | 'web_page'
  | 'user_document'
  | 'transcript'
  | 'visual_analysis';

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
  /** While preparing: reading, ocr, embedding or saving. */
  processingStage?: string | null;
  /** 0-100 within the embedding step. */
  processingProgress?: number | null;
  /** List responses only: the project this file belongs to. */
  projectName?: string | null;
  /** List responses only: research runs limited to this file (a few, newest first). */
  usedIn?: DocumentUsage[];
  /** List responses only: how many research runs use this file in total. */
  usedInCount?: number;
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

export interface DocumentUsage {
  id: string;
  title: string;
}

/** Library filter groups; the server maps each to its file types. */
export type DocumentKind = 'documents' | 'images' | 'audio' | 'video' | 'links';
