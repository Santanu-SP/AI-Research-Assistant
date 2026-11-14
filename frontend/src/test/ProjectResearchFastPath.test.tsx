// @vitest-environment jsdom
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const queryResearchMock = vi.fn();
const getResearchProgressMock = vi.fn();

vi.mock('../services/research.service', () => ({
  queryResearch: (...args: unknown[]) => queryResearchMock(...args),
  getResearchErrorMessage: (_err: unknown, fallback: string) => fallback,
}));

vi.mock('../services/progress.service', () => ({
  progressService: {
    getResearchProgress: (...args: unknown[]) => getResearchProgressMock(...args),
  },
}));

vi.mock('../components/layout/TopBar', () => ({
  TopBar: ({ breadcrumbs, rightActions }: { breadcrumbs?: React.ReactNode; rightActions?: React.ReactNode }) => (
    <header>
      {breadcrumbs}
      {rightActions}
    </header>
  ),
}));

import { ProjectResearchPanel } from '../components/projects/ProjectResearchPanel';
import { ResearchProgressPage } from '../pages/ResearchProgress';

describe('ProjectResearchPanel & ResearchProgress fast-path UX', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it('defaults inline project research to standard depth and supports switching to quick or deep', async () => {
    queryResearchMock.mockResolvedValue({
      researchId: 'res-1',
      projectId: 'proj-1',
      answer: 'Transformers use self-attention [S1].',
      citations: [],
      hybridCandidateCount: 3,
      evidenceCount: 1,
      insufficientEvidence: false,
    });

    render(
      <ProjectResearchPanel
        project={{
          id: 'proj-1',
          name: 'Attention Papers',
          description: null,
          createdAt: '2026-11-12T00:00:00Z',
          updatedAt: '2026-11-12T00:00:00Z',
          archivedAt: null,
        }}
        isArchived={false}
        readyCount={1}
      />
    );

    const textarea = screen.getByLabelText('Question');
    fireEvent.change(textarea, { target: { value: 'What is attention?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Research' }));

    await waitFor(() => {
      expect(queryResearchMock).toHaveBeenCalledWith({
        query: 'What is attention?',
        projectId: 'proj-1',
        researchDepth: 'standard',
      });
    });

    fireEvent.click(screen.getByRole('button', { name: 'New question' }));
    fireEvent.click(screen.getByRole('button', { name: 'quick' }));
    fireEvent.change(screen.getByLabelText('Question'), {
      target: { value: 'Quick check' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Research' }));

    await waitFor(() => {
      expect(queryResearchMock).toHaveBeenLastCalledWith({
        query: 'Quick check',
        projectId: 'proj-1',
        researchDepth: 'quick',
      });
    });

    fireEvent.click(screen.getByRole('button', { name: 'New question' }));
    fireEvent.click(screen.getByRole('button', { name: 'deep' }));
    fireEvent.change(screen.getByLabelText('Question'), {
      target: { value: 'Compare attention variants' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Research' }));

    await waitFor(() => {
      expect(queryResearchMock).toHaveBeenLastCalledWith({
        query: 'Compare attention variants',
        projectId: 'proj-1',
        researchDepth: 'deep',
      });
    });
  });

  it('discards stale in-flight project answers when switching projects', async () => {
    let resolveDeferred!: (value: unknown) => void;
    queryResearchMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveDeferred = resolve;
        })
    );

    const projectA = {
      id: 'proj-a',
      name: 'Project Alpha',
      description: null,
      createdAt: '2026-11-12T00:00:00Z',
      updatedAt: '2026-11-12T00:00:00Z',
      archivedAt: null,
    };
    const projectB = {
      id: 'proj-b',
      name: 'Project Beta',
      description: null,
      createdAt: '2026-11-12T00:00:00Z',
      updatedAt: '2026-11-12T00:00:00Z',
      archivedAt: null,
    };

    const { rerender } = render(
      <ProjectResearchPanel project={projectA} isArchived={false} readyCount={1} />
    );

    fireEvent.change(screen.getByLabelText('Question'), {
      target: { value: 'Alpha question?' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Research' }));

    // Switch to Project Beta while Project Alpha request is still in flight
    rerender(<ProjectResearchPanel project={projectB} isArchived={false} readyCount={1} />);

    // Switching back to Project Alpha before the old response arrives must still drop it
    rerender(<ProjectResearchPanel project={projectA} isArchived={false} readyCount={1} />);

    resolveDeferred({
      researchId: 'res-a',
      projectId: 'proj-a',
      answer: 'Stale Alpha answer.',
      citations: [],
      hybridCandidateCount: 1,
      evidenceCount: 1,
      insufficientEvidence: false,
    });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Research' })).toBeInTheDocument();
    });
    expect(screen.queryByText(/Stale Alpha answer/)).not.toBeInTheDocument();
  });

  it('auto-navigates to the completed report as soon as progress finishes', async () => {
    getResearchProgressMock.mockResolvedValue({
      id: 'run-42',
      projectId: null,
      question: 'What is attention?',
      status: 'completed',
      researchDepth: 'standard',
      currentStage: null,
      currentStepIndex: 4,
      totalSteps: 5,
      steps: [],
      sourcesDiscovered: 5,
      sourcesReviewed: 3,
      documentsFound: 1,
      startedAt: '2026-11-13T10:00:00Z',
      stageStartedAt: null,
      updatedAt: '2026-11-13T10:00:02Z',
      completedAt: '2026-11-13T10:00:02Z',
      failedAt: null,
    });

    render(
      <MemoryRouter initialEntries={['/research/run-42/progress']}>
        <Routes>
          <Route path="/research/:id/progress" element={<ResearchProgressPage />} />
          <Route path="/research/:id" element={<div>Report view reached</div>} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Report view reached')).toBeInTheDocument();
    });
  });
});
