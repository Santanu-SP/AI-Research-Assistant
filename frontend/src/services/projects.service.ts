import { apiRequest } from './api';
import { ResearchProjectListResponse } from '../types/project';

export const projectsService = {
  list(): Promise<ResearchProjectListResponse> {
    return apiRequest<ResearchProjectListResponse>('/projects?limit=100');
  },
};
