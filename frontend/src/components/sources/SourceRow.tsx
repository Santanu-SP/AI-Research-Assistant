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
      className="w-full text-left p-3 bg-panel border border-line hover:border-line-strong hover:bg-canvas rounded-lg transition-all duration-150 cursor-pointer group focus:outline-none focus:ring-2 focus:ring-accent/30"
    >
      <div className="flex items-start gap-2.5">
        <span className="font-semibold text-xs text-accent bg-accent-soft border border-accent-line min-w-[22px] h-[20px] rounded flex items-center justify-center shrink-0 mt-0.5 group-hover:bg-solid group-hover:text-on-solid transition-colors">
          [S{source.number}]
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-1 text-[11px] text-ink-muted mb-0.5">
            <span className="truncate">
              {[source.publisher, source.year].filter(Boolean).join(' · ') || `Page ${source.page ?? '—'}`}
            </span>
            {source.citationCount !== undefined && source.citationCount > 0 && (
              <span className="shrink-0 text-[10px] text-ink-muted">
                {source.citationCount}× cited
              </span>
            )}
          </div>

          <h5 className="text-[13px] font-medium text-ink group-hover:text-accent transition-colors leading-snug line-clamp-2">
            {source.title || 'Untitled uploaded source'}
          </h5>

          {source.authors.length > 0 && (
            <p className="text-[11.5px] text-ink-soft truncate mt-0.5">
              {source.authors.join(', ')}
            </p>
          )}
        </div>
      </div>
    </button>
  );
};
