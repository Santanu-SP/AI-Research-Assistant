export type DocumentStatus = 'uploaded' | 'processing' | 'indexed' | 'failed';
export type DocumentFormat = 'pdf' | 'docx' | 'txt';

export interface Document {
  id: string;
  name: string;
  type: DocumentFormat;
  mimeType: string;
  size: number;
  status: DocumentStatus;
  title?: string | null;
  authors?: string[] | null;
  doi?: string | null;
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
