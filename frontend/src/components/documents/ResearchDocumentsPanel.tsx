import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Globe, Library, Plus, ShieldCheck } from 'lucide-react';
import { Document } from '../../types/document';
import { DiscoveryScope } from '../../types/discovery';
import { DocumentLibrary } from '../../hooks/useDocumentLibrary';
import { isDocumentPending } from '../../services/documents.service';
import { SourceCard } from '../projects/SourceCard';
import { ProjectUploadModal } from '../projects/ProjectUploadModal';
import { DocumentViewer } from './DocumentViewer';
import { LibraryPickerDialog } from './LibraryPickerDialog';
import { SourceDiscoveryDialog } from './SourceDiscoveryDialog';
import { useToast } from '../../app/ToastContext';

interface ResearchDocumentsPanelProps {
  /** Every document the user has; used to show status and for the picker. */
  library: DocumentLibrary;
  attachedIds: string[];
  onChange: (ids: string[]) => void;
  onDocumentsResolved?: (docs: Document[]) => void;
  discoveryInitialQuery?: string;
  autoDiscover?: boolean;
  onAutoDiscoverChange?: (enabled: boolean) => void;
  discoveryScope?: DiscoveryScope;
  onDiscoveryScopeChange?: (scope: DiscoveryScope) => void;
  className?: string;
  /** Bump to draw attention to the panel, e.g. after a blocked Start research. */
  highlightSignal?: number;
}

const DISCOVERY_SCOPES: { id: DiscoveryScope; label: string }[] = [
  { id: 'all', label: 'All trusted' },
  { id: 'scholarly', label: 'Scholarly' },
  { id: 'web', label: 'Web' },
];

/**
 * The files one new research will read. Starts empty: upload a file, pick
 * from library, discover curated online papers/articles, or opt into auto-discovery.
 */
export const ResearchDocumentsPanel: React.FC<ResearchDocumentsPanelProps> = ({
  library,
  attachedIds,
  onChange,
  onDocumentsResolved,
  discoveryInitialQuery = '',
  autoDiscover = false,
  onAutoDiscoverChange,
  discoveryScope = 'all',
  onDiscoveryScopeChange,
  className = '',
  highlightSignal = 0,
}) => {
  const { addToast } = useToast();
  const sectionRef = useRef<HTMLElement>(null);
  const [highlighted, setHighlighted] = useState(false);

  useEffect(() => {
    if (!highlightSignal) return;
    setHighlighted(false);
    // Restart the animation on every attempt.
    const frame = window.requestAnimationFrame(() => {
      setHighlighted(true);
      sectionRef.current?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' });
    });
    const timer = window.setTimeout(() => setHighlighted(false), 2200);
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(timer);
    };
  }, [highlightSignal]);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isPickerOpen, setIsPickerOpen] = useState(false);
  const [isDiscoveryOpen, setIsDiscoveryOpen] = useState(false);
  const [viewing, setViewing] = useState<Document | null>(null);
  // Fresh uploads & imported discovery sources show straight away before library reloads.
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

  const attachMany = useCallback(
    (docs: Document[]) => {
      if (docs.length === 0) return;
      setUploaded((prev) => {
        const next = { ...prev };
        for (const doc of docs) next[doc.id] = doc;
        return next;
      });
      onDocumentsResolved?.(docs);
      const merged = [...attachedIds];
      for (const doc of docs) {
        if (!merged.includes(doc.id)) merged.push(doc.id);
      }
      onChange(merged);
      library.reload();
    },
    [attachedIds, onChange, onDocumentsResolved, library],
  );

  const handleUploaded = useCallback(
    (doc: Document) => {
      setUploaded((prev) => ({ ...prev, [doc.id]: doc }));
      onDocumentsResolved?.([doc]);
      attach(doc.id);
      library.reload();
      addToast({ type: 'success', title: 'Uploaded', description: `${doc.name} will be ready in a moment.` });
    },
    [attach, onDocumentsResolved, library, addToast],
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
      ? autoDiscover
        ? 'Will discover trusted online sources'
        : 'None added yet'
      : [ready > 0 && `${ready} ready`, preparing > 0 && `${preparing} preparing`]
          .filter(Boolean)
          .join(' · ') || `${attached.length} added`;

  const actionButton =
    'inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-line bg-panel px-2.5 text-[13px] font-medium text-ink shadow-xs transition-colors hover:bg-subtle';

  return (
    <section
      ref={sectionRef}
      aria-label="Files for this research"
      data-highlighted={highlighted || undefined}
      className={`flex min-h-0 flex-col overflow-hidden rounded-xl border border-line bg-panel shadow-xs transition-colors ${
        highlighted ? 'files-attention' : ''
      } ${className}`}
    >
      <header className="flex items-center gap-2 border-b border-line px-4 py-3">
        <div className="min-w-0 flex-1">
          <h2 className="text-[13px] font-semibold text-ink">Files to search</h2>
          <p className="mt-0.5 truncate text-xs tabular-nums text-ink-muted" aria-live="polite">
            {summary}
          </p>
        </div>
        {attached.length > 0 && (
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => setIsDiscoveryOpen(true)}
              className={actionButton}
              title="Discover curated online sources"
            >
              <Globe className="h-3.5 w-3.5" />
              Discover
            </button>
            <button type="button" onClick={() => setIsUploadOpen(true)} className={actionButton}>
              <Plus className="h-3.5 w-3.5" />
              Upload
            </button>
          </div>
        )}
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {attached.length === 0 ? (
          <div className="px-4 py-6 text-center">
            <p className="text-[13px] font-medium text-ink">Add the files to ask about</p>
            <p className="mx-auto mt-1 max-w-[250px] text-xs leading-relaxed text-ink-muted">
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
              <button type="button" onClick={() => setIsDiscoveryOpen(true)} className={actionButton}>
                <Globe className="h-3.5 w-3.5" />
                Discover
              </button>
              {library.total > 0 && (
                <button type="button" onClick={() => setIsPickerOpen(true)} className={actionButton}>
                  <Library className="h-3.5 w-3.5" />
                  Add from library
                </button>
              )}
            </div>

            {onAutoDiscoverChange && (
              <div className="mt-4 rounded-lg border border-line bg-canvas/70 p-3 text-left">
                <div className="flex items-start justify-between gap-2.5">
                  <div className="min-w-0">
                    <p className="flex items-center gap-1.5 text-xs font-medium text-ink">
                      <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-accent" />
                      <span>Trusted online discovery</span>
                    </p>
                    <p className="mt-0.5 text-[11px] leading-snug text-ink-muted">
                      Search OpenAlex, Crossref, arXiv &amp; Wikipedia if no files are added.
                    </p>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={autoDiscover}
                    aria-label="Enable trusted online discovery"
                    onClick={() => onAutoDiscoverChange(!autoDiscover)}
                    className={`relative mt-0.5 inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border transition-colors ${
                      autoDiscover
                        ? 'border-accent bg-solid'
                        : 'border-line-strong bg-subtle'
                    }`}
                  >
                    <span
                      className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow-xs transition-transform ${
                        autoDiscover ? 'translate-x-4' : 'translate-x-0.5'
                      }`}
                    />
                  </button>
                </div>

                {autoDiscover && onDiscoveryScopeChange && (
                  <div className="mt-2.5 flex items-center gap-1">
                    {DISCOVERY_SCOPES.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => onDiscoveryScopeChange(item.id)}
                        className={`rounded px-2 py-0.5 text-[11px] font-medium transition-colors ${
                          discoveryScope === item.id
                            ? 'bg-accent-soft text-accent border border-accent-line'
                            : 'text-ink-soft hover:bg-subtle hover:text-ink border border-transparent'
                        }`}
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          <div role="list" aria-label="Files for this research" className="divide-y divide-line">
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
        <Link to="/library" className="inline-flex items-center gap-1 font-medium text-ink-soft hover:text-ink">
          Open library
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
      <SourceDiscoveryDialog
        isOpen={isDiscoveryOpen}
        initialQuery={discoveryInitialQuery}
        projectId={null}
        onClose={() => setIsDiscoveryOpen(false)}
        onImported={attachMany}
      />
      {viewing && <DocumentViewer document={viewing} onClose={() => setViewing(null)} />}
    </section>
  );
};
