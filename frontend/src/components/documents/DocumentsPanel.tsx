import React, { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Plus } from 'lucide-react';
import { Document } from '../../types/document';
import { DocumentLibrary } from '../../hooks/useDocumentLibrary';
import { useDocumentActions } from '../../hooks/useDocumentActions';
import { SourceCard } from '../projects/SourceCard';
import { ProjectUploadModal } from '../projects/ProjectUploadModal';
import { DocumentViewer } from './DocumentViewer';
import { useToast } from '../../app/ToastContext';

interface DocumentsPanelProps {
  library: DocumentLibrary;
  /** Upload target. Without one, uploads go to the user's general documents. */
  projectId?: string | null;
  /** Link to the full list, e.g. a project's Documents tab. */
  manageHref?: string;
  readOnly?: boolean;
  title?: string;
  description?: string;
  className?: string;
}

/**
 * Compact list of the documents a question can draw on, shown next to the
 * place where questions are asked.
 */
export const DocumentsPanel: React.FC<DocumentsPanelProps> = ({
  library,
  projectId,
  manageHref,
  readOnly = false,
  title = 'Documents',
  description,
  className = '',
}) => {
  const { addToast } = useToast();
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const { documents, total, isLoading, error, readyCount, preparingCount, refreshPaused, reload } = library;
  const actions = useDocumentActions(reload);

  const handleUploaded = useCallback(
    (doc: Document) => {
      reload();
      addToast({ type: 'success', title: 'Uploaded', description: `${doc.name} will be ready in a moment.` });
    },
    [reload, addToast],
  );

  const summary =
    total === 0
      ? 'No documents yet'
      : [readyCount > 0 && `${readyCount} ready`, preparingCount > 0 && `${preparingCount} preparing`]
          .filter(Boolean)
          .join(' · ') || `${total} document${total === 1 ? '' : 's'}`;

  return (
    <section
      aria-label={title}
      className={`flex min-h-0 flex-col overflow-hidden rounded-xl border border-line bg-panel shadow-xs ${className}`}
    >
      <header className="flex items-center gap-3 border-b border-line px-4 py-3">
        <div className="min-w-0 flex-1">
          <h2 className="text-[13px] font-semibold text-ink">{title}</h2>
          <p className="mt-0.5 truncate text-xs tabular-nums text-ink-muted" aria-live="polite">
            {isLoading ? 'Loading…' : summary}
          </p>
        </div>
        {!readOnly && (
          <button
            type="button"
            onClick={() => setIsUploadOpen(true)}
            className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-line bg-panel px-2.5 text-[13px] font-medium text-ink shadow-xs transition-colors hover:bg-subtle"
          >
            <Plus className="h-3.5 w-3.5" />
            Upload
          </button>
        )}
      </header>

      {description && <p className="border-b border-line px-4 py-2.5 text-xs leading-relaxed text-ink-muted">{description}</p>}

      <div className="min-h-0 flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="space-y-1 p-3" aria-hidden="true">
            {[0, 1, 2].map((i) => (
              <div key={i} className="flex items-center gap-3 px-1 py-1.5">
                <span className="doc-skeleton h-8 w-7 rounded-md" />
                <span className="flex-1 space-y-1.5">
                  <span className="doc-skeleton block h-2.5 w-3/4 rounded" />
                  <span className="doc-skeleton block h-2 w-1/3 rounded" />
                </span>
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="px-4 py-6 text-center">
            <p className="text-[13px] text-ink-soft">Your documents couldn’t be loaded.</p>
            <button type="button" onClick={reload} className="mt-2 text-[13px] font-medium text-accent hover:underline">
              Try again
            </button>
          </div>
        ) : documents.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <p className="text-[13px] font-medium text-ink">Add a paper to get started</p>
            <p className="mx-auto mt-1 max-w-[240px] text-xs leading-relaxed text-ink-muted">
              Answers are drawn only from the documents listed here.
            </p>
            {!readOnly && (
              <button
                type="button"
                onClick={() => setIsUploadOpen(true)}
                className="mt-3 inline-flex h-8 items-center gap-1.5 rounded-md bg-solid px-3 text-[13px] font-medium text-on-solid shadow-xs hover:bg-solid-hover"
              >
                <Plus className="h-3.5 w-3.5" />
                Upload a document
              </button>
            )}
          </div>
        ) : (
          <div role="list" aria-label={title} className="divide-y divide-line">
            {documents.map((doc) => (
              <div key={doc.id} role="listitem">
                <SourceCard
                  compact
                  document={doc}
                  onOpen={actions.open}
                  onDelete={readOnly ? undefined : actions.remove}
                  onRetry={readOnly ? undefined : actions.retry}
                  isRetrying={actions.retryingId === doc.id}
                  isDeleting={actions.deletingId === doc.id}
                  isArchived={readOnly}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {(refreshPaused || (manageHref && total > 0)) && (
        <footer className="flex items-center justify-between gap-3 border-t border-line px-4 py-2.5 text-xs">
          {refreshPaused ? (
            <button type="button" onClick={reload} className="font-medium text-ink-soft hover:text-ink">
              Refresh
            </button>
          ) : (
            <span />
          )}
          {manageHref && total > 0 && (
            <Link to={manageHref} className="inline-flex items-center gap-1 font-medium text-ink-soft hover:text-ink">
              Manage documents
              <ArrowRight className="h-3 w-3" />
            </Link>
          )}
        </footer>
      )}

      <ProjectUploadModal
        isOpen={isUploadOpen}
        projectId={projectId}
        onClose={() => setIsUploadOpen(false)}
        onUploaded={handleUploaded}
      />
      {actions.viewing && <DocumentViewer document={actions.viewing} onClose={actions.close} />}
    </section>
  );
};
