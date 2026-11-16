import React, { useCallback, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Library, Plus } from 'lucide-react';
import { Document } from '../../types/document';
import { DocumentLibrary } from '../../hooks/useDocumentLibrary';
import { isDocumentPending } from '../../services/documents.service';
import { SourceCard } from '../projects/SourceCard';
import { ProjectUploadModal } from '../projects/ProjectUploadModal';
import { DocumentViewer } from './DocumentViewer';
import { LibraryPickerDialog } from './LibraryPickerDialog';
import { useToast } from '../../app/ToastContext';

interface ResearchDocumentsPanelProps {
  /** Every document the user has; used to show status and for the picker. */
  library: DocumentLibrary;
  attachedIds: string[];
  onChange: (ids: string[]) => void;
  className?: string;
}

/**
 * The files one new research will read. It starts empty: upload a file or
 * pick ones you uploaded before. Other uploads are left out.
 */
export const ResearchDocumentsPanel: React.FC<ResearchDocumentsPanelProps> = ({
  library,
  attachedIds,
  onChange,
  className = '',
}) => {
  const { addToast } = useToast();
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isPickerOpen, setIsPickerOpen] = useState(false);
  const [viewing, setViewing] = useState<Document | null>(null);
  // Fresh uploads show straight away, before the library list reloads.
  const [uploaded, setUploaded] = useState<Record<string, Document>>({});

  const attached = useMemo(() => {
    const byId = new Map(library.documents.map((doc) => [doc.id, doc]));
    return attachedIds
      .map((id) => byId.get(id) ?? uploaded[id])
      .filter((doc): doc is Document => Boolean(doc));
  }, [attachedIds, library.documents, uploaded]);

  const attach = useCallback(
    (id: string) => onChange(attachedIds.includes(id) ? attachedIds : [...attachedIds, id]),
    [attachedIds, onChange],
  );

  const handleUploaded = useCallback(
    (doc: Document) => {
      setUploaded((prev) => ({ ...prev, [doc.id]: doc }));
      attach(doc.id);
      library.reload();
      addToast({ type: 'success', title: 'Uploaded', description: `${doc.name} will be ready in a moment.` });
    },
    [attach, library, addToast],
  );

  const handleDuplicate = useCallback(
    (id: string) => {
      attach(id);
      library.reload();
    },
    [attach, library],
  );

  const ready = attached.filter((doc) => doc.status === 'indexed').length;
  const preparing = attached.filter((doc) => isDocumentPending(doc)).length;
  const summary =
    attached.length === 0
      ? 'None added yet'
      : [ready > 0 && `${ready} ready`, preparing > 0 && `${preparing} preparing`]
          .filter(Boolean)
          .join(' · ') || `${attached.length} added`;

  const actionButton =
    'inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-line bg-panel px-2.5 text-[13px] font-medium text-ink shadow-xs transition-colors hover:bg-subtle';

  return (
    <section
      aria-label="Documents for this research"
      className={`flex min-h-0 flex-col overflow-hidden rounded-xl border border-line bg-panel shadow-xs ${className}`}
    >
      <header className="flex items-center gap-3 border-b border-line px-4 py-3">
        <div className="min-w-0 flex-1">
          <h2 className="text-[13px] font-semibold text-ink">Documents to search</h2>
          <p className="mt-0.5 truncate text-xs tabular-nums text-ink-muted" aria-live="polite">
            {summary}
          </p>
        </div>
        {attached.length > 0 && (
          <button type="button" onClick={() => setIsUploadOpen(true)} className={actionButton}>
            <Plus className="h-3.5 w-3.5" />
            Upload
          </button>
        )}
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {attached.length === 0 ? (
          <div className="px-4 py-7 text-center">
            <p className="text-[13px] font-medium text-ink">Add the files to ask about</p>
            <p className="mx-auto mt-1 max-w-[240px] text-xs leading-relaxed text-ink-muted">
              This research reads only the files you add here, not everything you have uploaded.
            </p>
            <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
              <button
                type="button"
                onClick={() => setIsUploadOpen(true)}
                className="inline-flex h-8 items-center gap-1.5 rounded-md bg-solid px-3 text-[13px] font-medium text-on-solid shadow-xs hover:bg-solid-hover"
              >
                <Plus className="h-3.5 w-3.5" />
                Upload
              </button>
              {library.total > 0 && (
                <button type="button" onClick={() => setIsPickerOpen(true)} className={actionButton}>
                  <Library className="h-3.5 w-3.5" />
                  Add from library
                </button>
              )}
            </div>
          </div>
        ) : (
          <div role="list" aria-label="Documents for this research" className="divide-y divide-line">
            {attached.map((doc) => (
              <div key={doc.id} role="listitem">
                <SourceCard
                  compact
                  document={doc}
                  onOpen={setViewing}
                  onRemove={(id) => onChange(attachedIds.filter((item) => item !== id))}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      <footer className="flex items-center justify-between gap-3 border-t border-line px-4 py-2.5 text-xs">
        {attached.length > 0 && library.total > 0 ? (
          <button
            type="button"
            onClick={() => setIsPickerOpen(true)}
            className="inline-flex items-center gap-1 font-medium text-ink-soft hover:text-ink"
          >
            <Library className="h-3 w-3" />
            Add from library
          </button>
        ) : (
          <span />
        )}
        <Link to="/documents" className="inline-flex items-center gap-1 font-medium text-ink-soft hover:text-ink">
          All documents
          <ArrowRight className="h-3 w-3" />
        </Link>
      </footer>

      <ProjectUploadModal
        isOpen={isUploadOpen}
        projectId={null}
        onClose={() => setIsUploadOpen(false)}
        onUploaded={handleUploaded}
        onDuplicate={handleDuplicate}
      />
      <LibraryPickerDialog
        isOpen={isPickerOpen}
        library={library}
        attachedIds={attachedIds}
        onClose={() => setIsPickerOpen(false)}
        onApply={onChange}
      />
      {viewing && <DocumentViewer document={viewing} onClose={() => setViewing(null)} />}
    </section>
  );
};
