import React from 'react';
import { SourceResponse } from '../../types/report';

interface SourceRowProps {
  source: SourceResponse;
  onSelect: (number: number) => void;
}

export const SourceRow: React.FC<SourceRowProps> = ({ source, onSelect }) => {
  return (
    <button
      id={`source-${source.number}`}
      type="button"
      onClick={() => onSelect(source.number)}
      className="group w-full cursor-pointer rounded-lg border border-transparent px-3 py-2.5 text-left transition-colors hover:border-line hover:bg-subtle/60"
    >
      <div className="flex items-start gap-2.5">
        <span className="mt-0.5 flex h-5 min-w-5 shrink-0 items-center justify-center rounded bg-subtle px-1 font-mono text-[11px] font-medium text-ink-soft group-hover:bg-accent-soft group-hover:text-accent">
          {source.number}
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-1 text-[11px] text-ink-muted mb-0.5">
            <span className="truncate">
              {[source.publisher, source.year].filter(Boolean).join(' · ') || `Page ${source.page ?? '—'}`}
            </span>
            {source.citationCount !== undefined && source.citationCount > 0 && (
              <span className="shrink-0 tabular-nums text-[11px] text-ink-muted">
                {source.citationCount}× cited
              </span>
            )}
          </div>

          <h5 className="line-clamp-2 text-[13px] font-medium leading-snug text-ink">
            {source.title || 'Untitled uploaded source'}
          </h5>

          {source.authors.length > 0 && (
            <p className="mt-0.5 truncate text-xs text-ink-muted">
              {source.authors.join(', ')}
            </p>
          )}
        </div>
      </div>
    </button>
  );
};
