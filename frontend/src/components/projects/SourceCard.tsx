import React from 'react';
import { FileText, Folder, Sparkles, Trash2, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Document } from '../../types/document';
import { isDocumentPending } from '../../services/documents.service';
import { ingestionStep } from '../../lib/ingestionProgress';

interface SourceCardProps {
  document: Document;
  /** Opens a ready document. Files that are still being prepared can't be opened. */
  onOpen?: (document: Document) => void;
  onDelete?: (id: string) => void;
  /** Takes the document off a list (e.g. this research) without deleting the file. */
  onRemove?: (id: string) => void;
  onRetry?: (id: string) => void;
  isRetrying?: boolean;
  isDeleting?: boolean;
  isArchived?: boolean;
  /** Tighter row for side panels. */
  compact?: boolean;
  /** Show the project and research runs that use this file. */
  showUsage?: boolean;
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
  onRemove,
  onRetry,
  isRetrying = false,
  isDeleting = false,
  isArchived = false,
  compact = false,
  showUsage = false,
}) => {
  const displayName = document.title || document.name;
  const showFileName = !compact && document.title && document.title !== document.name;
  const state = document.status === 'failed' ? 'failed' : isDocumentPending(document) ? 'preparing' : 'ready';
  const canOpen = state === 'ready' && Boolean(onOpen);
  const step = ingestionStep(document);
  const canEdit = !isArchived && !isDeleting;

  const meta: string[] = [];
  if (document.pageCount && document.pageCount > 0) {
    const unit =
      document.type === 'pptx'
        ? ['slide', 'slides']
        : document.type === 'xlsx'
          ? ['sheet', 'sheets']
          : document.type === 'audio' || document.type === 'video' || document.type === 'youtube'
            ? ['segment', 'segments']
            : document.type === 'web' || document.type === 'html' || document.type === 'image'
              ? ['section', 'sections']
              : ['page', 'pages'];
    meta.push(`${document.pageCount} ${document.pageCount === 1 ? unit[0] : unit[1]}`);
  }
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

          {onRemove && (
            <button
              type="button"
              aria-label={`Remove from this research: ${displayName}`}
              title="Remove from this research"
              onClick={() => onRemove(document.id)}
              className={`relative z-[1] flex shrink-0 cursor-pointer items-center justify-center rounded-md text-ink-muted transition-[opacity,color,background-color] hover:bg-subtle hover:text-ink focus-visible:opacity-100 ${
                compact ? 'h-7 w-7' : 'h-8 w-8'
              } opacity-0 group-hover:opacity-100 [@media(hover:none)]:opacity-100`}
            >
              <X className="h-4 w-4" />
            </button>
          )}

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
            <span aria-live="polite">{step.label}</span>
            {step.percent === null ? (
              <span className="doc-skeleton h-1.5 w-16 rounded-full" aria-hidden="true" />
            ) : (
              <span
                className="relative h-1.5 w-16 overflow-hidden rounded-full bg-subtle"
                role="progressbar"
                aria-label={`Preparing ${displayName}`}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={step.percent}
              >
                <span
                  className="absolute inset-y-0 left-0 rounded-full bg-accent transition-[width] duration-500"
                  style={{ width: `${step.percent}%` }}
                />
              </span>
            )}
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
        {showUsage && <UsageTags document={document} />}
      </div>
    </div>
  );
};

const TAG_CLASS =
  'relative z-[1] inline-flex max-w-[14rem] items-center gap-1 rounded-md border border-line bg-subtle/70 px-1.5 py-0.5 text-[11px] text-ink-soft';

/** Where a file is used: its project and the research runs limited to it. */
const UsageTags: React.FC<{ document: Document }> = ({ document }) => {
  const usedIn = document.usedIn ?? [];
  const more = Math.max(0, (document.usedInCount ?? usedIn.length) - usedIn.length);
  if (!document.projectName && usedIn.length === 0) {
    return <p className="mt-1.5 text-[11px] text-ink-muted">Not used in any project or research yet</p>;
  }
  return (
    <ul className="mt-1.5 flex flex-wrap items-center gap-1.5" aria-label="Used in">
      {document.projectName && document.projectId && (
        <li>
          <Link to={`/projects/${document.projectId}`} className={`${TAG_CLASS} hover:text-ink`} title={`Project: ${document.projectName}`}>
            <Folder className="h-3 w-3 shrink-0" aria-hidden="true" />
            <span className="truncate">{document.projectName}</span>
          </Link>
        </li>
      )}
      {usedIn.map((run) => (
        <li key={run.id}>
          <Link to={`/research/${run.id}`} className={`${TAG_CLASS} hover:text-ink`} title={`Research: ${run.title}`}>
            <Sparkles className="h-3 w-3 shrink-0 text-accent" aria-hidden="true" />
            <span className="truncate">{run.title}</span>
          </Link>
        </li>
      ))}
      {more > 0 && <li className="text-[11px] text-ink-muted">+{more} more</li>}
    </ul>
  );
};
