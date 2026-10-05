/**
 * Tests for ProjectContext.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import React from 'react';
import { ProjectProvider, useProject } from '../app/ProjectContext';
import { makeProject } from './fixtures';

// Mock the projects service
vi.mock('../services/projects.service', () => ({
  projectsService: {
    getProject: vi.fn(),
  },
  getProjectErrorMessage: (err: unknown, fallback: string) => fallback,
}));

import { projectsService } from '../services/projects.service';

const wrapper: React.FC<React.PropsWithChildren> = ({ children }) => (
  <ProjectProvider>{children}</ProjectProvider>
);

describe('ProjectContext / useProject', () => {
  beforeEach(() => {
    // Clear sessionStorage between tests
    sessionStorage.clear();
    vi.clearAllMocks();
  });

  afterEach(() => {
    sessionStorage.clear();
  });

  it('starts with no selected project', () => {
    const { result } = renderHook(() => useProject(), { wrapper });
    expect(result.current.selectedProject).toBeNull();
    expect(result.current.projectLoading).toBe(false);
  });

  it('selectProject triggers fetch and populates selectedProject', async () => {
    const fixture = makeProject();
    vi.mocked(projectsService.getProject).mockResolvedValue(fixture);

    const { result } = renderHook(() => useProject(), { wrapper });

    await act(async () => {
      result.current.selectProject('proj-alpha-123');
    });

    expect(result.current.selectedProject?.id).toBe('proj-alpha-123');
    expect(result.current.projectLoading).toBe(false);
  });

  it('clearProject resets to null', async () => {
    const fixture = makeProject();
    vi.mocked(projectsService.getProject).mockResolvedValue(fixture);

    const { result } = renderHook(() => useProject(), { wrapper });

    await act(async () => {
      result.current.selectProject('proj-alpha-123');
    });

    expect(result.current.selectedProject).not.toBeNull();

    act(() => {
      result.current.clearProject();
    });

    expect(result.current.selectedProject).toBeNull();
  });

  it('sets projectError on failed fetch', async () => {
    vi.mocked(projectsService.getProject).mockRejectedValue(
      new Error('Network error')
    );

    const { result } = renderHook(() => useProject(), { wrapper });

    await act(async () => {
      result.current.selectProject('proj-does-not-exist');
    });

    expect(result.current.selectedProject).toBeNull();
    expect(result.current.projectError).toBeTruthy();
  });

  it('persists selected project ID to sessionStorage', async () => {
    const fixture = makeProject();
    vi.mocked(projectsService.getProject).mockResolvedValue(fixture);

    const { result } = renderHook(() => useProject(), { wrapper });

    await act(async () => {
      result.current.selectProject('proj-alpha-123');
    });

    expect(sessionStorage.getItem('selected_project_id')).toBe('proj-alpha-123');
  });

  it('clears sessionStorage on clearProject', async () => {
    const fixture = makeProject();
    vi.mocked(projectsService.getProject).mockResolvedValue(fixture);

    const { result } = renderHook(() => useProject(), { wrapper });

    await act(async () => {
      result.current.selectProject('proj-alpha-123');
    });

    act(() => {
      result.current.clearProject();
    });

    expect(sessionStorage.getItem('selected_project_id')).toBeNull();
  });
});
