export type DocumentStatus = 'uploaded' | 'processing' | 'indexed' | 'failed';
export type DocumentFormat = 'pdf' | 'docx' | 'txt';

export interface Document {
  id: string;
  name: string;
  type: DocumentFormat;
  mime_type: string;
  size: number;
  status: DocumentStatus;
  title?: string | null;
  authors?: string[] | null;
  doi?: string | null;
  page_count?: number | null;
  uploaded_at: string;
  processing_error?: string | null;
  chunk_count?: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  items: Document[];
  total: number;
  limit: number;
  offset: number;
}
