/**
 * SourceCard (DocumentCard): Reusable card for a project document/source.
 *
 * Renders only fields that have real values from the backend.
 * Does not show: internal local paths (source_uri), raw processing stack traces.
 * Architecture is future-ready for multiple source types but only exposes
 * actions backend actually supports.
 */
import React from 'react';
import { FileText, Trash2 } from 'lucide-react';
import { Document } from '../../types/document';
import { IngestionStatus } from '../common/IngestionStatus';
import { SourceTypeLabel, ContentLevelLabel } from '../common/SourceTypeLabel';

interface SourceCardProps {
  document: Document;
  onDelete?: (id: string) => void;
  isArchived?: boolean;
}

const formatSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const formatDate = (iso: string): string =>
  new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year:
      new Date(iso).getFullYear() === new Date().getFullYear()
        ? undefined
        : 'numeric',
  }).format(new Date(iso));

/** Extract a safe error summary (no internal paths, no Python tracebacks). */
const safeErrorSummary = (error: string | null | undefined): string | null => {
  if (!error) return null;
  const firstLine = error.split('\n')[0].trim();
  // Suppress Python tracebacks and long internal error strings
  if (
    firstLine.startsWith('Traceback') ||
    firstLine.includes('File "') ||
    firstLine.length > 120
  ) {
    return 'Processing failed. Contact support if this persists.';
  }
  return firstLine;
};

export const SourceCard: React.FC<SourceCardProps> = ({
  document,
  onDelete,
  isArchived = false,
}) => {
  const displayName = document.title || document.name;
  const showFileName = document.title && document.title !== document.name;

  return (
    <div
      className="bg-white border border-[#e5e7e4] rounded-xl p-4 flex flex-col sm:flex-row sm:items-start gap-4 hover:border-[#cbd0ca] hover:shadow-xs transition-all duration-150"
      data-document-id={document.id}
    >
      {/* File icon */}
      <div className="w-9 h-9 rounded-lg bg-[#f1f6f3] flex items-center justify-center shrink-0">
        <FileText className="w-5 h-5 text-[#163328]" />
      </div>

      {/* Main content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-[#181a18] leading-snug truncate">
              {displayName}
            </p>
            {showFileName && (
              <p className="text-[11px] text-[#929792] truncate mt-0.5">
                {document.name}
              </p>
            )}
          </div>

          {onDelete && !isArchived && (
            <button
              type="button"
              aria-label={`Delete document: ${displayName}`}
              onClick={() => onDelete(document.id)}
              className="shrink-0 p-1.5 text-[#929792] hover:text-[#b91c1c] hover:bg-[#fee2e2]/40 rounded-md transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Metadata row */}
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <IngestionStatus
            status={document.ingestionStatus}
            errorSummary={safeErrorSummary(document.processingError)}
          />
          <SourceTypeLabel sourceType={document.sourceType} />
          <ContentLevelLabel contentLevel={document.contentLevel} />
          {document.type && (
            <span className="text-[10px] font-medium text-[#929792] uppercase tracking-wide">
              {document.type}
            </span>
          )}
        </div>

        {/* Secondary metadata row */}
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[#929792]">
          <span>{formatSize(document.size)}</span>
          {document.pageCount && document.pageCount > 0 && (
            <span>{document.pageCount} pages</span>
          )}
          {document.chunkCount !== undefined && document.chunkCount > 0 && (
            <span>{document.chunkCount} chunks</span>
          )}
          {document.doi && (
            <a
              href={`https://doi.org/${document.doi}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#163328] hover:underline"
              onClick={(e) => e.stopPropagation()}
            >
              DOI: {document.doi}
            </a>
          )}
          <span>Added {formatDate(document.uploadedAt)}</span>
        </div>
      </div>
    </div>
  );
};
