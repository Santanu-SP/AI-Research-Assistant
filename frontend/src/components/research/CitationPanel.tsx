/**
 * CitationPanel: Detailed view of a single citation/evidence record.
 *
 * Shows only backend-provided fields. Hides null/zero values (page 0 = null,
 * "Unknown section" = hidden). Does not fabricate source details.
 */
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
    <div className="bg-white border border-[#e5e7e4] rounded-xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-[#f5f5f2] bg-[#fafaf8]">
        <div className="flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-[#163328]" />
          <span className="text-sm font-semibold text-[#181a18]">
            Citation Evidence
          </span>
        </div>
        <button
          type="button"
          aria-label="Close citation panel"
          onClick={onClose}
          className="text-[#929792] hover:text-[#181a18] p-1 rounded-md hover:bg-[#f5f5f2] transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Content */}
      <div className="p-5 space-y-4">
        {/* Paper title */}
        {citation.paperTitle && (
          <div>
            <div className="flex items-start gap-2">
              <FileText className="w-4 h-4 text-[#929792] shrink-0 mt-0.5" />
              <p className="text-sm font-semibold text-[#181a18] leading-snug">
                {citation.paperTitle}
              </p>
            </div>
            {hasAuthors && (
              <p className="text-xs text-[#6b706c] mt-1 ml-6">
                {citation.authors!.join(', ')}
              </p>
            )}
          </div>
        )}

        {/* Metadata badges */}
        <div className="flex flex-wrap items-center gap-2 ml-0">
          {citation.sourceType && (
            <SourceTypeLabel sourceType={citation.sourceType} />
          )}
          {citation.contentLevel && (
            <ContentLevelLabel contentLevel={citation.contentLevel} />
          )}
          {hasPage && (
            <span className="inline-flex items-center gap-1 text-[10px] text-[#929792]">
              <Hash className="w-3 h-3" />
              Page {citation.page}
              {hasPageEnd && citation.pageEnd !== citation.page
                ? `–${citation.pageEnd}`
                : ''}
            </span>
          )}
          {hasSection && (
            <span className="text-[10px] text-[#929792] italic">
              § {citation.section}
            </span>
          )}
          {hasDoi && (
            <a
              href={`https://doi.org/${citation.doi}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[10px] text-[#163328] hover:underline"
            >
              DOI: {citation.doi}
            </a>
          )}
        </div>

        {/* Evidence excerpt */}
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-[#929792] mb-2">
            Evidence excerpt
          </p>
          <blockquote className="border-l-2 border-[#163328] pl-4 text-sm text-[#424744] leading-relaxed italic bg-[#fafaf8] py-2 pr-3 rounded-r-lg">
            {citation.excerpt}
          </blockquote>
        </div>

        {/* Technical IDs – useful for debugging, hidden when not meaningful */}
        <details className="text-[11px] text-[#929792]">
          <summary className="cursor-pointer hover:text-[#6b706c] transition-colors">
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
