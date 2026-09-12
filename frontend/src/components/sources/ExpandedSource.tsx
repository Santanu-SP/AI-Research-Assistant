import React, { useState } from 'react';
import { ExternalLink, Copy, Check } from 'lucide-react';
import { Source } from '../../types/source';

interface ExpandedSourceProps {
  source: Source;
}

export const ExpandedSource: React.FC<ExpandedSourceProps> = ({ source }) => {
  const [isCopied, setIsCopied] = useState(false);

  const handleCopyBibtex = () => {
    const bibtex =
      source.bibtex ||
      `@article{source_${source.number},
  title={${source.title}},
  author={${source.authors.join(' and ')}},
  journal={${source.publisher}},
  year={${source.year}}
}`;
    navigator.clipboard.writeText(bibtex);
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  return (
    <div
      id={`source-${source.number}`}
      className="bg-[#fcfdfc] border-2 border-[#163328] rounded-lg p-3.5 shadow-xs transition-all duration-200"
    >
      {/* Top Metadata Row */}
      <div className="flex items-center justify-between gap-2 mb-1.5 text-xs">
        <div className="flex items-center gap-1.5 font-medium text-[#163328]">
          <span className="font-bold">[{source.number}]</span>
          <span>{source.publisher}</span>
          <span className="text-[#929792]">·</span>
          <span>{source.year}</span>
        </div>

        <span className="text-[10px] font-medium uppercase tracking-wider bg-[#f1f6f3] text-[#173d31] border border-[#d8e5df] px-2 py-0.5 rounded-full">
          {source.sourceType.replace('-', ' ')}
        </span>
      </div>

      {/* Title */}
      <h4 className="text-[13.5px] font-semibold text-[#181a18] leading-snug mb-1">
        {source.title}
      </h4>

      {/* Authors */}
      <p className="text-xs text-[#6b706c] mb-3">
        {source.authors.join(', ')}
      </p>

      {/* Relevant Excerpt */}
      {source.relevantExcerpt && (
        <div className="bg-[#fafaf8] border-l-2 border-[#163328] pl-3 py-2 pr-2 text-xs text-[#424744] italic rounded-r mb-3 leading-relaxed">
          &ldquo;{source.relevantExcerpt}&rdquo;
        </div>
      )}

      {/* Action Footer */}
      <div className="flex items-center justify-between pt-2 border-t border-[#e5e7e4] text-xs">
        <div className="flex items-center gap-3">
          {source.url ? (
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#163328] hover:text-[#214f40] font-medium inline-flex items-center gap-1 transition-colors"
            >
              <span>Open source</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          ) : (
            <span className="text-[#6b706c] font-medium inline-flex items-center gap-1 cursor-default">
              <span>View source</span>
              <ExternalLink className="w-3 h-3" />
            </span>
          )}

          <button
            type="button"
            onClick={handleCopyBibtex}
            className="text-[#6b706c] hover:text-[#181a18] font-medium inline-flex items-center gap-1 transition-colors cursor-pointer"
          >
            {isCopied ? (
              <>
                <Check className="w-3 h-3 text-emerald-600" />
                <span className="text-emerald-700">Copied!</span>
              </>
            ) : (
              <>
                <Copy className="w-3 h-3 text-[#929792]" />
                <span>Copy BibTeX</span>
              </>
            )}
          </button>
        </div>

        {source.citationCount !== undefined && source.citationCount > 0 && (
          <span className="text-[11px] text-[#929792] font-medium">
            Cited {source.citationCount} {source.citationCount === 1 ? 'time' : 'times'}
          </span>
        )}
      </div>
    </div>
  );
};
