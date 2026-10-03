export interface ResearchProject {
  id: string;
  name: string;
  description: string | null;
  archivedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ResearchProjectListResponse {
  items: ResearchProject[];
  total: number;
  limit: number;
  offset: number;
}
