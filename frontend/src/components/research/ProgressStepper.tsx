import React from 'react';
import { CheckCircle2, Circle, FileSpreadsheet } from 'lucide-react';
import { ResearchProgress } from '../../types/research';

interface ProgressStepperProps {
  progress: ResearchProgress;
}

export const ProgressStepper: React.FC<ProgressStepperProps> = ({ progress }) => {
  return (
    <div className="w-full bg-white border border-[#e5e7e4] rounded-xl p-5 mb-8">
      {/* Stepper Header */}
      <div className="flex items-center justify-between pb-3 mb-3 border-b border-[#e5e7e4]">
        <span className="uppercase tracking-wider text-[11px] font-semibold text-[#929792]">
          Research Progress Stepper
        </span>
        <span className="text-xs text-[#6b706c] font-medium">
          Step {progress.currentStepIndex + 1} of {progress.totalSteps} in progress
        </span>
      </div>

      {/* Steps 5-card grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-2.5 mb-4">
        {progress.steps.map((step) => {
          const isCompleted = step.status === 'completed';
          const isActive = step.status === 'active';

          return (
            <div
              key={step.id}
              className={`p-3 rounded-lg border transition-all duration-150 flex flex-col justify-between min-h-[92px] ${
                isActive
                  ? 'bg-[#f1f6f3]/60 border-[#163328] ring-1 ring-[#163328]'
                  : isCompleted
                  ? 'bg-white border-[#e5e7e4]'
                  : 'bg-white/70 border-[#e5e7e4] opacity-75'
              }`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <span
                  className={`text-[10.5px] font-semibold tracking-wider ${
                    isActive
                      ? 'text-[#163328]'
                      : isCompleted
                      ? 'text-[#6b706c]'
                      : 'text-[#929792]'
                  }`}
                >
                  {step.number}
                </span>

                {isCompleted ? (
                  <CheckCircle2 className="w-4 h-4 text-[#163328]" />
                ) : isActive ? (
                  <span className="w-2.5 h-2.5 rounded-full bg-[#163328] animate-pulse" />
                ) : (
                  <Circle className="w-3.5 h-3.5 text-[#d0d7d2]" />
                )}
              </div>

              <div>
                <h4
                  className={`text-[13px] leading-tight truncate ${
                    isActive
                      ? 'font-semibold text-[#163328]'
                      : isCompleted
                      ? 'font-medium text-[#181a18]'
                      : 'font-normal text-[#6b706c]'
                  }`}
                >
                  {step.title}
                </h4>
                <p className="text-[11px] text-[#929792] leading-tight mt-1 line-clamp-1">
                  {step.detail}
                </p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Stepper bottom counters & metadata */}
      <div className="pt-2 flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2 text-[#181a18] font-medium">
          <FileSpreadsheet className="w-4 h-4 text-[#163328]" />
          <span>
            {progress.sourcesDiscovered} sources discovered · {progress.sourcesReviewed} sources reviewed
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className="bg-[#fafaf8] border border-[#e5e7e4] text-[#6b706c] text-[11px] px-2.5 py-1 rounded-md">
            Web &amp; academic: {progress.webAcademicCount} sources
          </span>
          <span className="bg-[#fafaf8] border border-[#e5e7e4] text-[#6b706c] text-[11px] px-2.5 py-1 rounded-md">
            Uploaded documents: {progress.uploadedDocumentsCount} sources
          </span>
        </div>
      </div>
    </div>
  );
};
