import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { StatusBadge } from '../components/common/StatusBadge';
import { TopBar } from '../components/layout/TopBar';
import { ProgressStepper } from '../components/research/ProgressStepper';
import { progressService } from '../services/progress.service';
import { ResearchProgressResponse } from '../types/progress';
import { CenteredLoadingState } from '../components/common/LoadingState';
import { ErrorState } from '../components/common/ErrorState';
import { ApiError } from '../services/api';
import { RunRecovery } from '../components/research/RunRecovery';
import { useResearchHistory } from '../app/ResearchHistoryContext';

const PROGRESS_POLL_DELAYS_MS = [400, 600, 900, 1400, 2000] as const;

export const ResearchProgressPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [progress, setProgress] = useState<ResearchProgressResponse | null>(null);
  const [error, setError] = useState<Error | null>(null);
  // Bumped after "Try again" so polling starts over for the same run.
  const [runKey, setRunKey] = useState(0);
  const history = useResearchHistory();
  const reloadHistory = history?.reload;

  useEffect(() => {
    let mounted = true;
    let timer: number | undefined;
    let pollAttempt = 0;

    const fetchProgress = async () => {
      if (!id) return;
      try {
        const res = await progressService.getResearchProgress(id);
        if (mounted) {
          setProgress(res);
          setError(null);

          if (res.status === 'completed') {
            reloadHistory?.();
            navigate(`/research/${res.id}`, { replace: true });
            return;
          }

          if (res.status === 'failed') {
            reloadHistory?.();
          }

          if (res.status === 'researching' || res.status === 'draft') {
            const delay =
              PROGRESS_POLL_DELAYS_MS[
                Math.min(pollAttempt, PROGRESS_POLL_DELAYS_MS.length - 1)
              ];
            pollAttempt += 1;
            timer = window.setTimeout(fetchProgress, delay);
          }
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err : new Error('Failed to load progress'));
        }
      }
    };

    fetchProgress();

    return () => {
      mounted = false;
      if (timer) {
        window.clearTimeout(timer);
      }
    };
    // runKey restarts polling after "Try again".
  }, [id, navigate, runKey, reloadHistory]);

  if (error) {
    if (error instanceof ApiError && error.status === 404) {
      return (
        <div className="flex min-h-screen items-center justify-center px-4">
          <div className="w-full max-w-md"><ErrorState title="Research not found" message="It may have been deleted, or the link is wrong." onRetry={() => navigate('/research/new')} /></div>
        </div>
      );
    }
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <div className="w-full max-w-md"><ErrorState title="Could not load progress" message={error.message} onRetry={() => window.location.reload()} /></div>
      </div>
    );
  }

  if (!progress) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <CenteredLoadingState label="Loading progress…" />
      </div>
    );
  }

  const isCompleted = progress.status === 'completed';
  const isFailed = progress.status === 'failed';

  const statusLabel = isCompleted
    ? 'Completed'
    : isFailed
      ? 'Failed'
      : progress.status === 'draft'
        ? 'Draft'
        : 'Researching';

  return (
    <div className="min-h-screen flex flex-col">
      <TopBar
        breadcrumbs={
          <div className="flex min-w-0 items-center gap-2">
            <span className="shrink-0 text-ink-soft">Research</span>
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-ink-muted" />
            <span className="truncate font-medium text-ink">{statusLabel}</span>
          </div>
        }
        rightActions={
          isCompleted ? (
            <button
              type="button"
              onClick={() => navigate(`/research/${progress.id}`)}
              className="inline-flex h-8 items-center rounded-md bg-solid px-3 text-[13px] font-medium text-on-solid shadow-xs transition-colors hover:bg-solid-hover"
            >
              View report
            </button>
          ) : null
        }
      />

      <main className="flex-1 px-4 pb-16 pt-14 sm:px-6 lg:px-10">
        <div className="mx-auto max-w-5xl py-8 sm:py-10">
          <div className="mb-8">
            <div className="mb-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-muted">
              <StatusBadge status={progress.status} size="sm" />
              <span>{progress.researchDepth.charAt(0).toUpperCase() + progress.researchDepth.slice(1)} depth</span>
              {progress.startedAt && (
                <>
                  <span aria-hidden="true">·</span>
                  <span>Started {new Date(progress.startedAt).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</span>
                </>
              )}
            </div>

            <h1 className="max-w-3xl font-serif text-2xl leading-snug tracking-[-0.01em] text-ink sm:text-[28px]">
              {progress.question}
            </h1>
            {isFailed && (
              <RunRecovery
                key={progress.updatedAt}
                progress={progress}
                onRestarted={() => {
                  setProgress((current) => (current ? { ...current, status: 'researching', failureReason: null } : current));
                  reloadHistory?.();
                  setRunKey((value) => value + 1);
                }}
              />
            )}
          </div>

          <ProgressStepper progress={progress} />
        </div>
      </main>
    </div>
  );
};
