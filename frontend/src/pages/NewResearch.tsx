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
        breadcrumbs={
          <div className="flex items-center gap-2">
            <span className="text-ink-soft">Research</span>
            <span className="text-ink-muted">/</span>
            <span className="text-ink font-medium">New Research</span>
          </div>
        }
      />

      <main className="flex-1 pt-14 pb-16 px-4 sm:px-6">
        <div className="max-w-3xl mx-auto py-10">
          <div className="mb-8 text-center sm:text-left">
            <h1 className="font-serif text-3xl sm:text-4xl text-ink tracking-tight font-normal mb-2.5">
              What would you like to investigate?
            </h1>
            <p className="text-sm sm:text-[15px] text-ink-soft max-w-2xl leading-relaxed">
              Search your indexed papers and generate a locally grounded answer with validated citations.
            </p>
          </div>

          <div className="mb-10">
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

          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="uppercase tracking-wider text-[11px] font-semibold text-ink-muted">
                Recent Research
              </span>
              <Link
                to="/research"
                className="text-xs font-medium text-accent hover:underline"
              >
                View all ({recentTotal})
              </Link>
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
                description="Create your first research record using the question above."
              />
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {recentResearch.map((item) => {
                const targetPath =
                  item.status === 'researching'
                    ? `/research/${item.id}/progress`
                    : item.status === 'completed'
                      ? `/research/${item.id}`
                      : `/research/${item.id}/progress`;

                return (
                  <Link
                    key={item.id}
                    to={targetPath}
                    className="p-4 bg-panel border border-line hover:border-line-strong hover:shadow-xs rounded-lg transition-all duration-150 flex flex-col justify-between group"
                  >
                    <div>
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <span className="text-[11px] font-medium text-ink-soft truncate">
                          {item.domain || 'General research'}
                        </span>
                        <StatusBadge status={item.status} size="sm" />
                      </div>

                      <h4 className="text-[13.5px] font-medium text-ink group-hover:text-accent transition-colors line-clamp-2 leading-snug mb-3">
                        {item.title}
                      </h4>
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-ink-muted pt-2 border-t border-line">
                      <span>{item.sourceCount} sources</span>
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        <span>{formatUpdatedAt(item.updatedAt)}</span>
                      </span>
                    </div>
                  </Link>
                );
              })}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};
