import { ResearchStatus } from './research';

export type SourceType = 'peer-reviewed' | 'preprint' | 'institutional' | 'official-documentation' | 'web-article' | 'book' | 'other';

export interface CitationResponse {
  id: string;
  sourceId: string;
  number: number;
  position: number;
}

export interface ReportSectionResponse {
  id: string;
  heading: string;
  content: string;
  quote: string | null;
  position: number;
  citationIds: number[];
  citations: CitationResponse[];
  createdAt: string;
  updatedAt: string;
}

export interface SourceResponse {
  id: string;
  number: number;
  title: string;
  publisher: string;
  authors: string[];
  year: number;
  url: string | null;
  sourceType: SourceType;
  relevantExcerpt: string | null;
  citationCount: number;
  doi: string | null;
  bibtex: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ResearchReportResponse {
  id: string;
  researchId: string;
  title: string;
  summary: string;
  dossierRef: string;
  readingTimeMinutes: number;
  sourceCount: number;
  status: ResearchStatus;
  version: number;
  sections: ReportSectionResponse[];
  createdAt: string;
  updatedAt: string;
}

export interface ComposedReportResponse {
  report: ResearchReportResponse;
  sources: SourceResponse[];
}
