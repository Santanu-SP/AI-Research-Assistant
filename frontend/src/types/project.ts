/** CamelCase matches the API aliases from the project schemas. */

import type { CollaboratorRole } from './collaboration';

export interface ResearchProject {
  id: string;
  name: string;
  description: string | null;
  version?: number;
  myRole?: CollaboratorRole;
  isShared?: boolean;
  memberCount?: number;
  ownerName?: string | null;
  archivedAt: string | null;
  createdAt: string;
  updatedAt: string;
  /** Files in the project; sent with project lists. */
  fileCount?: number | null;
  /** Finished research reports in the project; sent with project lists. */
  reportCount?: number | null;
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
  version?: number;
}

export interface ProjectListParams {
  search?: string;
  limit?: number;
  offset?: number;
  includeArchived?: boolean;
}
