// @vitest-environment jsdom
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const queryResearchMock = vi.fn();
const getResearchProgressMock = vi.fn();
const getModelsStatusMock = vi.fn();
const saveKeyMock = vi.fn();
const revokeKeyMock = vi.fn();
const setLocalFallbackMock = vi.fn();
const setProviderModelMock = vi.fn();

vi.mock('../services/research.service', () => ({
  queryResearch: (...args: unknown[]) => queryResearchMock(...args),
  getResearchErrorMessage: (_err: unknown, fallback: string) => fallback,
}));

vi.mock('../services/progress.service', () => ({
  progressService: {
    getResearchProgress: (...args: unknown[]) => getResearchProgressMock(...args),
  },
}));

vi.mock('../services/clientAi.service', () => ({
  byokService: {
    getModelsStatus: (...args: unknown[]) => getModelsStatusMock(...args),
    saveKey: (...args: unknown[]) => saveKeyMock(...args),
    revokeKey: (...args: unknown[]) => revokeKeyMock(...args),
    setLocalFallback: (...args: unknown[]) => setLocalFallbackMock(...args),
    setProviderModel: (...args: unknown[]) => setProviderModelMock(...args),
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
    getModelsStatusMock.mockResolvedValue({
      local: {
        provider: 'ollama',
        available: true,
        connected: true,
        baseUrl: 'http://localhost:11434',
        configuredModel: 'qwen3.5:9b',
        activeModel: 'llama3.2:3b',
        installedModels: ['llama3.2:3b'],
      },
      providers: [
        {
          id: 'gemini',
          label: 'Gemini',
          configuredServer: true,
          configuredByok: false,
          configured: true,
          defaultModel: 'gemini-3.8-flash',
          isLocal: false,
          available: true,
        },
        {
          id: 'groq',
          label: 'Groq',
          configuredServer: false,
          configuredByok: false,
          configured: false,
          defaultModel: 'llama-3.3-70b-versatile',
          isLocal: false,
          available: true,
        },
        {
          id: 'openai',
          label: 'OpenAI',
          configuredServer: false,
          configuredByok: false,
          configured: false,
          defaultModel: 'gpt-4o-mini',
          isLocal: false,
          available: true,
        },
        {
          id: 'claude',
          label: 'Claude',
          configuredServer: false,
          configuredByok: false,
          configured: false,
          defaultModel: 'claude-3-5-haiku-latest',
          isLocal: false,
          available: true,
        },
        {
          id: 'grok',
          label: 'Grok',
          configuredServer: false,
          configuredByok: false,
          configured: false,
          defaultModel: 'grok-3-mini-fast',
          isLocal: false,
          available: true,
        },
        {
          id: 'ollama',
          label: 'Local Ollama',
          configuredServer: true,
          configuredByok: false,
          configured: true,
          defaultModel: 'llama3.2:3b',
          isLocal: true,
          available: true,
        },
      ],
      routerOrder: ['gemini', 'openrouter'],
      usage: {
        enrolledUsers: 2,
        sharedRequestsUsedToday: 3,
        userDailyRequestCap: 50,
        userRequestsRemainingToday: 47,
        systemPoolTotal: 100,
        systemPoolUsedToday: 6,
        systemPoolRemaining: 94,
        byokRequestsToday: 1,
        localRequestsToday: 0,
        totalRequestsToday: 4,
        totalTokensToday: 2400,
        totalRequestsAllTime: 9,
        totalTokensAllTime: 6100,
        resetsAt: '2026-11-15T00:00:00Z',
        models: [
          {
            provider: 'gemini',
            modelName: 'gemini-3.8-flash',
            requestsToday: 3,
            tokensToday: 1800,
            totalRequests: 7,
            totalTokens: 4500,
            estimatedCostUsd: 0,
            lastUsedAt: '2026-11-14T12:00:00Z',
          },
        ],
      },
    });
    setLocalFallbackMock.mockImplementation(async (connected: boolean) => ({
      provider: 'ollama',
      available: true,
      connected,
      baseUrl: 'http://localhost:11434',
      configuredModel: 'qwen3.5:9b',
      activeModel: 'llama3.2:3b',
      installedModels: ['llama3.2:3b'],
    }));
    setProviderModelMock.mockImplementation(async (provider: string, modelName: string | null) => ({
      provider,
      selectedModel: modelName,
    }));
    saveKeyMock.mockResolvedValue({
      id: 'key-1',
      provider: 'openai',
      keyHint: 'sk-p...1234',
      isActive: true,
      usageRequests: 0,
      usageTokens: 0,
      createdAt: '2026-11-14T00:00:00Z',
    });
  });

  afterEach(() => {
    cleanup();
  });

  it('defaults to Medium (standard), switches models/Low/High, toggles local fallback, and saves BYOK keys', async () => {
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

    await waitFor(() => {
      expect(getModelsStatusMock).toHaveBeenCalled();
    });

    const textarea = screen.getByLabelText('Question');
    fireEvent.change(textarea, { target: { value: 'What is attention?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Research' }));

    await waitFor(() => {
      expect(queryResearchMock).toHaveBeenCalledWith({
        query: 'What is attention?',
        projectId: 'proj-1',
        researchDepth: 'standard',
        localFallbackEnabled: true,
      });
    });

    fireEvent.click(screen.getByRole('button', { name: 'New question' }));
    fireEvent.click(screen.getByRole('button', { name: 'Models' }));
    expect(screen.getByText('Gemini')).toBeInTheDocument();
    expect(screen.getByText('Groq')).toBeInTheDocument();
    expect(screen.getByText('Claude')).toBeInTheDocument();
    expect(screen.getByText('Grok')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'OpenAI Low' }));

    fireEvent.change(screen.getByLabelText('Question'), {
      target: { value: 'Quick check' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Research' }));

    await waitFor(() => {
      expect(queryResearchMock).toHaveBeenLastCalledWith({
        query: 'Quick check',
        projectId: 'proj-1',
        researchDepth: 'quick',
        preferredProvider: 'openai',
        localFallbackEnabled: true,
      });
    });

    // Disconnect local fallback with one click and switch to Auto High (deep)
    fireEvent.click(screen.getByRole('button', { name: 'New question' }));
    fireEvent.click(screen.getByRole('button', { name: 'Models' }));
    expect(screen.getByText('Available')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Connected' }));
    await waitFor(() => {
      expect(setLocalFallbackMock).toHaveBeenCalledWith(false);
    });
    fireEvent.click(screen.getByRole('button', { name: 'Auto High' }));

    fireEvent.change(screen.getByLabelText('Question'), {
      target: { value: 'Compare attention variants' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Research' }));

    await waitFor(() => {
      expect(queryResearchMock).toHaveBeenLastCalledWith({
        query: 'Compare attention variants',
        projectId: 'proj-1',
        researchDepth: 'deep',
        localFallbackEnabled: false,
      });
    });

    // Apply API key dialog is focused strictly on key setup (model picker lives inside Models)
    fireEvent.click(screen.getByRole('button', { name: 'Apply my API key' }));
    fireEvent.change(screen.getByLabelText('Paste API key'), {
      target: { value: 'sk-proj-testkey1234' },
    });
    expect(screen.getByText('Detected: openai')).toBeInTheDocument();
    expect(screen.queryByLabelText('Custom model name')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Save & integrate key' }));
    await waitFor(() => {
      expect(saveKeyMock).toHaveBeenCalledWith('auto', 'sk-proj-testkey1234');
    });

    // Pick custom model inside Models dropdown + inspect clearly labeled daily usage & cap
    fireEvent.click(screen.getByRole('button', { name: 'New question' }));
    expect(screen.getByText('47 requests left')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Models' }));
    expect(screen.getByText('3 / 50 requests (47 left)')).toBeInTheDocument();
    expect(screen.getByText('94 of 100 requests')).toBeInTheDocument();
    expect(screen.getByText('2 enrolled users')).toBeInTheDocument();
    expect(screen.getByText('4 requests · 2.4k tokens')).toBeInTheDocument();
    expect(screen.getByText('1 BYOK · 0 Local')).toBeInTheDocument();
    expect(screen.getByText('gemini / gemini-3.8-flash')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add OpenAI key' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Select model gpt-4o' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Specific model name'), {
      target: { value: 'gpt-4.1-mini' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Use model' }));
    await waitFor(() => {
      expect(setProviderModelMock).toHaveBeenCalledWith('openai', 'gpt-4.1-mini');
    });
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    fireEvent.change(screen.getByLabelText('Question'), {
      target: { value: 'Test custom OpenAI model' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Research' }));
    await waitFor(() => {
      expect(queryResearchMock).toHaveBeenLastCalledWith({
        query: 'Test custom OpenAI model',
        projectId: 'proj-1',
        researchDepth: 'deep',
        preferredProvider: 'openai',
        modelOverride: 'gpt-4.1-mini',
        localFallbackEnabled: false,
      });
    });

    // Can also pick/override model inside Models dropdown via suggestion chip
    fireEvent.click(screen.getByRole('button', { name: 'New question' }));
    fireEvent.click(screen.getByRole('button', { name: 'Models' }));
    fireEvent.click(screen.getByRole('button', { name: 'Select model gpt-4o' }));
    await waitFor(() => {
      expect(setProviderModelMock).toHaveBeenCalledWith('openai', 'gpt-4o');
    });
    fireEvent.change(screen.getByLabelText('Question'), {
      target: { value: 'Test suggested chip' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Research' }));
    await waitFor(() => {
      expect(queryResearchMock).toHaveBeenLastCalledWith({
        query: 'Test suggested chip',
        projectId: 'proj-1',
        researchDepth: 'deep',
        preferredProvider: 'openai',
        modelOverride: 'gpt-4o',
        localFallbackEnabled: false,
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

  it('keeps Models menu open when clicking a provider row and respects viewport bounds', async () => {
    const innerHeightSpy = vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(700);
    try {
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

      await waitFor(() => {
        expect(getModelsStatusMock).toHaveBeenCalled();
      });

      const modelsBtn = screen.getByRole('button', { name: 'Models' });
      vi.spyOn(modelsBtn, 'getBoundingClientRect').mockReturnValue({
        top: 120,
        bottom: 152,
        left: 24,
        right: 180,
        width: 156,
        height: 32,
        x: 24,
        y: 120,
        toJSON: () => ({}),
      });

      fireEvent.click(modelsBtn);
      const menu = screen.getByRole('menu', { name: 'Models and effort levels' });
      // Only 102px above vs 530px below -> flips downward so top items are never cut off
      expect(menu.className).toContain('top-full');
      expect(Number.parseInt(menu.style.maxHeight, 10)).toBeLessThanOrEqual(530);

      // Clicking a provider name keeps the menu open so its models can be chosen smoothly
      fireEvent.click(screen.getByRole('button', { name: 'Select provider Claude' }));
      expect(screen.getByText('Model for Claude')).toBeInTheDocument();
      expect(screen.getByRole('menu', { name: 'Models and effort levels' })).toBeInTheDocument();

      // Escape or Done closes cleanly
      fireEvent.keyDown(document, { key: 'Escape' });
      expect(screen.queryByRole('menu', { name: 'Models and effort levels' })).not.toBeInTheDocument();
    } finally {
      innerHeightSpy.mockRestore();
    }
  });
});
