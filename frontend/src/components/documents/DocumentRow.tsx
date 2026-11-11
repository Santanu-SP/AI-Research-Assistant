import React from 'react';
import { FileText, RotateCcw, Trash2 } from 'lucide-react';
import { Document } from '../../types/document';
import { StatusBadge } from '../common/StatusBadge';

interface DocumentRowProps {
  document: Document;
  onDelete: (id: string) => void;
  onOpen: (document: Document) => void;
  onRetry?: (id: string) => void;
  isRetrying?: boolean;
}

const formatSize = (bytes: number): string =>
  bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`;

const formatDate = (iso: string) =>
  new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(iso));

/** One document in a list. The parent supplies the surrounding border and dividers. */
export const DocumentRow: React.FC<DocumentRowProps> = ({
  document,
  onDelete,
  onOpen,
  onRetry,
  isRetrying = false,
}) => {
  const failed = document.status === 'failed';

  return (
    <div className="group flex flex-col gap-3 px-4 py-3.5 transition-colors hover:bg-subtle/50 sm:flex-row sm:items-center sm:px-5">
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <span className="relative mt-0.5 flex h-9 w-8 shrink-0 items-center justify-center rounded-md border border-line bg-subtle text-ink-soft">
          <FileText className="h-4 w-4" strokeWidth={1.75} />
          <span className="absolute -bottom-1.5 left-1/2 -translate-x-1/2 rounded-sm border border-line bg-panel px-1 font-mono text-[8.5px] font-medium uppercase leading-3 text-ink-soft">
            {document.type}
          </span>
        </span>

        <div className="min-w-0 flex-1">
          <button
            type="button"
            onClick={() => onOpen(document)}
            className="block max-w-full truncate rounded-sm text-left text-sm font-medium text-ink hover:underline hover:decoration-line-strong hover:underline-offset-2"
          >
            {document.title || document.name}
          </button>

          <p className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-ink-muted">
            {document.title && document.title !== document.name && (
              <>
                <span className="max-w-[220px] truncate">{document.name}</span>
                <span aria-hidden="true">·</span>
              </>
            )}
            <span className="tabular-nums">{formatSize(document.size)}</span>
            {document.pageCount ? (
              <>
                <span aria-hidden="true">·</span>
                <span className="tabular-nums">{document.pageCount} pages</span>
              </>
            ) : null}
            <span aria-hidden="true">·</span>
            <span>{formatDate(document.uploadedAt || document.createdAt)}</span>
            {document.authors && document.authors.length > 0 ? (
              <>
                <span aria-hidden="true">·</span>
                <span className="max-w-[200px] truncate" title={document.authors.join(', ')}>
                  {document.authors.join(', ')}
                </span>
              </>
            ) : null}
            {document.doi ? (
              <>
                <span aria-hidden="true">·</span>
                <span className="max-w-[140px] truncate font-mono text-[11px]" title={document.doi}>
                  {document.doi}
                </span>
              </>
            ) : null}
          </p>

          {failed && document.processingError && (
            <p className="mt-1 text-xs text-danger">{document.processingError}</p>
          )}
        </div>
      </div>

      <div className="flex shrink-0 items-center justify-between gap-2 pl-11 sm:justify-end sm:pl-0">
        <StatusBadge
          status={document.status}
          size="sm"
          title={failed && document.processingError ? document.processingError : undefined}
        />

        <div className="flex items-center gap-1">
          {failed && onRetry && (
            <button
              type="button"
              onClick={() => onRetry(document.id)}
              disabled={isRetrying}
              aria-label={`Retry processing ${document.name}`}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line bg-panel px-2.5 text-xs font-medium text-ink transition-colors hover:bg-subtle disabled:opacity-50"
            >
              <RotateCcw className={`h-3.5 w-3.5 ${isRetrying ? 'animate-spin' : ''}`} />
              Retry
            </button>
          )}

          <button
            type="button"
            onClick={() => onOpen(document)}
            className="inline-flex h-8 items-center rounded-md px-2.5 text-xs font-medium text-ink-soft transition-colors hover:bg-subtle hover:text-ink"
          >
            Details
          </button>

          <button
            type="button"
            onClick={() => onDelete(document.id)}
            title="Delete document"
            aria-label={`Delete ${document.name}`}
            className="flex h-8 w-8 items-center justify-center rounded-md text-ink-muted transition-colors hover:bg-danger-soft hover:text-danger"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
};
