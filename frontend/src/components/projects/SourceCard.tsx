import React from 'react';
import { FileText, RotateCcw, Trash2 } from 'lucide-react';
import { Document } from '../../types/document';
import { IngestionStatus } from '../common/IngestionStatus';
import { SourceTypeLabel, ContentLevelLabel } from '../common/SourceTypeLabel';

interface SourceCardProps {
  document: Document;
  onDelete?: (id: string) => void;
  onRetry?: (id: string) => void;
  isRetrying?: boolean;
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

/** A document inside a project. Rendered as a row; the parent list draws the borders. */
export const SourceCard: React.FC<SourceCardProps> = ({
  document,
  onDelete,
  onRetry,
  isRetrying = false,
  isArchived = false,
}) => {
  const displayName = document.title || document.name;
  const showFileName = document.title && document.title !== document.name;
  const showSourceType = document.sourceType !== 'uploaded_file';
  const showContentLevel = document.contentLevel !== 'user_document';

  return (
    <div
      className="group flex items-start gap-3 px-4 py-3.5 transition-colors hover:bg-subtle/50 sm:px-5"
      data-document-id={document.id}
    >
      <span className="relative mt-0.5 flex h-9 w-8 shrink-0 items-center justify-center rounded-md border border-line bg-subtle text-ink-soft">
        <FileText className="h-4 w-4" strokeWidth={1.75} />
        {document.type && (
          <span className="absolute -bottom-1.5 left-1/2 -translate-x-1/2 rounded-sm border border-line bg-panel px-1 font-mono text-[8.5px] font-medium uppercase leading-3 text-ink-soft">
            {document.type}
          </span>
        )}
      </span>

      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium leading-snug text-ink">{displayName}</p>
            {showFileName && (
              <p className="mt-0.5 truncate text-xs text-ink-muted">{document.name}</p>
            )}
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <IngestionStatus status={document.ingestionStatus} />
            {onRetry && !isArchived && document.status === 'failed' && (
              <button
                type="button"
                aria-label={`Retry processing: ${displayName}`}
                title="Retry processing"
                disabled={isRetrying}
                onClick={() => onRetry(document.id)}
                className="flex h-8 w-8 items-center justify-center rounded-md text-ink-muted transition-colors hover:bg-subtle hover:text-ink disabled:opacity-50"
              >
                <RotateCcw className={`h-4 w-4 ${isRetrying ? 'animate-spin' : ''}`} />
              </button>
            )}
            {onDelete && !isArchived && (
              <button
                type="button"
                aria-label={`Delete document: ${displayName}`}
                title="Delete document"
                onClick={() => onDelete(document.id)}
                className="flex h-8 w-8 items-center justify-center rounded-md text-ink-muted transition-colors hover:bg-danger-soft hover:text-danger"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>

        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
          <span className="tabular-nums">{formatSize(document.size)}</span>
          {document.pageCount && document.pageCount > 0 && (
            <span className="tabular-nums">{document.pageCount} pages</span>
          )}
          {document.chunkCount !== undefined && document.chunkCount > 0 && (
            <span className="tabular-nums">{document.chunkCount} chunks</span>
          )}
          {showSourceType && <SourceTypeLabel sourceType={document.sourceType} />}
          {showContentLevel && <ContentLevelLabel contentLevel={document.contentLevel} />}
          {document.doi && (
            <a
              href={`https://doi.org/${document.doi}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent hover:underline"
              onClick={(e) => e.stopPropagation()}
            >
              DOI: {document.doi}
            </a>
          )}
          <span>Added {formatDate(document.uploadedAt)}</span>
        </div>

        {document.status === 'failed' && safeErrorSummary(document.processingError) && (
          <p className="mt-1.5 text-xs text-danger">{safeErrorSummary(document.processingError)}</p>
        )}
      </div>
    </div>
  );
};
