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
      className="w-full text-left p-3 bg-white border border-[#e5e7e4] hover:border-[#cbd0ca] hover:bg-[#fafaf8] rounded-lg transition-all duration-150 cursor-pointer group focus:outline-none focus:ring-2 focus:ring-[#163328]/30"
    >
      <div className="flex items-start gap-2.5">
        <span className="font-semibold text-xs text-[#163328] bg-[#f1f6f3] border border-[#d8e5df] min-w-[22px] h-[20px] rounded flex items-center justify-center shrink-0 mt-0.5 group-hover:bg-[#163328] group-hover:text-white transition-colors">
          [{source.number}]
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-1 text-[11px] text-[#929792] mb-0.5">
            <span className="truncate">{source.publisher} · {source.year}</span>
            {source.citationCount !== undefined && source.citationCount > 0 && (
              <span className="shrink-0 text-[10px] text-[#929792]">
                {source.citationCount}× cited
              </span>
            )}
          </div>

          <h5 className="text-[13px] font-medium text-[#181a18] group-hover:text-[#163328] transition-colors leading-snug line-clamp-2">
            {source.title}
          </h5>

          <p className="text-[11.5px] text-[#6b706c] truncate mt-0.5">
            {source.authors.join(', ')}
          </p>
        </div>
      </div>
    </button>
  );
};
