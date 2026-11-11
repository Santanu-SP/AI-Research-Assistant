import React, { useState, useRef } from 'react';
import { SourceResponse } from '../../types/report';

interface CitationChipProps {
  number: number;
  source?: SourceResponse;
  isSelected?: boolean;
  onSelect: (number: number) => void;
}

export const CitationChip: React.FC<CitationChipProps> = ({
  number,
  source,
  isSelected = false,
  onSelect,
}) => {
  const [isHovered, setIsHovered] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);

  return (
    <span className="relative inline-block mx-0.5 align-baseline">
      <button
        ref={triggerRef}
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onSelect(number);
        }}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        onFocus={() => setIsHovered(true)}
        onBlur={() => setIsHovered(false)}
        aria-label={`Citation [S${number}] - ${source?.title || 'Source reference'}`}
        className={`inline-flex h-[18px] min-w-[18px] -translate-y-px cursor-pointer select-none items-center justify-center rounded px-1 align-middle font-mono text-[11px] font-medium leading-none transition-colors duration-150 ${
          isSelected
            ? 'bg-solid text-on-solid'
            : 'bg-accent-soft text-accent hover:bg-accent-muted'
        }`}
      >
        {number}
      </button>

      {isHovered && source && (
        <span
          role="tooltip"
          className="dialog-enter pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 block w-72 -translate-x-1/2 rounded-lg border border-line bg-panel p-3 text-left font-sans text-xs shadow-lg"
        >
          <span className="mb-1 flex items-center justify-between text-[11px] text-ink-muted">
            <span>
              <span className="font-mono font-medium text-accent">{source.number}</span>
              {' · '}
              {source.publisher || 'Uploaded source'}
            </span>
            <span className="tabular-nums">{source.year || ''}</span>
          </span>
          <span className="mb-1 line-clamp-2 block text-[13px] font-medium leading-snug text-ink">
            {source.title || 'Untitled uploaded source'}
          </span>
          <span className="block truncate text-xs text-ink-muted">{source.authors.join(', ')}</span>
          <span className="mt-2 flex items-center justify-between border-t border-line pt-2 text-[11px] text-ink-muted">
            <span>Click to open in sources</span>
            {source.citationCount !== undefined && (
              <span className="tabular-nums">Cited {source.citationCount}×</span>
            )}
          </span>
        </span>
      )}
    </span>
  );
};
