import React from 'react';
import { FileText, Trash2 } from 'lucide-react';
import { Document } from '../../types/document';
import { isDocumentPending } from '../../services/documents.service';

interface SourceCardProps {
  document: Document;
  /** Opens a ready document. Files that are still being prepared can't be opened. */
  onOpen?: (document: Document) => void;
  onDelete?: (id: string) => void;
  onRetry?: (id: string) => void;
  isRetrying?: boolean;
  isDeleting?: boolean;
  isArchived?: boolean;
  /** Tighter row for side panels. */
  compact?: boolean;
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
    year: new Date(iso).getFullYear() === new Date().getFullYear() ? undefined : 'numeric',
  }).format(new Date(iso));

const FileGlyph: React.FC<{ type?: string; state: 'ready' | 'preparing' | 'failed'; compact: boolean }> = ({
  type,
  state,
  compact,
}) => (
  <span
    className={`relative flex shrink-0 items-center justify-center rounded-md border ${
      compact ? 'h-8 w-7' : 'mt-0.5 h-9 w-8'
    } ${
      state === 'failed'
        ? 'border-danger-line bg-danger-soft text-danger'
        : state === 'preparing'
          ? 'border-line bg-subtle text-ink-muted'
          : 'border-line bg-subtle text-ink-soft'
    }`}
    aria-hidden="true"
  >
    {state === 'preparing' ? (
      <span className="h-3.5 w-3.5 animate-spin rounded-full border-[1.5px] border-line-strong border-t-ink-soft [animation-duration:1.1s]" />
    ) : (
      <FileText className="h-4 w-4" strokeWidth={1.75} />
    )}
    {type && state !== 'preparing' && (
      <span className="absolute -bottom-1.5 left-1/2 -translate-x-1/2 rounded-sm border border-line bg-panel px-1 font-mono text-[8.5px] font-medium uppercase leading-3 text-ink-soft">
        {type}
      </span>
    )}
  </span>
);

/**
 * One document in a list. Users only see three states: ready (opens in the
 * workspace), preparing (a quiet placeholder while the server works on it)
 * and a plain failure with retry and remove.
 */
export const SourceCard: React.FC<SourceCardProps> = ({
  document,
  onOpen,
  onDelete,
  onRetry,
  isRetrying = false,
  isDeleting = false,
  isArchived = false,
  compact = false,
}) => {
  const displayName = document.title || document.name;
  const showFileName = !compact && document.title && document.title !== document.name;
  const state = document.status === 'failed' ? 'failed' : isDocumentPending(document) ? 'preparing' : 'ready';
  const canOpen = state === 'ready' && Boolean(onOpen);
  const canEdit = !isArchived && !isDeleting;

  const meta: string[] = [];
  if (document.pageCount && document.pageCount > 0) meta.push(`${document.pageCount} pages`);
  meta.push(formatSize(document.size));
  if (!compact) meta.push(`Added ${formatDate(document.uploadedAt)}`);

  const name = (
    <>
      <span className={`block truncate font-medium leading-snug ${compact ? 'text-[13px]' : 'text-sm'} ${state === 'ready' ? 'text-ink' : 'text-ink-soft'}`}>
        {displayName}
      </span>
      {showFileName && <span className="mt-0.5 block truncate text-xs text-ink-muted">{document.name}</span>}
    </>
  );

  return (
    <div
      className={`doc-row group flex items-start gap-3 transition-colors ${compact ? 'px-3 py-2.5' : 'px-4 py-3.5 sm:px-5'} ${
        canOpen ? 'hover:bg-subtle/60' : ''
      } ${isDeleting ? 'opacity-50' : ''}`}
      data-document-id={document.id}
      data-state={state}
      aria-busy={state === 'preparing' || undefined}
    >
      <FileGlyph type={document.type} state={state} compact={compact} />

      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            {canOpen ? (
              <button
                type="button"
                onClick={() => onOpen?.(document)}
                className="block w-full min-w-0 rounded-sm text-left after:absolute after:inset-0 focus-visible:outline-offset-2"
                aria-label={`Open ${displayName}`}
              >
                {name}
              </button>
            ) : (
              <div aria-disabled={state === 'preparing' || undefined}>{name}</div>
            )}
          </div>

          {onDelete && canEdit && (
            <button
              type="button"
              aria-label={`Delete document: ${displayName}`}
              title="Delete"
              onClick={() => onDelete(document.id)}
              className={`relative z-[1] flex shrink-0 items-center justify-center rounded-md text-ink-muted transition-[opacity,color,background-color] hover:bg-danger-soft hover:text-danger focus-visible:opacity-100 ${
                compact ? 'h-7 w-7' : 'h-8 w-8'
              } ${state === 'failed' ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 [@media(hover:none)]:opacity-100'}`}
            >
              <Trash2 className="h-4 w-4" />
            </button>
          )}
        </div>

        {state === 'preparing' ? (
          <p className="mt-1 flex items-center gap-2 text-xs text-ink-muted">
            <span>Preparing…</span>
            <span className="doc-skeleton h-1.5 w-16 rounded-full" aria-hidden="true" />
          </p>
        ) : state === 'failed' ? (
          <p className="mt-1 flex flex-wrap items-center gap-x-1.5 text-xs text-ink-soft">
            <span>Couldn’t process this file.</span>
            {onRetry && canEdit && (
              <button
                type="button"
                onClick={() => onRetry(document.id)}
                disabled={isRetrying}
                className="relative z-[1] font-medium text-accent hover:underline disabled:opacity-60"
              >
                {isRetrying ? 'Trying again…' : 'Try again'}
              </button>
            )}
          </p>
        ) : (
          <p className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-ink-muted">
            {document.type && <span className="uppercase">{document.type}</span>}
            {meta.map((item) => (
              <React.Fragment key={item}>
                <span aria-hidden="true">·</span>
                <span className="tabular-nums">{item}</span>
              </React.Fragment>
            ))}
            {!compact && document.doi && (
              <>
                <span aria-hidden="true">·</span>
                <a
                  href={`https://doi.org/${document.doi}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="relative z-[1] text-accent hover:underline"
                >
                  DOI: {document.doi}
                </a>
              </>
            )}
          </p>
        )}
      </div>
    </div>
  );
};
