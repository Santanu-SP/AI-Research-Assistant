// @vitest-environment jsdom
import React, { useState } from 'react';
import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Link, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider, useAuth } from '../app/AuthContext';
import { SessionDataCacheProvider } from '../app/SessionDataCacheContext';
import { AppRouter } from '../app/router';
import { ToastProvider } from '../app/ToastContext';
import { ProjectProvider } from '../app/ProjectContext';
import { DocumentsPanel } from '../components/documents/DocumentsPanel';
import { ModelControlBar } from '../components/research/ModelControlBar';
import { useDocumentLibrary } from '../hooks/useDocumentLibrary';
import { ApiError } from '../services/api';
import { authService } from '../services/auth.service';
import { byokService } from '../services/clientAi.service';
import { documentsService } from '../services/documents.service';
import { projectsService } from '../services/projects.service';
import { researchService } from '../services/research.service';
import { makeDocument, makeDocumentList, makeProject } from './fixtures';

const signedInUser = {
  id: 'u-1',
  name: 'Santanu',
  email: 'santanu@example.com',
  isActive: true,
  createdAt: '2026-11-01T00:00:00Z',
  updatedAt: '2026-11-01T00:00:00Z',
};

const researchItem = {
  id: 'res-1',
  title: 'What is market research?',
  question: 'What is market research?',
  domain: null,
  status: 'completed' as const,
  researchDepth: 'standard' as const,
  sourceCount: 1,
  createdAt: '2026-11-15T10:00:00Z',
  updatedAt: '2026-11-15T10:00:00Z',
  archivedAt: null,
};

const modelsStatusFixture = {
  local: {
    provider: 'ollama',
    available: true,
    connected: false,
    baseUrl: 'http://127.0.0.1:11434',
    configuredModel: 'qwen3.5:9b',
    activeModel: 'qwen3.5:9b',
    installedModels: ['qwen3.5:9b'],
  },
  providers: [
    {
      id: 'gemini',
      label: 'Gemini',
      configuredServer: true,
      configuredByok: false,
      configured: true,
      defaultModel: 'gemini-flash-lite-latest',
      isLocal: false,
      available: true,
    },
  ],
  routerOrder: ['gemini'],
};

describe('Workspace navigation and state stability', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes('min-width: 1024px'),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('keeps sidebar mounted without skeletons or redundant refetches when switching routes and returning', async () => {
    vi.spyOn(authService, 'me').mockResolvedValue(signedInUser);
    const listResearchSpy = vi
      .spyOn(researchService, 'listResearch')
      .mockResolvedValue({ items: [researchItem], total: 1, limit: 100, offset: 0 });
    const getDocsSpy = vi
      .spyOn(documentsService, 'getDocuments')
      .mockResolvedValue(makeDocumentList([makeDocument({ name: 'paper-1.pdf', title: null })]));
    const getModelsSpy = vi
      .spyOn(byokService, 'getModelsStatus')
      .mockResolvedValue(modelsStatusFixture);
    vi.spyOn(projectsService, 'listProjects').mockResolvedValue({
      items: [makeProject()],
      total: 1,
      limit: 100,
      offset: 0,
    });

    render(
      <MemoryRouter initialEntries={['/research/new']}>
        <AuthProvider>
          <ProjectProvider>
            <ToastProvider>
              <AppRouter />
            </ToastProvider>
          </ProjectProvider>
        </AuthProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText('What is market research?')).toBeInTheDocument();
    // A new research starts with no files; the library is offered instead.
    expect(await screen.findByRole('button', { name: /Add from library/i })).toBeInTheDocument();
    expect(screen.queryByText('paper-1.pdf')).not.toBeInTheDocument();
    expect(listResearchSpy).toHaveBeenCalledTimes(1);
    expect(getDocsSpy).toHaveBeenCalledTimes(1);
    expect(getModelsSpy).toHaveBeenCalledTimes(1);

    // Navigate away to Projects — sidebar and research history must remain mounted without refetching.
    fireEvent.click(screen.getAllByRole('link', { name: 'Projects' })[0]);
    expect(await screen.findByText('Project Alpha')).toBeInTheDocument();
    expect(screen.getByText('What is market research?')).toBeInTheDocument();
    expect(screen.queryByLabelText('Loading research history')).not.toBeInTheDocument();
    expect(listResearchSpy).toHaveBeenCalledTimes(1);

    // Navigate back to New research — cached docs and models render immediately with no "Loading…" skeleton.
    fireEvent.click(screen.getAllByRole('link', { name: /New research/i })[0]);
    expect(screen.queryByText('Loading…')).not.toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /Add from library/i })).toBeInTheDocument();
    expect(listResearchSpy).toHaveBeenCalledTimes(1);
    expect(getDocsSpy).toHaveBeenCalledTimes(1);
    expect(getModelsSpy).toHaveBeenCalledTimes(1);
  });

  it('keeps existing documents visible without flashing skeletons during reload()', async () => {
    const initialDoc = makeDocument({ id: 'doc-1', name: 'existing.pdf', title: null });
    const addedDoc = makeDocument({ id: 'doc-2', name: 'added.pdf', title: null });

    let resolveReload!: (val: ReturnType<typeof makeDocumentList>) => void;
    const getDocsSpy = vi
      .spyOn(documentsService, 'getDocuments')
      .mockResolvedValueOnce(makeDocumentList([initialDoc]))
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveReload = resolve;
          }),
      );

    const Harness: React.FC = () => {
      const library = useDocumentLibrary({ all: true });
      return (
        <div>
          <button type="button" onClick={library.reload}>
            Reload docs
          </button>
          <DocumentsPanel library={library} />
        </div>
      );
    };

    render(
      <MemoryRouter>
        <SessionDataCacheProvider>
          <ToastProvider>
            <Harness />
          </ToastProvider>
        </SessionDataCacheProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText('existing.pdf')).toBeInTheDocument();
    expect(getDocsSpy).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: 'Reload docs' }));

    // Existing documents remain rendered (no "Loading…" skeleton takeover) while reload is in flight.
    expect(screen.queryByText('Loading…')).not.toBeInTheDocument();
    expect(screen.getByText('existing.pdf')).toBeInTheDocument();

    await act(async () => {
      resolveReload(makeDocumentList([addedDoc, initialDoc]));
    });

    expect(await screen.findByText('added.pdf')).toBeInTheDocument();
    expect(screen.getByText('existing.pdf')).toBeInTheDocument();
  });

  it('does not re-fetch models-status when localFallbackEnabled initializes or parent rerenders', async () => {
    const getModelsSpy = vi
      .spyOn(byokService, 'getModelsStatus')
      .mockResolvedValue(modelsStatusFixture);

    const Harness: React.FC = () => {
      const [depth, setDepth] = useState<'quick' | 'standard' | 'deep'>('standard');
      const [provider, setProvider] = useState<string | null>(null);
      const [fallback, setFallback] = useState<boolean | undefined>(undefined);
      const [tick, setTick] = useState(0);
      return (
        <div>
          <button type="button" onClick={() => setTick((t) => t + 1)}>
            Rerender {tick}
          </button>
          <ModelControlBar
            depth={depth}
            onDepthChange={setDepth}
            preferredProvider={provider}
            onPreferredProviderChange={setProvider}
            localFallbackEnabled={fallback}
            // Recreated inline callback every render
            onLocalFallbackChange={(val) => setFallback(val)}
          />
        </div>
      );
    };

    render(<Harness />);
    await waitFor(() => expect(getModelsSpy).toHaveBeenCalledTimes(1));

    // Trigger several parent rerenders after localFallbackEnabled flips from undefined -> false.
    fireEvent.click(screen.getByRole('button', { name: /Rerender/ }));
    fireEvent.click(screen.getByRole('button', { name: /Rerender/ }));

    await act(async () => {
      await Promise.resolve();
    });
    expect(getModelsSpy).toHaveBeenCalledTimes(1);
  });

  it('shares cached document library across route unmount and remount inside SessionDataCacheProvider', async () => {
    const getDocsSpy = vi
      .spyOn(documentsService, 'getDocuments')
      .mockResolvedValue(makeDocumentList([makeDocument({ id: 'd-cache', name: 'cached-paper.pdf' })]));

    const PageA: React.FC = () => {
      const lib = useDocumentLibrary({ all: true });
      return (
        <div>
          <Link to="/other">Go other</Link>
          <span>{lib.isLoading ? 'loading-a' : lib.documents.map((d) => d.name).join(',')}</span>
        </div>
      );
    };
    const PageB: React.FC = () => <Link to="/">Back home</Link>;

    render(
      <MemoryRouter initialEntries={['/']}>
        <SessionDataCacheProvider>
          <Routes>
            <Route path="/" element={<PageA />} />
            <Route path="/other" element={<PageB />} />
          </Routes>
        </SessionDataCacheProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText('cached-paper.pdf')).toBeInTheDocument();
    expect(getDocsSpy).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('link', { name: 'Go other' }));
    expect(screen.getByRole('link', { name: 'Back home' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('link', { name: 'Back home' }));
    // Renders immediately from cache without showing loading-a or making another fetch.
    expect(screen.getByText('cached-paper.pdf')).toBeInTheDocument();
    expect(screen.queryByText('loading-a')).not.toBeInTheDocument();
    expect(getDocsSpy).toHaveBeenCalledTimes(1);
  });

  it('preserves signed-in user in AuthProvider on transient non-401 refresh errors', async () => {
    const meSpy = vi
      .spyOn(authService, 'me')
      .mockResolvedValueOnce(signedInUser)
      .mockRejectedValueOnce(new ApiError('Temporary upstream error', 503))
      .mockRejectedValueOnce(new ApiError('Unauthorized', 401));

    const wrapper: React.FC<React.PropsWithChildren> = ({ children }) => (
      <AuthProvider>{children}</AuthProvider>
    );
    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => expect(result.current.user?.id).toBe('u-1'));

    await act(async () => {
      await result.current.refreshUser();
    });
    expect(result.current.user?.id).toBe('u-1');

    await act(async () => {
      await result.current.refreshUser();
    });
    expect(result.current.user).toBeNull();
    expect(meSpy).toHaveBeenCalledTimes(3);
  });
});
