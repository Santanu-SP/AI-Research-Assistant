export type DocumentStatus = 'uploaded' | 'processing' | 'indexed' | 'failed';
export type DocumentFormat = 'pdf' | 'docx' | 'txt';

export interface Document {
  id: string;
  name: string;
  type: DocumentFormat;
  mime_type: string;
  size: number;
  status: DocumentStatus;
  created_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  items: Document[];
  total: number;
  limit: number;
  offset: number;
}
