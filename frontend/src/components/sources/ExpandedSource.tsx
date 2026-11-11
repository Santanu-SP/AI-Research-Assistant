import React, { useState } from 'react';
import { ExternalLink, Copy, Check } from 'lucide-react';
import { SourceResponse } from '../../types/report';

interface ExpandedSourceProps {
  source: SourceResponse;
}

export const ExpandedSource: React.FC<ExpandedSourceProps> = ({ source }) => {
  const [isCopied, setIsCopied] = useState(false);

  const handleCopyBibtex = () => {
    if (!source.bibtex) return;
    navigator.clipboard.writeText(source.bibtex);
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  return (
    <div
      id={`source-${source.number}`}
      className="bg-canvas border-2 border-accent rounded-lg p-3.5 shadow-xs transition-all duration-200"
    >
      <div className="flex items-center justify-between gap-2 mb-1.5 text-xs">
        <div className="flex items-center gap-1.5 font-medium text-accent">
          <span className="font-bold">[S{source.number}]</span>
          {source.publisher && <span>{source.publisher}</span>}
          {source.publisher && source.year && <span className="text-ink-muted">·</span>}
          {source.year && <span>{source.year}</span>}
        </div>

        <span className="text-[10px] font-medium uppercase tracking-wider bg-accent-soft text-accent border border-accent-line px-2 py-0.5 rounded-full">
          {source.sourceType.replace('-', ' ')}
        </span>
      </div>

      <h4 className="text-[13.5px] font-semibold text-ink leading-snug mb-1">
        {source.title || 'Untitled uploaded source'}
      </h4>

      {source.authors.length > 0 && (
        <p className="text-xs text-ink-soft mb-3">
          {source.authors.join(', ')}
        </p>
      )}

      <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-ink-soft mb-3">
        {source.page && <span>Page {source.page}</span>}
        {source.section && <span>Section: {source.section}</span>}
        {source.doi && <span>DOI: {source.doi}</span>}
      </div>

      {source.relevantExcerpt && (
        <div className="bg-canvas border-l-2 border-accent pl-3 py-2 pr-2 text-xs text-ink-soft italic rounded-r mb-3 leading-relaxed">
          &ldquo;{source.relevantExcerpt}&rdquo;
        </div>
      )}

      <div className="flex items-center justify-between pt-2 border-t border-line text-xs">
        <div className="flex items-center gap-3">
          {source.url ? (
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent hover:text-accent font-medium inline-flex items-center gap-1 transition-colors"
            >
              <span>Open source</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          ) : (
            <span className="text-ink-soft font-medium inline-flex items-center gap-1 cursor-default">
              <span>View source</span>
              <ExternalLink className="w-3 h-3" />
            </span>
          )}

          {source.bibtex && <button
            type="button"
            onClick={handleCopyBibtex}
            className="text-ink-soft hover:text-ink font-medium inline-flex items-center gap-1 transition-colors cursor-pointer"
          >
            {isCopied ? (
              <>
                <Check className="w-3 h-3 text-emerald-600" />
                <span className="text-emerald-700">Copied!</span>
              </>
            ) : (
              <>
                <Copy className="w-3 h-3 text-ink-muted" />
                <span>Copy BibTeX</span>
              </>
            )}
          </button>}
        </div>

        {source.citationCount !== undefined && source.citationCount > 0 && (
          <span className="text-[11px] text-ink-muted font-medium">
            Cited {source.citationCount} {source.citationCount === 1 ? 'time' : 'times'}
          </span>
        )}
      </div>
    </div>
  );
};
