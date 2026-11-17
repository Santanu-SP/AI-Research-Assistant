// @vitest-environment jsdom
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ResearchProgressResponse } from '../types/progress';
import { describeModelFailure, prettyModelName } from '../lib/modelErrors';

const retryMock = vi.fn();

vi.mock('../services/research.service', () => ({
  retryResearch: (...args: unknown[]) => retryMock(...args),
  friendlyResearchError: (_err: unknown, fallback: string) => fallback,
}));

vi.mock('../services/clientAi.service', () => ({
  byokService: {
    getModelsStatus: () =>
      Promise.resolve({
        local: { provider: 'ollama', available: false, connected: false, baseUrl: '', configuredModel: 'local', installedModels: [] },
        providers: [
          { id: 'gemini', label: 'Gemini', configuredServer: true, configuredByok: false, configured: true, defaultModel: 'gemini-2.5-flash', isLocal: false, available: true },
        ],
        routerOrder: ['gemini'],
      }),
    setProviderModel: () => Promise.resolve({}),
  },
}));

import { RunRecovery } from '../components/research/RunRecovery';

const failed = (overrides: Partial<ResearchProgressResponse> = {}): ResearchProgressResponse =>
  ({
    id: 'run-1',
    question: 'How does temperature affect photosynthesis?',
    status: 'failed',
    researchDepth: 'standard',
    projectId: null,
    failureReason: 'model_unavailable',
    failureProvider: 'gemini',
    failureModel: 'gemini-2.5-pro',
    failureType: 'quota',
    documentsReady: 1,
    documentsPreparing: 0,
    steps: [],
    ...overrides,
  }) as unknown as ResearchProgressResponse;

afterEach(() => {
  cleanup();
  retryMock.mockReset();
});

describe('model failure messages', () => {
  it('turns provider and model ids into readable names', () => {
    expect(prettyModelName('gemini', 'gemini-2.5-pro')).toBe('Gemini 2.5 Pro');
    expect(prettyModelName('openai', 'gpt-4o-mini')).toBe('OpenAI GPT 4o Mini');
    expect(prettyModelName('gemini', null)).toBe('Gemini');
  });

  it('explains each failure type in plain words', () => {
    expect(describeModelFailure(failed())?.title).toBe('Gemini 2.5 Pro hit its free limit');
    expect(describeModelFailure(failed({ failureType: 'auth' }))?.title).toBe('Your API key was rejected by Gemini 2.5 Pro');
    expect(describeModelFailure(failed({ failureType: 'timeout' }))?.title).toBe('Gemini 2.5 Pro timed out');
    expect(describeModelFailure(failed({ failureType: null }))).toBeNull();
  });
});

describe('RunRecovery with a model failure', () => {
  it('shows the reason and lets the user switch model before trying again', async () => {
    retryMock.mockResolvedValue({});
    const onRestarted = vi.fn();
    render(
      <MemoryRouter>
        <RunRecovery progress={failed()} onRestarted={onRestarted} />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: 'Gemini 2.5 Pro hit its free limit' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /switch model/i }));

    // The model list opens straight away.
    const picker = await screen.findByLabelText('Pick a model for the next try');
    await waitFor(() => expect(within(picker).getByRole('button', { name: 'Models' })).toHaveAttribute('aria-expanded', 'true'));

    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    await waitFor(() => expect(onRestarted).toHaveBeenCalled());
    expect(retryMock).toHaveBeenCalledWith('run-1', expect.objectContaining({ researchDepth: 'standard', preferredProvider: null }));
  });

  it('does not show a raw error text', () => {
    render(
      <MemoryRouter>
        <RunRecovery progress={failed({ failureType: 'auth' })} onRestarted={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Update it in Settings/)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/AIza|sk-/);
  });
});
