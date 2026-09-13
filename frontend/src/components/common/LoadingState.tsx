import React from 'react';
import { LoadingOrb } from './LoadingOrb';

interface LoadingStateProps {
  rows?: number;
}

export const LoadingState: React.FC<LoadingStateProps> = ({ rows = 3 }) => {
  return (
    <div className="w-full bg-white border border-[#e5e7e4] rounded-xl overflow-hidden shadow-xs divide-y divide-[#e5e7e4]">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 animate-pulse">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <div className="h-5 w-16 bg-[#f1f6f3] rounded"></div>
              <div className="h-5 w-20 bg-[#fafaf8] rounded"></div>
            </div>
            <div className="h-5 w-3/4 sm:w-1/2 bg-[#f5f5f2] rounded mb-2"></div>
            <div className="h-4 w-full sm:w-2/3 bg-[#fafaf8] rounded"></div>
          </div>
          <div className="flex items-center justify-between sm:justify-end gap-5 shrink-0 pt-2 sm:pt-0">
            <div className="flex flex-col items-end gap-1.5">
              <div className="h-4 w-16 bg-[#f5f5f2] rounded"></div>
              <div className="h-3 w-20 bg-[#fafaf8] rounded"></div>
            </div>
            <div className="w-8 h-8 rounded-full bg-[#f1f6f3]"></div>
          </div>
        </div>
      ))}
    </div>
  );
};

interface CenteredLoadingStateProps {
  label: string;
}

/** A focused, low-noise waiting state for full-page data fetches. */
export const CenteredLoadingState: React.FC<CenteredLoadingStateProps> = ({ label }) => (
  <div className="flex min-h-[15rem] flex-col items-center justify-center gap-3 text-center">
    <LoadingOrb size={46} label={label} />
    <p className="text-xs text-[#6b706c]">{label}</p>
  </div>
);
