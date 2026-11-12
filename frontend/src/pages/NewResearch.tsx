import React, { useEffect, useState } from 'react';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { TopBar } from '../components/layout/TopBar';
import { ResearchComposer } from '../components/research/ResearchComposer';
import { ErrorState } from '../components/common/ErrorState';
import {
  getResearchErrorMessage,
  researchService,
} from '../services/research.service';
import { FileUp, FolderOpen, History } from 'lucide-react';
import { shortcutLabel } from '../lib/shortcuts';
import { ResearchDepth } from '../types/research';

const TIPS: { icon: React.ElementType; title: string; body: React.ReactNode; to: string | null }[] = [
  {
    icon: FileUp,
    title: 'Add papers first',
    body: 'Answers only use documents that are uploaded and indexed.',
    to: '/documents',
  },
  {
    icon: FolderOpen,
    title: 'Keep a topic scoped',
    body: 'Ask inside a project to search just that project’s papers.',
    to: '/projects',
  },
  {
    icon: History,
    title: 'Find past research',
    body: (
      <>
        Everything you ask is listed in the sidebar, with search.
        <span className="hidden sm:inline"> Press {shortcutLabel('K')} to jump to it.</span>
      </>
    ),
    to: null,
  },
];

/** Opens the sidebar search the same way the keyboard shortcut does. */
const focusResearchSearch = () =>
  window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, metaKey: true }));

export const NewResearch: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  useEffect(() => {
    setCreateError(null);
  }, [location.key]);

  const handleStartResearch = async (payload: {
    question: string;
    depth: ResearchDepth;
  }) => {
    setIsSubmitting(true);
    setCreateError(null);
    try {
      const research = await researchService.startResearchJob({
        query: payload.question,
        researchDepth: payload.depth,
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
        <div className="mx-auto max-w-3xl py-10 sm:pb-14 sm:pt-[9vh]">
          <div className="mb-6">
            <h1 className="font-serif text-[28px] leading-tight tracking-[-0.01em] text-ink sm:text-[34px]">
              What do you want to find out?
            </h1>
            <p className="mt-2 max-w-xl text-sm leading-relaxed text-ink-soft">
              Questions are answered only from the papers you have uploaded and indexed. Each
              claim in the answer links to the passage it came from.
            </p>
          </div>

          <div className="mb-12">
            <ResearchComposer
              key={location.key}
              onStartResearch={handleStartResearch}
              isLoading={isSubmitting}
            />
            {createError ? (
              <div className="mt-3">
                <ErrorState
                  title="Research could not be started"
                  message={createError}
                />
              </div>
            ) : null}
          </div>

          <ul className="grid gap-3 sm:grid-cols-3">
            {TIPS.map(({ icon: Icon, title, body, to }) => {
              const className =
                'group flex h-full w-full flex-col rounded-lg border border-line bg-panel/80 p-4 text-left shadow-xs transition-[border-color,box-shadow] duration-200 hover:border-line-strong hover:shadow-sm';
              const content = (
                <>
                  <Icon className="h-4 w-4 text-accent" strokeWidth={1.75} />
                  <span className="mt-3 text-[13px] font-medium text-ink">{title}</span>
                  <span className="mt-1 text-xs leading-relaxed text-ink-muted">{body}</span>
                </>
              );
              return (
                <li key={title}>
                  {to ? (
                    <Link to={to} className={className}>
                      {content}
                    </Link>
                  ) : (
                    <button type="button" onClick={focusResearchSearch} className={className}>
                      {content}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      </main>
    </div>
  );
};
