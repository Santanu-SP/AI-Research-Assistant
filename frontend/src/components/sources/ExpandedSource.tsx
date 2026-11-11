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
      className="rounded-lg border border-accent-line bg-panel p-4 shadow-sm ring-1 ring-accent-line"
    >
      <div className="flex items-center justify-between gap-2 mb-1.5 text-xs">
        <div className="flex min-w-0 items-center gap-1.5 text-ink-muted">
          <span className="flex h-5 min-w-5 items-center justify-center rounded bg-solid px-1 font-mono text-[11px] font-medium text-on-solid">{source.number}</span>
          {source.publisher && <span>{source.publisher}</span>}
          {source.publisher && source.year && <span className="text-ink-muted">·</span>}
          {source.year && <span>{source.year}</span>}
        </div>

        <span className="shrink-0 rounded border border-line bg-subtle px-1.5 py-px text-[11px] font-medium capitalize text-ink-soft">
          {source.sourceType.replace('-', ' ')}
        </span>
      </div>

      <h4 className="mb-1 mt-2 text-sm font-semibold leading-snug text-ink">
        {source.title || 'Untitled uploaded source'}
      </h4>

      {source.authors.length > 0 && (
        <p className="mb-3 text-xs text-ink-muted">
          {source.authors.join(', ')}
        </p>
      )}

      <div className="mb-3 flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-soft">
        {source.page && <span className="tabular-nums">Page {source.page}</span>}
        {source.section && <span>{source.section}</span>}
        {source.doi && <span className="font-mono text-[11px]">{source.doi}</span>}
      </div>

      {source.relevantExcerpt && (
        <div className="mb-3 rounded-r border-l-2 border-accent-line bg-subtle/60 py-2 pl-3 pr-2 font-serif text-[13px] italic leading-relaxed text-ink-soft">
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
          ) : null}

          {source.bibtex && <button
            type="button"
            onClick={handleCopyBibtex}
            className="text-ink-soft hover:text-ink font-medium inline-flex items-center gap-1 transition-colors cursor-pointer"
          >
            {isCopied ? (
              <>
                <Check className="w-3 h-3 text-accent" />
                <span className="text-accent">Copied</span>
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
