import React from 'react';
import { Check } from 'lucide-react';
import { ResearchProgressResponse, ResearchProgressStage } from '../../types/progress';

interface ProgressStepperProps {
  progress: ResearchProgressResponse;
}

const STAGE_DETAIL: Record<ResearchProgressStage, string> = {
  PLANNING: 'Reading the question and deciding what to look for.',
  SEARCHING: 'Running semantic and keyword search over your indexed documents.',
  EXTRACTING: 'Reranking passages and keeping the ones that answer the question.',
  SYNTHESIZING: 'Writing the answer from the selected passages.',
  FINALIZING: 'Checking that every sentence is backed by a citation.',
};

export const ProgressStepper: React.FC<ProgressStepperProps> = ({ progress }) => {
  const done = progress.steps.filter((step) => step.status === 'completed').length;
  const percent = progress.totalSteps > 0 ? Math.round((done / progress.totalSteps) * 100) : 0;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_260px]">
      <section className="rounded-lg border border-line bg-panel p-5 shadow-xs sm:p-6" aria-label="Research steps">
        <div className="mb-5 flex items-center justify-between gap-4">
          <h2 className="text-sm font-medium text-ink">Progress</h2>
          <span className="text-xs tabular-nums text-ink-muted">
            Step {Math.min((progress.currentStepIndex ?? -1) + 1, progress.totalSteps) || done} of {progress.totalSteps}
          </span>
        </div>

        <div
          className="mb-6 h-1 overflow-hidden rounded-full bg-subtle"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          aria-label="Research progress"
        >
          <div className="h-full rounded-full bg-solid transition-[width] duration-500" style={{ width: `${percent}%` }} />
        </div>

        <ol className="relative">
          {progress.steps.map((step, index) => {
            const isCompleted = step.status === 'completed';
            const isActive = step.status === 'active';
            const isLast = index === progress.steps.length - 1;

            return (
              <li key={step.id} className="relative flex gap-4 pb-6 last:pb-0" aria-current={isActive ? 'step' : undefined}>
                {!isLast && (
                  <span
                    aria-hidden="true"
                    className={`absolute left-[11px] top-7 h-[calc(100%-28px)] w-px ${isCompleted ? 'bg-accent' : 'bg-line'}`}
                  />
                )}
                <span
                  className={`relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[11px] font-medium tabular-nums ${
                    isCompleted
                      ? 'border-solid bg-solid text-on-solid'
                      : isActive
                        ? 'border-accent bg-panel text-accent ring-4 ring-accent-soft'
                        : 'border-line-strong bg-panel text-ink-muted'
                  }`}
                >
                  {isCompleted ? <Check className="h-3.5 w-3.5" strokeWidth={2.5} /> : index + 1}
                </span>
                <div className="min-w-0 pt-0.5">
                  <p
                    className={`text-sm leading-tight ${
                      isActive ? 'font-medium text-ink' : isCompleted ? 'text-ink' : 'text-ink-muted'
                    }`}
                  >
                    {step.title}
                    {isActive && (
                      <span className="ml-2 inline-flex items-center gap-1.5 text-xs font-normal text-accent">
                        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
                        In progress
                      </span>
                    )}
                  </p>
                  <p className={`mt-1 text-[13px] leading-snug ${isActive ? 'text-ink-soft' : 'text-ink-muted'}`}>
                    {STAGE_DETAIL[step.id] ?? ''}
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      </section>

      <aside className="h-fit rounded-lg border border-line bg-panel shadow-xs">
        <h2 className="border-b border-line px-5 py-3 text-sm font-medium text-ink">Evidence so far</h2>
        <dl className="divide-y divide-line">
          <Stat label="Sources discovered" value={progress.sourcesDiscovered} />
          <Stat label="Sources reviewed" value={progress.sourcesReviewed} />
          <Stat label="Documents matched" value={progress.documentsFound} />
        </dl>
      </aside>
    </div>
  );
};

const Stat: React.FC<{ label: string; value: number }> = ({ label, value }) => (
  <div className="flex items-baseline justify-between px-5 py-3">
    <dt className="text-[13px] text-ink-soft">{label}</dt>
    <dd className="text-lg font-semibold tabular-nums text-ink">{value}</dd>
  </div>
);
