// @vitest-environment jsdom
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ResearchProgressResponse } from '../types/progress';

const retryMock = vi.fn();

vi.mock('../services/research.service', () => ({
  retryResearch: (...args: unknown[]) => retryMock(...args),
  friendlyResearchError: (_err: unknown, fallback: string) => fallback,
}));

import { RunRecovery } from '../components/research/RunRecovery';

const failed = (overrides: Partial<ResearchProgressResponse> = {}): ResearchProgressResponse =>
  ({
    id: 'run-1',
    question: 'How does temperature affect photosynthesis?',
    status: 'failed',
    projectId: 'project-1',
    failureReason: 'model_unavailable',
    documentsReady: 1,
    documentsPreparing: 0,
    steps: [],
    ...overrides,
  }) as unknown as ResearchProgressResponse;

const renderRecovery = (progress: ResearchProgressResponse, onRestarted = vi.fn()) => {
  render(
    <MemoryRouter>
      <RunRecovery progress={progress} onRestarted={onRestarted} />
    </MemoryRouter>,
  );
  return onRestarted;
};

describe('RunRecovery', () => {
  afterEach(() => {
    cleanup();
    retryMock.mockReset();
  });

  it('explains the failure and retries the same run only once on a double click', async () => {
    let finish: () => void = () => {};
    retryMock.mockImplementation(() => new Promise<void>((resolve) => (finish = resolve)));
    const onRestarted = renderRecovery(failed());

    expect(screen.getByText(/language model didn’t reply/i)).toBeInTheDocument();
    const button = screen.getByRole('button', { name: /try again/i });
    fireEvent.click(button);
    fireEvent.click(button);
    finish();

    await waitFor(() => expect(onRestarted).toHaveBeenCalledTimes(1));
    expect(retryMock).toHaveBeenCalledTimes(1);
    expect(retryMock).toHaveBeenCalledWith('run-1', {});
  });

  it('sends an edited question to the same run', async () => {
    retryMock.mockResolvedValue({});
    const onRestarted = renderRecovery(failed());

    fireEvent.click(screen.getByRole('button', { name: /edit question/i }));
    fireEvent.change(screen.getByLabelText('Question'), { target: { value: 'What limits photosynthesis?' } });
    fireEvent.click(screen.getByRole('button', { name: /ask edited question/i }));

    await waitFor(() => expect(onRestarted).toHaveBeenCalled());
    expect(retryMock).toHaveBeenCalledWith('run-1', { query: 'What limits photosynthesis?' });
  });

  it('points to the documents when they are still being prepared', () => {
    renderRecovery(failed({ failureReason: 'no_ready_documents', documentsReady: 0, documentsPreparing: 2 }));

    expect(screen.getByText(/2 documents are still being prepared/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /documents status/i })).toHaveAttribute(
      'href',
      '/projects/project-1?tab=documents',
    );
  });
});
