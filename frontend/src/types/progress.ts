export type ResearchStatus = 'completed' | 'researching' | 'draft' | 'failed';
export type ResearchDepth = 'quick' | 'standard' | 'deep';
export type ResearchProgressStage =
  | 'planning'
  | 'searching_sources'
  | 'finding_documents'
  | 'reviewing_evidence'
  | 'building_synthesis';
export type ResearchProgressStepStatus = 'completed' | 'active' | 'pending' | 'failed';
/** Why a run stopped, in terms the UI can explain. */
export type ResearchFailureReason =
  | 'model_unavailable'
  | 'quota_reached'
  | 'no_ready_documents'
  | 'unexpected';

export interface ResearchProgressStep {
  id: ResearchProgressStage;
  title: string;
  status: ResearchProgressStepStatus;
}

export interface ResearchProgressResponse {
  id: string;
  projectId?: string | null;
  question: string;
  status: ResearchStatus;
  researchDepth: ResearchDepth;
  currentStage: ResearchProgressStage | null;
  currentStepIndex: number | null;
  totalSteps: number;
  steps: ResearchProgressStep[];
  sourcesDiscovered: number;
  sourcesReviewed: number;
  documentsFound: number;
  startedAt: string | null;
  stageStartedAt: string | null;
  updatedAt: string;
  completedAt: string | null;
  failedAt: string | null;
  failureReason?: ResearchFailureReason | null;
  documentsReady?: number;
  documentsPreparing?: number;
}
