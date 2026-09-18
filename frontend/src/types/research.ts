export type ResearchStatus = 'completed' | 'researching' | 'draft' | 'failed';
export type ResearchDepth = 'quick' | 'standard' | 'deep';

export interface Research {
  id: string;
  title: string;
  question: string;
  domain: string;
  status: ResearchStatus;
  researchDepth: ResearchDepth;
  sourceCount: number;
  createdAt: string;
  updatedAt: string;
  description?: string;
}

export interface ResearchResponse {
  id: string;
  title: string;
  question: string;
  domain: string | null;
  status: ResearchStatus;
  researchDepth: ResearchDepth;
  sourceCount: number;
  createdAt: string;
  updatedAt: string;
  archivedAt: string | null;
}

export interface CreateResearchInput {
  question: string;
  title?: string;
  domain?: string;
  researchDepth?: ResearchDepth;
}

export interface UpdateResearchInput {
  title?: string;
  question?: string;
  domain?: string | null;
  researchDepth?: ResearchDepth;
}

export interface ResearchListParams {
  search?: string;
  domain?: string;
  status?: ResearchStatus;
  limit?: number;
  offset?: number;
  includeArchived?: boolean;
}

export interface ResearchListResponse {
  items: ResearchResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface ResearchProgress {
  id: string;
  question: string;
  dossierRef: string;
  depth: ResearchDepth;
  startedAt: string;
  currentStepIndex: number;
  totalSteps: number;
  currentStepTitle: string;
  currentStepDescription?: string;
  steps: {
    id: string;
    number: string;
    title: string;
    status: 'completed' | 'active' | 'pending';
    detail: string;
  }[];
  sourcesDiscovered: number;
  sourcesReviewed: number;
  webAcademicCount: number;
  uploadedDocumentsCount: number;
  liveEvidence: {
    id: string;
    publisher: string;
    year: number;
    title: string;
    excerpt: string;
    statusTag: string;
    identifierLabel?: string;
    identifierValue?: string;
    authors?: string;
  }[];
  discoveredSources: {
    id: string;
    title: string;
    publisher: string;
    year: number;
    sourceType: string;
    authors: string;
  }[];
  ingestingQueueCount: number;
}

// Week 2: Research API Types

export interface ResearchQueryRequest {
  query: string;
  document_ids?: string[];
  options?: Record<string, any>;
}

export interface Citation {
  citation_id: string;
  document_id: string;
  paper_title: string;
  doi?: string;
  page?: number;
  section?: string;
  excerpt: string;
}

export interface EvidenceSource {
  document_id: string;
  title: string;
  authors?: string[];
  relevance_score?: number;
}

export interface ResearchQueryResponse {
  answer: string;
  citations: Citation[];
  evidence_sources: EvidenceSource[];
}
