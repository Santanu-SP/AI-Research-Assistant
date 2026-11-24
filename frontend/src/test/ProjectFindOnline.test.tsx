// @vitest-environment jsdom
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { makeProject } from './fixtures';

const queryResearchMock = vi.fn();
const startResearchJobMock = vi.fn();

vi.mock('../services/research.service', () => ({
  queryResearch: (...args: unknown[]) => queryResearchMock(...args),
  startResearchJob: (...args: unknown[]) => startResearchJobMock(...args),
  listResearch: vi.fn().mockResolvedValue({ items: [], total: 0, limit: 10, offset: 0 }),
  friendlyResearchError: (_err: unknown, fallback: string) => fallback,
  researchIdFromError: () => null,
  retryResearch: vi.fn(),
}));

vi.mock('../services/clientAi.service', () => ({
  byokService: {
    getModelsStatus: vi.fn().mockResolvedValue({
      local: { provider: 'ollama', available: false, connected: false, installedModels: [] },
      providers: [],
    }),
    saveKey: vi.fn(),
    revokeKey: vi.fn(),
    setLocalFallback: vi.fn(),
    setProviderModel: vi.fn(),
  },
}));

import { ProjectResearchPanel } from '../components/projects/ProjectResearchPanel';

const project = makeProject({ id: 'proj-find', name: 'Sleep Study' });

const renderPanel = (props: Partial<React.ComponentProps<typeof ProjectResearchPanel>> = {}) => {
  const onOpenRun = vi.fn();
  render(
    <MemoryRouter>
      <ProjectResearchPanel project={project} isArchived={false} readyCount={0} onOpenRun={onOpenRun} {...props} />
    </MemoryRouter>,
  );
  return { onOpenRun };
};

const askQuestion = (text: string) => {
  fireEvent.change(screen.getByLabelText('Question'), { target: { value: text } });
};

describe('Also find sources online in a project', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
  });
  afterEach(() => cleanup());

  it('is off by default, so an empty project still asks for a file first', () => {
    renderPanel();
    const toggle = screen.getByRole('switch', { name: 'Also find sources online' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByText(/Upload a file, or turn on/)).toBeInTheDocument();
    askQuestion('How does sleep help memory?');
    expect(screen.getByRole('button', { name: 'Research' })).toBeDisabled();
  });

  it('lets an empty project ask and starts a background run that finds sources', async () => {
    startResearchJobMock.mockResolvedValue({ id: 'run-42' });
    const { onOpenRun } = renderPanel();

    fireEvent.click(screen.getByRole('switch', { name: 'Also find sources online' }));
    expect(screen.getByText(/plus trusted sources found online/)).toBeInTheDocument();
    askQuestion('How does sleep help memory?');
    const button = screen.getByRole('button', { name: 'Research' });
    expect(button).toBeEnabled();
    fireEvent.click(button);

    await waitFor(() => expect(onOpenRun).toHaveBeenCalledWith('run-42'));
    expect(startResearchJobMock).toHaveBeenCalledWith(
      expect.objectContaining({
        query: 'How does sleep help memory?',
        projectId: 'proj-find',
        autoDiscover: true,
        discoveryScope: 'all',
      }),
    );
    expect(queryResearchMock).not.toHaveBeenCalled();
  });

  it('keeps the normal project-only answer when the switch is off', async () => {
    queryResearchMock.mockResolvedValue({
      researchId: 'res-1',
      projectId: 'proj-find',
      answer: 'Sleep helps memory [S1].',
      citations: [],
      hybridCandidateCount: 1,
      evidenceCount: 1,
      insufficientEvidence: false,
    });
    renderPanel({ readyCount: 2 });
    askQuestion('How does sleep help memory?');
    fireEvent.click(screen.getByRole('button', { name: 'Research' }));
    await waitFor(() => expect(queryResearchMock).toHaveBeenCalled());
    expect(queryResearchMock.mock.calls[0][0]).not.toHaveProperty('autoDiscover');
    expect(startResearchJobMock).not.toHaveBeenCalled();
  });

  it('remembers the switch for each project', () => {
    renderPanel();
    fireEvent.click(screen.getByRole('switch', { name: 'Also find sources online' }));
    cleanup();
    renderPanel();
    expect(screen.getByRole('switch', { name: 'Also find sources online' })).toHaveAttribute('aria-checked', 'true');
    cleanup();
    render(
      <MemoryRouter>
        <ProjectResearchPanel project={makeProject({ id: 'other' })} isArchived={false} readyCount={0} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('switch', { name: 'Also find sources online' })).toHaveAttribute('aria-checked', 'false');
  });

  it('is not offered to view-only members', () => {
    window.localStorage.setItem('ara.projectFindOnline.proj-find', '1');
    renderPanel({ readOnly: true });
    expect(screen.queryByRole('switch', { name: 'Also find sources online' })).not.toBeInTheDocument();
    expect(screen.getByText(/cannot start new research or add sources found online/)).toBeInTheDocument();
  });
});
