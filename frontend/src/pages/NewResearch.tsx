import React, { useEffect, useState } from 'react';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { TopBar } from '../components/layout/TopBar';
import { ResearchComposer } from '../components/research/ResearchComposer';
import { ErrorState } from '../components/common/ErrorState';
import {
  getResearchErrorMessage,
  researchService,
} from '../services/research.service';
import { FolderOpen, History } from 'lucide-react';
import { shortcutLabel } from '../lib/shortcuts';
import { ResearchDepth } from '../types/research';
import { DocumentsPanel } from '../components/documents/DocumentsPanel';
import { useDocumentLibrary } from '../hooks/useDocumentLibrary';

const ALL_DOCUMENTS = { all: true } as const;

const TIP_CLASS =
  'group flex h-full w-full flex-col rounded-lg border border-line bg-panel/80 p-4 text-left shadow-xs transition-[border-color,box-shadow] duration-200 hover:border-line-strong hover:shadow-sm';

/** Opens the sidebar search the same way the keyboard shortcut does. */
const focusResearchSearch = () =>
  window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, metaKey: true }));

export const NewResearch: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const library = useDocumentLibrary(ALL_DOCUMENTS);

  useEffect(() => {
    setCreateError(null);
  }, [location.key]);

  const handleStartResearch = async (payload: {
    question: string;
    depth: ResearchDepth;
    preferredProvider?: string | null;
    modelOverride?: string | null;
    localFallbackEnabled?: boolean;
  }) => {
    setIsSubmitting(true);
    setCreateError(null);
    const requestExtras = {
      ...(payload.preferredProvider ? { preferredProvider: payload.preferredProvider } : {}),
      ...(payload.modelOverride ? { modelOverride: payload.modelOverride } : {}),
      ...(payload.localFallbackEnabled !== undefined
        ? { localFallbackEnabled: payload.localFallbackEnabled }
        : {}),
    };
    try {
      if (payload.depth === 'quick') {
        const response = await researchService.queryResearch({
          query: payload.question,
          researchDepth: payload.depth,
          ...requestExtras,
        });
        navigate(`/research/${response.researchId}`);
        return;
      }
      const research = await researchService.startResearchJob({
        query: payload.question,
        researchDepth: payload.depth,
        ...requestExtras,
      });
      navigate(`/research/${research.id}/progress`);
    } catch (error) {
      setCreateError(
        getResearchErrorMessage(error, 'Research could not be started. Please try again.')
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col">
      <TopBar
        breadcrumbs={<span className="font-medium text-ink">New research</span>}
      />

      <main className="flex-1 px-4 pb-16 pt-14 sm:px-6 lg:px-10">
        <div className="mx-auto grid max-w-5xl items-start gap-8 py-10 sm:pb-14 sm:pt-[9vh] lg:grid-cols-[minmax(0,1fr)_300px]">
          <div className="min-w-0">
            <div className="mb-6">
              <h1 className="font-serif text-[28px] leading-tight tracking-[-0.01em] text-ink sm:text-[34px]">
                What do you want to find out?
              </h1>
              <p className="mt-2 max-w-xl text-sm leading-relaxed text-ink-soft">
                Answers come only from your documents, and each claim links to the passage it came
                from.
              </p>
            </div>

            <ResearchComposer
              key={location.key}
              onStartResearch={handleStartResearch}
              isLoading={isSubmitting}
            />
            {createError ? (
              <div className="mt-3">
                <ErrorState title="Research could not be started" message={createError} />
              </div>
            ) : null}

            <ul className="mt-8 grid gap-3 sm:grid-cols-2">
              <li>
                <Link to="/projects" className={TIP_CLASS}>
                  <FolderOpen className="h-4 w-4 text-accent" strokeWidth={1.75} />
                  <span className="mt-3 text-[13px] font-medium text-ink">Keep a topic scoped</span>
                  <span className="mt-1 text-xs leading-relaxed text-ink-muted">
                    Ask inside a project to use just that project’s papers.
                  </span>
                </Link>
              </li>
              <li>
                <button type="button" onClick={focusResearchSearch} className={TIP_CLASS}>
                  <History className="h-4 w-4 text-accent" strokeWidth={1.75} />
                  <span className="mt-3 text-[13px] font-medium text-ink">Find past research</span>
                  <span className="mt-1 text-xs leading-relaxed text-ink-muted">
                    Everything you ask is listed in the sidebar, with search.
                    <span className="hidden sm:inline"> Press {shortcutLabel('K')} to jump to it.</span>
                  </span>
                </button>
              </li>
            </ul>
          </div>

          <DocumentsPanel
            library={library}
            title="Your documents"
            className="lg:sticky lg:top-20 lg:mt-[7.5rem] lg:max-h-[calc(100vh-7rem)]"
          />
        </div>
      </main>
    </div>
  );
};
