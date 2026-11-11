import React from 'react';
import { CheckCircle2, Circle, FileSpreadsheet } from 'lucide-react';
import { ResearchProgressResponse } from '../../types/progress';

interface ProgressStepperProps {
  progress: ResearchProgressResponse;
}

export const ProgressStepper: React.FC<ProgressStepperProps> = ({ progress }) => {
  return (
    <div className="w-full bg-panel border border-line rounded-xl p-5 mb-8">
      <div className="flex items-center justify-between pb-3 mb-3 border-b border-line">
        <span className="uppercase tracking-wider text-[11px] font-semibold text-ink-muted">
          Research Progress Stepper
        </span>
        <span className="text-xs text-ink-soft font-medium">
          Step {(progress.currentStepIndex ?? -1) + 1} of {progress.totalSteps} in progress
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-2.5 mb-4">
        {progress.steps.map((step, index) => {
          const isCompleted = step.status === 'completed';
          const isActive = step.status === 'active';

          return (
            <div
              key={step.id}
              className={`p-3 rounded-lg border transition-all duration-150 flex flex-col justify-between min-h-[92px] ${
                isActive
                  ? 'bg-accent-soft/60 border-accent ring-1 ring-accent'
                  : isCompleted
                  ? 'bg-panel border-line'
                  : 'bg-panel/70 border-line opacity-75'
              }`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <span
                  className={`text-[10.5px] font-semibold tracking-wider ${
                    isActive
                      ? 'text-accent'
                      : isCompleted
                      ? 'text-ink-soft'
                      : 'text-ink-muted'
                  }`}
                >
                  STAGE {(index + 1).toString().padStart(2, '0')}{isActive ? ' · ACTIVE' : ''}
                </span>

                {isCompleted ? (
                  <CheckCircle2 className="w-4 h-4 text-accent" />
                ) : isActive ? (
                  <span className="w-2.5 h-2.5 rounded-full bg-solid animate-pulse" />
                ) : (
                  <Circle className="w-3.5 h-3.5 text-ink-muted" />
                )}
              </div>

              <div>
                <h4
                  className={`text-[13px] leading-tight truncate ${
                    isActive
                      ? 'font-semibold text-accent'
                      : isCompleted
                      ? 'font-medium text-ink'
                      : 'font-normal text-ink-soft'
                  }`}
                >
                  {step.title}
                </h4>
                <p className="text-[11px] text-ink-muted leading-tight mt-1 line-clamp-1 capitalize">
                  {step.status}
                </p>
              </div>
            </div>
          );
        })}
      </div>

      <div className="pt-2 flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2 text-ink font-medium">
          <FileSpreadsheet className="w-4 h-4 text-accent" />
          <span>
            {progress.sourcesDiscovered} sources discovered · {progress.sourcesReviewed} sources reviewed
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className="bg-canvas border border-line text-ink-soft text-[11px] px-2.5 py-1 rounded-md">
            Documents Found: {progress.documentsFound}
          </span>
        </div>
      </div>
    </div>
  );
};
