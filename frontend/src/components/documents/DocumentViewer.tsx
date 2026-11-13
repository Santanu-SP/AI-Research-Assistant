import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Download, ExternalLink, FileText, X } from 'lucide-react';
import { Document } from '../../types/document';
import { API_BASE_URL } from '../../services/api';

interface DocumentViewerProps {
  document: Document;
  onClose: () => void;
}

/**
 * Opens a ready document inside the app. The file endpoint refuses to be
 * framed directly, so the file is fetched once and shown from a local copy.
 */
export const DocumentViewer: React.FC<DocumentViewerProps> = ({ document: doc, onClose }) => {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);
  const isPdf = doc.type === 'pdf';
  const title = doc.title || doc.name;

  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | null = null;
    fetch(`${API_BASE_URL}/documents/${encodeURIComponent(doc.id)}/file`, {
      credentials: 'include',
      signal: controller.signal,
    })
      .then((res) => {
        if (!res.ok) throw new Error(String(res.status));
        return res.blob();
      })
      .then((blob) => {
        objectUrl = URL.createObjectURL(isPdf ? new Blob([blob], { type: 'application/pdf' }) : blob);
        setUrl(objectUrl);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [doc.id, isPdf]);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onClose();
      }
    };
    document.addEventListener('keydown', onKey, true);
    const { overflow } = document.body.style;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey, true);
      document.body.style.overflow = overflow;
    };
  }, [onClose]);

  return createPortal(
    <div className="overlay-enter fixed inset-0 z-[80] flex items-stretch justify-center bg-black/50 p-0 sm:p-6" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(event) => event.stopPropagation()}
        className="dialog-enter flex w-full max-w-5xl flex-col overflow-hidden bg-panel shadow-xl sm:rounded-xl sm:border sm:border-line"
      >
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line px-4">
          <FileText className="h-4 w-4 shrink-0 text-ink-muted" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-[14px] font-medium text-ink">{title}</p>
            {doc.title && doc.title !== doc.name && <p className="truncate text-xs text-ink-muted">{doc.name}</p>}
          </div>
          {url && (
            <a
              href={url}
              target={isPdf ? '_blank' : undefined}
              rel="noreferrer"
              download={isPdf ? undefined : doc.name}
              className="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-[13px] font-medium text-ink-soft transition-colors hover:bg-subtle hover:text-ink"
            >
              {isPdf ? <ExternalLink className="h-4 w-4" /> : <Download className="h-4 w-4" />}
              <span className="hidden sm:inline">{isPdf ? 'Open in new tab' : 'Download'}</span>
            </a>
          )}
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Close document"
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-ink-muted transition-colors hover:bg-subtle hover:text-ink"
          >
            <X className="h-[18px] w-[18px]" />
          </button>
        </header>

        <div className="relative min-h-0 flex-1 bg-sunken">
          {failed ? (
            <div className="flex h-full items-center justify-center p-6 text-center">
              <div>
                <p className="text-sm font-medium text-ink">This document couldn’t be opened.</p>
                <p className="mt-1 text-[13px] text-ink-muted">Try again in a moment.</p>
              </div>
            </div>
          ) : !url ? (
            <div className="flex h-full items-center justify-center" aria-label="Opening document">
              <span className="h-5 w-5 animate-spin rounded-full border-2 border-line-strong border-t-ink-soft" />
            </div>
          ) : isPdf ? (
            <iframe title={title} src={url} className="h-full w-full border-0" />
          ) : (
            <div className="flex h-full items-center justify-center p-6 text-center">
              <div>
                <p className="text-sm font-medium text-ink">Word documents can’t be previewed here.</p>
                <a
                  href={url}
                  download={doc.name}
                  className="mt-3 inline-flex h-9 items-center gap-2 rounded-md bg-solid px-3.5 text-[13px] font-medium text-on-solid shadow-xs hover:bg-solid-hover"
                >
                  <Download className="h-4 w-4" />
                  Download {doc.name}
                </a>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
};
