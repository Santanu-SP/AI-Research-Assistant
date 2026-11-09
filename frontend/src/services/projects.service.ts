import {
  CreateProjectInput,
  ProjectListParams,
  ResearchProject,
  ResearchProjectListResponse,
  UpdateProjectInput,
} from '../types/project';
import { ApiError, apiRequest } from './api';

export const projectsService = {
  async listProjects(
    params: ProjectListParams = {}
  ): Promise<ResearchProjectListResponse> {
    const query = new URLSearchParams();
    if (params.search?.trim()) query.set('search', params.search.trim());
    if (params.limit !== undefined) query.set('limit', String(params.limit));
    if (params.offset !== undefined) query.set('offset', String(params.offset));
    if (params.includeArchived) query.set('includeArchived', 'true');

    const qs = query.toString();
    return apiRequest<ResearchProjectListResponse>(
      qs ? `/projects?${qs}` : '/projects'
    );
  },

  async getProject(id: string): Promise<ResearchProject> {
    return apiRequest<ResearchProject>(`/projects/${encodeURIComponent(id)}`);
  },

  async createProject(input: CreateProjectInput): Promise<ResearchProject> {
    return apiRequest<ResearchProject>('/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    });
  },

  async updateProject(
    id: string,
    input: UpdateProjectInput
  ): Promise<ResearchProject> {
    return apiRequest<ResearchProject>(`/projects/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    });
  },

  async archiveProject(id: string): Promise<void> {
    await apiRequest<void>(`/projects/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    });
  },
};

export const getProjectErrorMessage = (
  error: unknown,
  fallback: string
): string => {
  if (!(error instanceof ApiError)) return fallback;

  if (error.status === 404) return 'Project not found.';
  if (error.status === 403) return 'You do not have access to this project.';
  if (error.status === 409) return 'A project with that name already exists.';
  if (error.status === 422) {
    const data = error.data as { detail?: unknown } | null;
    if (Array.isArray(data?.detail)) {
      const first = data.detail.find(
        (item): item is { msg: string } =>
          typeof item === 'object' &&
          item !== null &&
          typeof (item as { msg?: unknown }).msg === 'string'
      );
      if (first) return first.msg;
    }
    if (typeof data?.detail === 'string') return data.detail;
  }

  return fallback;
};
