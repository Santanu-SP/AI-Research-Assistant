import React from 'react';
import { LoadingOrb } from './LoadingOrb';

interface LoadingStateProps {
  rows?: number;
}

/** Skeleton rows shown while a list loads. */
export const LoadingState: React.FC<LoadingStateProps> = ({ rows = 3 }) => (
  <div
    aria-busy="true"
    aria-label="Loading"
    className="w-full divide-y divide-line overflow-hidden rounded-lg border border-line bg-panel"
  >
    {Array.from({ length: rows }).map((_, i) => (
      <div key={i} className="flex animate-pulse items-center gap-4 px-4 py-4 sm:px-5">
        <div className="h-8 w-8 shrink-0 rounded-md bg-subtle" />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="h-3.5 w-2/3 rounded bg-subtle sm:w-1/3" />
          <div className="h-3 w-full rounded bg-subtle/70 sm:w-1/2" />
        </div>
        <div className="hidden h-5 w-16 rounded-full bg-subtle sm:block" />
      </div>
    ))}
  </div>
);

interface CenteredLoadingStateProps {
  label: string;
}

/** A focused, low-noise waiting state for full-page data fetches. */
export const CenteredLoadingState: React.FC<CenteredLoadingStateProps> = ({ label }) => (
  <div className="flex min-h-[15rem] flex-1 flex-col items-center justify-center gap-3 text-center">
    <LoadingOrb size={32} label={label} />
    <p className="text-xs text-ink-muted">{label}</p>
  </div>
);
