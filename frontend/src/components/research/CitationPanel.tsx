/** Page 0 and the placeholder "Unknown section" are omitted rather than shown. */
import React from 'react';
import { X, FileText, BookOpen, Hash } from 'lucide-react';
import { Citation } from '../../types/research';
import { SourceTypeLabel, ContentLevelLabel } from '../common/SourceTypeLabel';

interface CitationPanelProps {
  citation: Citation | null;
  onClose: () => void;
}

export const CitationPanel: React.FC<CitationPanelProps> = ({
  citation,
  onClose,
}) => {
  if (!citation) return null;

  const hasPage = citation.page !== null && citation.page !== undefined && citation.page > 0;
  const hasPageEnd = citation.pageEnd !== null && citation.pageEnd !== undefined && citation.pageEnd > 0;
  const hasDoi = Boolean(citation.doi);
  const hasSection = Boolean(citation.section);
  const hasAuthors = citation.authors && citation.authors.length > 0;

  return (
    <div className="bg-panel border border-line rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-line bg-canvas">
        <div className="flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-accent" />
          <span className="text-sm font-semibold text-ink">
            Citation Evidence
          </span>
        </div>
        <button
          type="button"
          aria-label="Close citation panel"
          onClick={onClose}
          className="text-ink-muted hover:text-ink p-1 rounded-md hover:bg-subtle transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="p-5 space-y-4">
        {citation.paperTitle && (
          <div>
            <div className="flex items-start gap-2">
              <FileText className="w-4 h-4 text-ink-muted shrink-0 mt-0.5" />
              <p className="text-sm font-semibold text-ink leading-snug">
                {citation.paperTitle}
              </p>
            </div>
            {hasAuthors && (
              <p className="text-xs text-ink-soft mt-1 ml-6">
                {citation.authors!.join(', ')}
              </p>
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2 ml-0">
          {citation.sourceType && (
            <SourceTypeLabel sourceType={citation.sourceType} />
          )}
          {citation.contentLevel && (
            <ContentLevelLabel contentLevel={citation.contentLevel} />
          )}
          {hasPage && (
            <span className="inline-flex items-center gap-1 text-[10px] text-ink-muted">
              <Hash className="w-3 h-3" />
              Page {citation.page}
              {hasPageEnd && citation.pageEnd !== citation.page
                ? `–${citation.pageEnd}`
                : ''}
            </span>
          )}
          {hasSection && (
            <span className="text-[10px] text-ink-muted italic">
              § {citation.section}
            </span>
          )}
          {hasDoi && (
            <a
              href={`https://doi.org/${citation.doi}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[10px] text-accent hover:underline"
            >
              DOI: {citation.doi}
            </a>
          )}
        </div>

        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted mb-2">
            Evidence excerpt
          </p>
          <blockquote className="border-l-2 border-accent pl-4 text-sm text-ink-soft leading-relaxed italic bg-canvas py-2 pr-3 rounded-r-lg">
            {citation.excerpt}
          </blockquote>
        </div>

        {/* Technical IDs – useful for debugging, hidden when not meaningful */}
        <details className="text-[11px] text-ink-muted">
          <summary className="cursor-pointer hover:text-ink-soft transition-colors">
            Technical details
          </summary>
          <dl className="mt-2 space-y-1 font-mono">
            <div>
              <dt className="inline">Citation ID: </dt>
              <dd className="inline break-all">{citation.citationId}</dd>
            </div>
            <div>
              <dt className="inline">Chunk: </dt>
              <dd className="inline break-all">{citation.chunkId}</dd>
            </div>
            <div>
              <dt className="inline">Document: </dt>
              <dd className="inline break-all">{citation.documentId}</dd>
            </div>
          </dl>
        </details>
      </div>
    </div>
  );
};
