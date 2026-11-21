import { ResearchStatus } from './research';
import type { SourceType } from './source';
import type { CollaboratorRole } from './collaboration';

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
  title: string | null;
  publisher: string | null;
  authors: string[];
  year: number | null;
  url: string | null;
  sourceType: SourceType;
  relevantExcerpt: string | null;
  citationCount: number;
  doi: string | null;
  bibtex: string | null;
  documentId: string | null;
  chunkId: string | null;
  page: number | null;
  section: string | null;
  rerankScore: number | null;
  createdAt: string;
  updatedAt: string;
}

export interface ResearchReportResponse {
  id: string;
  researchId: string;
  title: string;
  question?: string | null;
  summary: string;
  dossierRef: string;
  readingTimeMinutes: number;
  sourceCount: number;
  status: ResearchStatus;
  version: number;
  myRole?: CollaboratorRole;
  isShared?: boolean;
  sections: ReportSectionResponse[];
  createdAt: string;
  updatedAt: string;
}

export interface ReportFollowupResponse {
  id: string;
  reportId: string;
  authorId?: string | null;
  authorName?: string | null;
  question: string;
  answer: string;
  citationIds: number[];
  position: number;
  provider?: string | null;
  model?: string | null;
  insufficientEvidence: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface ReportFollowupRequest {
  question: string;
  preferredProvider?: string | null;
  modelOverride?: string | null;
  localFallbackEnabled?: boolean | null;
}

export interface ReportFollowupCreateResponse {
  followup: ReportFollowupResponse;
  sources: SourceResponse[];
  creditCost: number;
}

export interface ComposedReportResponse {
  report: ResearchReportResponse;
  sources: SourceResponse[];
  followups?: ReportFollowupResponse[];
}
