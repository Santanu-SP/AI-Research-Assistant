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
        className={`inline-flex items-center justify-center min-w-[20px] h-[18px] px-1 text-[11px] font-semibold rounded-[4px] border transition-all duration-150 select-none cursor-pointer ${
          isSelected
            ? 'bg-solid text-on-solid border-accent ring-2 ring-accent/20'
            : 'bg-accent-soft text-accent border-accent-line hover:bg-solid hover:text-on-solid hover:border-accent'
        }`}
      >
        [S{number}]
      </button>

      {isHovered && source && (
        <div
          className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-72 p-3 bg-inverse text-on-inverse rounded-lg shadow-xl z-50 pointer-events-none text-left text-xs animate-in fade-in zoom-in-95 duration-150"
          style={{ transformOrigin: 'bottom center' }}
        >
          <div className="flex items-center justify-between text-[10.5px] text-ink-muted mb-1">
            <span className="font-semibold text-emerald-400">[S{source.number}] {source.publisher || 'Uploaded source'}</span>
            <span>{source.year || ''}</span>
          </div>
          <div className="font-medium text-white text-[12.5px] leading-snug mb-1 line-clamp-2">
            {source.title || 'Untitled uploaded source'}
          </div>
          <div className="text-[11px] text-ink-muted truncate">
            {source.authors.join(', ')}
          </div>
          <div className="mt-2 pt-1.5 border-t border-white/10 text-[10px] text-emerald-300 flex items-center justify-between">
            <span>Click to inspect in Sources panel</span>
            {source.citationCount !== undefined && (
              <span>Cited {source.citationCount} times</span>
            )}
          </div>
          <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-1 border-4 border-transparent border-t-ink" />
        </div>
      )}
    </span>
  );
};
