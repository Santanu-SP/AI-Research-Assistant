import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { TopBar } from '../components/layout/TopBar';
import { ResearchComposer } from '../components/research/ResearchComposer';
import { StatusBadge } from '../components/common/StatusBadge';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';
import { LoadingState } from '../components/common/LoadingState';
import {
  getResearchErrorMessage,
  researchService,
} from '../services/research.service';
import { Clock } from 'lucide-react';
import { ResearchDepth, ResearchResponse } from '../types/research';

const formatUpdatedAt = (value: string): string =>
  new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: new Date(value).getFullYear() === new Date().getFullYear() ? undefined : 'numeric',
  }).format(new Date(value));

export const NewResearch: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [recentResearch, setRecentResearch] = useState<ResearchResponse[]>([]);
  const [recentTotal, setRecentTotal] = useState(0);
  const [isRecentLoading, setIsRecentLoading] = useState(true);
  const [recentError, setRecentError] = useState<string | null>(null);

  useEffect(() => {
    setCreateError(null);
  }, [location.key]);

  const loadRecentResearch = useCallback(async () => {
    setIsRecentLoading(true);
    setRecentError(null);
    try {
      const response = await researchService.listResearch({ limit: 4, offset: 0 });
      setRecentResearch(response.items);
      setRecentTotal(response.total);
    } catch (error) {
      setRecentError(
        getResearchErrorMessage(error, 'We could not load your recent research.')
      );
    } finally {
      setIsRecentLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRecentResearch();
  }, [loadRecentResearch]);

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
    <div className="min-h-screen bg-canvas flex flex-col">
      <TopBar
        breadcrumbs={<span className="font-medium text-ink">New research</span>}
      />

      <main className="flex-1 px-4 pb-16 pt-14 sm:px-6 lg:px-10">
        <div className="mx-auto max-w-3xl py-10 sm:py-14">
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

          <section>
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-medium text-ink">Recent research</h2>
              {recentTotal > 0 && (
                <Link
                  to="/research"
                  className="text-[13px] font-medium text-accent hover:underline"
                >
                  View all ({recentTotal})
                </Link>
              )}
            </div>

            {isRecentLoading ? (
              <LoadingState rows={2} />
            ) : recentError ? (
              <ErrorState
                title="Recent research unavailable"
                message={recentError}
                onRetry={() => void loadRecentResearch()}
              />
            ) : recentResearch.length === 0 ? (
              <EmptyState
                title="No research yet"
                description="Ask your first question above. Finished answers will be listed here."
              />
            ) : (
              <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-panel shadow-xs">
                {recentResearch.map((item) => {
                  const targetPath =
                    item.status === 'completed'
                      ? `/research/${item.id}`
                      : `/research/${item.id}/progress`;

                  return (
                    <li key={item.id}>
                      <Link
                        to={targetPath}
                        className="group flex items-center gap-4 px-4 py-3 transition-colors hover:bg-subtle/60"
                      >
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-ink">{item.title}</p>
                          <p className="mt-0.5 flex items-center gap-1.5 text-xs text-ink-muted">
                            <span className="truncate">{item.domain || 'General'}</span>
                            <span aria-hidden="true">·</span>
                            <span className="shrink-0">{item.sourceCount} sources</span>
                            <span aria-hidden="true">·</span>
                            <span className="flex shrink-0 items-center gap-1">
                              <Clock className="h-3 w-3" />
                              {formatUpdatedAt(item.updatedAt)}
                            </span>
                          </p>
                        </div>
                        <StatusBadge status={item.status} size="sm" />
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      </main>
    </div>
  );
};
