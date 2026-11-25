// @vitest-environment jsdom
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ResearchProgressResponse } from '../types/progress';

const getProgressMock = vi.fn();
const pauseMock = vi.fn();
const editQuestionMock = vi.fn();
const getReportMock = vi.fn();

vi.mock('../app/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 'u1',
      name: 'Researcher',
      email: 'researcher@example.com',
      isActive: true,
      createdAt: '2026-11-25T00:00:00Z',
      updatedAt: '2026-11-25T00:00:00Z',
    },
    logout: vi.fn(),
    logoutAll: vi.fn(),
  }),
}));

vi.mock('../services/progress.service', () => ({
  progressService: {
    getResearchProgress: (...args: unknown[]) => getProgressMock(...args),
  },
}));

vi.mock('../services/research.service', async () => {
  const actual = await vi.importActual<typeof import('../services/research.service')>(
    '../services/research.service',
  );
  return {
    ...actual,
    pauseResearch: (...args: unknown[]) => pauseMock(...args),
    editResearchQuestion: (...args: unknown[]) => editQuestionMock(...args),
  };
});

vi.mock('../services/report.service', () => ({
  reportService: {
    getResearchReport: (...args: unknown[]) => getReportMock(...args),
    askFollowup: vi.fn(),
  },
}));

vi.mock('../services/clientAi.service', () => ({
  byokService: {
    getModelsStatus: vi.fn().mockResolvedValue({
      local: {
        provider: 'ollama',
        available: false,
        connected: false,
        baseUrl: 'http://127.0.0.1:11434',
        configuredModel: 'qwen3.5:9b',
        installedModels: [],
      },
      providers: [],
      usageSummary: {
        providerCredits: [],
        enrolledUsers: 1,
        sharedRequestsUsedToday: 0,
        userDailyRequestCap: 20,
        userRequestsRemainingToday: 20,
        systemPoolTotal: 100,
        systemPoolUsedToday: 0,
        systemPoolRemaining: 100,
        byokRequestsToday: 0,
        localRequestsToday: 0,
        totalRequestsToday: 0,
        totalTokensToday: 0,
        totalRequestsAllTime: 0,
        totalTokensAllTime: 0,
        resetsAt: '2026-11-26T00:00:00Z',
        models: [],
      },
    }),
  },
}));

import { ResearchProgressPage } from '../pages/ResearchProgress';
import { ResearchReportPage } from '../pages/ResearchReport';

const activeProgress = (
  overrides: Partial<ResearchProgressResponse> = {},
): ResearchProgressResponse =>
  ({
    id: 'res-1',
    projectId: null,
    question: 'What are the side effects of lithium carbonate?',
    status: 'researching',
    researchDepth: 'standard',
    currentStage: 'searching_sources',
    currentStepIndex: 1,
    totalSteps: 5,
    steps: [
      { id: 'planning', title: 'Planning research', status: 'completed' },
      { id: 'searching_sources', title: 'Searching sources', status: 'active' },
      { id: 'finding_documents', title: 'Finding documents', status: 'pending' },
      { id: 'reviewing_evidence', title: 'Reviewing evidence', status: 'pending' },
      { id: 'building_synthesis', title: 'Building synthesis', status: 'pending' },
    ],
    sourcesDiscovered: 0,
    sourcesReviewed: 0,
    documentsFound: 0,
    startedAt: '2026-11-25T12:00:00Z',
    stageStartedAt: '2026-11-25T12:00:05Z',
    updatedAt: '2026-11-25T12:00:05Z',
    completedAt: null,
    failedAt: null,
    failureReason: null,
    ...overrides,
  }) as ResearchProgressResponse;

describe('Research pause and edit question controls', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it('allows pausing and editing an in-progress run from ResearchProgressPage', async () => {
    getProgressMock.mockResolvedValue(activeProgress());
    pauseMock.mockResolvedValue({ id: 'res-1', status: 'failed' });
    editQuestionMock.mockResolvedValue({
      id: 'res-1',
      question: 'Compare lithium and valproate monitoring requirements',
      status: 'researching',
    });

    render(
      <MemoryRouter initialEntries={['/research/res-1/progress']}>
        <Routes>
          <Route path="/research/:id/progress" element={<ResearchProgressPage />} />
        </Routes>
      </MemoryRouter>,
    );

    const pauseBtn = await screen.findByRole('button', { name: /^pause$/i });
    const editBtn = screen.getByRole('button', { name: /edit question/i });
    expect(pauseBtn).toBeInTheDocument();
    expect(editBtn).toBeInTheDocument();

    fireEvent.click(editBtn);
    const textarea = screen.getByLabelText('Edit question');
    fireEvent.change(textarea, {
      target: { value: 'Compare lithium and valproate monitoring requirements' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save & restart/i }));

    await waitFor(() =>
      expect(editQuestionMock).toHaveBeenCalledWith('res-1', {
        query: 'Compare lithium and valproate monitoring requirements',
      }),
    );

    const pauseBtnAfter = await screen.findByRole('button', { name: /^pause$/i });
    fireEvent.click(pauseBtnAfter);
    await waitFor(() => expect(pauseMock).toHaveBeenCalledWith('res-1'));
    expect(await screen.findByText('Research paused')).toBeInTheDocument();
  });

  it('allows an editor to edit the question on a completed ResearchReportPage', async () => {
    getReportMock.mockResolvedValue({
      report: {
        id: 'rep-1',
        researchId: 'res-1',
        title: 'Lithium Side Effects',
        question: 'What are the side effects of lithium carbonate?',
        summary: 'Summary [S1].',
        dossierRef: 'LOCAL RAG · RES1',
        readingTimeMinutes: 2,
        sourceCount: 1,
        status: 'completed',
        version: 1,
        myRole: 'owner',
        sections: [
          {
            id: 'sec-1',
            heading: 'Grounded answer',
            content: 'Summary [S1].',
            quote: null,
            position: 0,
            citationIds: [1],
            citations: [{ id: 'cit-1', sourceId: 'src-1', number: 1, position: 0 }],
            createdAt: '2026-11-25T12:00:00Z',
            updatedAt: '2026-11-25T12:00:00Z',
          },
        ],
        createdAt: '2026-11-25T12:00:00Z',
        updatedAt: '2026-11-25T12:00:00Z',
      },
      sources: [
        {
          id: 'src-1',
          number: 1,
          title: 'Lithium Pharmacology',
          publisher: 'ACM',
          authors: ['A. Author'],
          year: 2025,
          url: null,
          sourceType: 'peer-reviewed',
          relevantExcerpt: 'Excerpt',
          citationCount: 1,
          doi: null,
          bibtex: null,
          documentId: null,
          chunkId: null,
          page: 1,
          section: null,
          rerankScore: 0.9,
          createdAt: '2026-11-25T12:00:00Z',
          updatedAt: '2026-11-25T12:00:00Z',
        },
      ],
      followups: [],
    });
    editQuestionMock.mockResolvedValue({ id: 'res-1', status: 'researching' });

    render(
      <MemoryRouter initialEntries={['/research/res-1/report']}>
        <Routes>
          <Route path="/research/:id/report" element={<ResearchReportPage />} />
          <Route path="/research/:id/progress" element={<div>Progress Route</div>} />
        </Routes>
      </MemoryRouter>,
    );

    const editBtn = await screen.findByRole('button', { name: /edit question/i });
    fireEvent.click(editBtn);

    const textarea = screen.getByLabelText('Edit question');
    fireEvent.change(textarea, {
      target: { value: 'Updated renal monitoring question' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save & restart/i }));

    await waitFor(() =>
      expect(editQuestionMock).toHaveBeenCalledWith('res-1', {
        query: 'Updated renal monitoring question',
      }),
    );
    expect(await screen.findByText('Progress Route')).toBeInTheDocument();
  });
});
