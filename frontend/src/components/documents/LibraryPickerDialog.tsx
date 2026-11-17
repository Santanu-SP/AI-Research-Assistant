import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Check, Search, X } from 'lucide-react';
import { Document } from '../../types/document';
import { DocumentLibrary } from '../../hooks/useDocumentLibrary';
import { isDocumentPending } from '../../services/documents.service';

interface LibraryPickerDialogProps {
  isOpen: boolean;
  library: DocumentLibrary;
  /** Already attached; shown as picked. */
  attachedIds: string[];
  onClose: () => void;
  /** Called with the full new set of picked document ids. */
  onApply: (ids: string[]) => void;
}

const stateLabel = (doc: Document): string | null => {
  if (doc.status === 'failed') return 'Couldn’t process';
  if (isDocumentPending(doc)) return 'Preparing…';
  return null;
};

/**
 * Pick files you already uploaded for one research. Picking here doesn't
 * copy or move anything; it only says which files this research may read.
 */
export const LibraryPickerDialog: React.FC<LibraryPickerDialogProps> = ({
  isOpen,
  library,
  attachedIds,
  onClose,
  onApply,
}) => {
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [term, setTerm] = useState('');
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    setPicked(new Set(attachedIds));
    setTerm('');
    window.setTimeout(() => searchRef.current?.focus(), 0);
    // Only reset when the dialog opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isOpen, onClose]);

  const visible = useMemo(() => {
    const needle = term.trim().toLowerCase();
    if (!needle) return library.documents;
    return library.documents.filter((doc) =>
      `${doc.title ?? ''} ${doc.name}`.toLowerCase().includes(needle),
    );
  }, [library.documents, term]);

  if (!isOpen) return null;

  const toggle = (id: string) =>
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const changed =
    picked.size !== attachedIds.length || attachedIds.some((id) => !picked.has(id));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 overlay-enter" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="library-picker-title"
        className="flex max-h-[min(640px,calc(100vh-2rem))] w-full max-w-lg flex-col overflow-hidden rounded-xl border border-line bg-panel shadow-xl dialog-enter"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-line px-6 py-4">
          <div>
            <h3 id="library-picker-title" className="text-base font-semibold text-ink">
              Add from your library
            </h3>
            <p className="mt-0.5 text-xs text-ink-soft">Pick the files this research should read.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close library"
            className="rounded-md p-1.5 text-ink-muted transition-colors hover:bg-subtle hover:text-ink"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="border-b border-line px-6 py-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-muted" />
            <input
              ref={searchRef}
              type="search"
              aria-label="Search your library"
              value={term}
              onChange={(event) => setTerm(event.target.value)}
              placeholder="Search your library"
              className="h-8 w-full rounded-md border border-line bg-canvas pl-8 pr-3 text-[13px] text-ink placeholder:text-ink-muted transition-colors focus:border-accent-line focus:bg-panel focus:outline-none [&::-webkit-search-cancel-button]:hidden"
            />
          </div>
        </div>

        <div className="min-h-[160px] flex-1 overflow-y-auto">
          {library.isLoading ? (
            <p className="px-6 py-8 text-center text-[13px] text-ink-muted">Loading…</p>
          ) : library.documents.length === 0 ? (
            <p className="px-6 py-8 text-center text-[13px] text-ink-muted">
              Nothing uploaded yet. Use Upload to add a file.
            </p>
          ) : visible.length === 0 ? (
            <p className="px-6 py-8 text-center text-[13px] text-ink-muted">No files match “{term}”.</p>
          ) : (
            <ul aria-label="Your files" className="divide-y divide-line">
              {visible.map((doc) => {
                const isPicked = picked.has(doc.id);
                const note = stateLabel(doc);
                const disabled = doc.status === 'failed' && !isPicked;
                return (
                  <li key={doc.id}>
                    <label
                      className={`flex items-center gap-3 px-6 py-2.5 transition-colors ${
                        disabled ? 'opacity-60' : 'hover:bg-subtle/60'
                      }`}
                    >
                      <input
                        type="checkbox"
                        className="peer sr-only"
                        checked={isPicked}
                        disabled={disabled}
                        onChange={() => toggle(doc.id)}
                      />
                      <span
                        aria-hidden="true"
                        className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-accent ${
                          isPicked ? 'border-solid bg-solid text-on-solid' : 'border-line-strong bg-panel'
                        }`}
                      >
                        {isPicked && <Check className="h-3 w-3" strokeWidth={2.5} />}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] font-medium text-ink">{doc.title || doc.name}</span>
                        <span className="mt-0.5 block truncate text-xs text-ink-muted">
                          {[doc.type?.toUpperCase(), doc.projectId ? 'In a project' : null, note]
                            .filter(Boolean)
                            .join(' · ')}
                        </span>
                      </span>
                    </label>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-line px-6 py-3">
          <span className="text-xs tabular-nums text-ink-muted" aria-live="polite">
            {picked.size === 0 ? 'None picked' : `${picked.size} picked`}
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-8 items-center rounded-md px-3 text-[13px] font-medium text-ink-soft transition-colors hover:bg-subtle hover:text-ink"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={!changed}
              onClick={() => {
                onApply(Array.from(picked));
                onClose();
              }}
              className="inline-flex h-8 items-center rounded-md bg-solid px-3 text-[13px] font-medium text-on-solid shadow-xs transition-colors hover:bg-solid-hover disabled:opacity-50"
            >
              Use these
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
