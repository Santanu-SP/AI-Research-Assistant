/** CamelCase matches the API aliases from the project schemas. */

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

export interface CreateProjectInput {
  name: string;
  description?: string;
}

export interface UpdateProjectInput {
  name?: string;
  description?: string | null;
}

export interface ProjectListParams {
  search?: string;
  limit?: number;
  offset?: number;
  includeArchived?: boolean;
}
