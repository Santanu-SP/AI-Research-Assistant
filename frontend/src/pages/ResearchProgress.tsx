import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { TopBar } from '../components/layout/TopBar';
import { ProgressStepper } from '../components/research/ProgressStepper';
import { progressService } from '../services/progress.service';
import { ResearchProgressResponse } from '../types/progress';
import { Ban } from 'lucide-react';
import { CenteredLoadingState } from '../components/common/LoadingState';
import { ErrorState } from '../components/common/ErrorState';
import { ApiError } from '../services/api';

export const ResearchProgressPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [progress, setProgress] = useState<ResearchProgressResponse | null>(null);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let mounted = true;
    let timer: number | undefined;

    const fetchProgress = async () => {
      if (!id) return;
      try {
        const res = await progressService.getResearchProgress(id);
        if (mounted) {
          setProgress(res);
          setError(null);
          
          if (res.status === 'researching') {
            timer = window.setTimeout(fetchProgress, 3000);
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
  }, [id]);

  if (error) {
    if (error instanceof ApiError && error.status === 404) {
      return (
        <div className="min-h-screen bg-[#fafaf8] flex items-center justify-center">
          <ErrorState title="Not Found" message="This research investigation does not exist." onRetry={() => navigate('/research')} />
        </div>
      );
    }
    return (
      <div className="min-h-screen bg-[#fafaf8] flex items-center justify-center">
        <ErrorState title="Connection Error" message={error.message} onRetry={() => window.location.reload()} />
      </div>
    );
  }

  if (!progress) {
    return (
      <div className="min-h-screen bg-[#fafaf8] flex items-center justify-center">
        <CenteredLoadingState label="Loading investigation state…" />
      </div>
    );
  }

  const isCompleted = progress.status === 'completed';
  const isFailed = progress.status === 'failed';

  return (
    <div className="min-h-screen bg-[#fafaf8] flex flex-col">
      {/* TopBar */}
      <TopBar
        breadcrumbs={
          <div className="flex items-center gap-2">
            <Link to="/research" className="text-[#6b706c] hover:text-[#181a18]">
              Research
            </Link>
            <span className="text-[#929792]">/</span>
            <div className="flex items-center gap-1.5 text-[#163328] font-medium">
              {progress.status === 'researching' && (
                <span className="w-2 h-2 rounded-full bg-emerald-600 animate-pulse" />
              )}
              <span>{isCompleted ? 'Completed Investigation' : isFailed ? 'Failed Investigation' : 'Active Investigation'}</span>
            </div>
          </div>
        }
        rightActions={
          <div className="flex items-center gap-3">
            {progress.status === 'researching' && (
              <button
                type="button"
                onClick={() => navigate('/research')}
                className="text-xs text-[#6b706c] hover:text-[#b91c1c] border border-[#e5e7e4] hover:border-[#fecaca] hover:bg-[#fee2e2]/30 px-2.5 py-1 rounded-md transition-colors flex items-center gap-1 cursor-pointer"
              >
                <Ban className="w-3 h-3" />
                <span>Cancel research</span>
              </button>
            )}
            {isCompleted && (
              <button
                type="button"
                onClick={() => navigate(`/research/${progress.id}/report`)}
                className="bg-[#163328] hover:bg-[#1a3d30] text-white px-3 py-1.5 rounded-md text-xs font-medium transition-colors"
              >
                View Report
              </button>
            )}
          </div>
        }
      />

      {/* Main Container */}
      <main className="flex-1 pt-14 pb-16 px-4 sm:px-6">
        <div className="max-w-5xl mx-auto py-8">
          {/* Header Metadata */}
          <div className="mb-6">
            <div className="flex flex-wrap items-center gap-2 text-xs text-[#6b706c] mb-2 font-mono">
              <span className="text-[#163328] font-semibold">{progress.id}</span>
              <span className="text-[#929792]">·</span>
              <span className="capitalize">Depth: {progress.researchDepth}</span>
              {progress.startedAt && (
                <>
                  <span className="text-[#929792]">·</span>
                  <span>Started {new Date(progress.startedAt).toLocaleString()}</span>
                </>
              )}
            </div>

            <h1 className="font-serif text-2xl sm:text-3xl text-[#181a18] font-normal leading-snug">
              {progress.question}
            </h1>
          </div>

          {/* Stepper Component */}
          <ProgressStepper progress={progress} />
          
        </div>
      </main>
    </div>
  );
};
