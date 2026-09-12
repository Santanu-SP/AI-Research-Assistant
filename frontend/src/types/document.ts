export type DocumentStatus = 'ready' | 'processing' | 'failed';
export type DocumentFormat = 'PDF' | 'DOCX' | 'TXT' | 'MD';

export interface Document {
  id: string;
  name: string;
  type: DocumentFormat;
  size: number; // in bytes
  pageCount?: number;
  status: DocumentStatus;
  uploadedAt: string;
  notes?: string;
}
