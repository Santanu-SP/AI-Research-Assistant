import React, { useCallback, useEffect, useRef, useState } from 'react';
import { X, UploadCloud, CheckCircle2, AlertCircle, Clock, Link2 } from 'lucide-react';
import { PrimaryButton } from '../common/PrimaryButton';
import {
  documentsService,
  getDocumentErrorMessage,
  isDuplicateDocumentError,
  duplicateDocumentIdFromError,
  isDocumentPending,
} from '../../services/documents.service';
import { ingestionStep } from '../../lib/ingestionProgress';
import { Document } from '../../types/document';
import { useToast } from '../../app/ToastContext';
import { useSessionDataCache } from '../../app/SessionDataCacheContext';

type FileItemStatus =
  | 'waiting'
  | 'uploading'
  | 'processing'
  | 'done'
  | 'duplicate'
  | 'failed';

interface QueuedItem {
  id: string;
  label: string;
  file?: File;
  documentId?: string;
  status: FileItemStatus;
  errorMessage?: string;
  /** The server's current step while the file is being prepared. */
  stepLabel?: string;
}

interface ProjectUploadModalProps {
  isOpen: boolean;
  /** Uploads into this project; without one the file joins the user's general documents. */
  projectId?: string | null;
  onClose: () => void;
  onUploaded: (document: Document) => void;
  /** Called with the existing copy's id when a file or URL was already uploaded. */
  onDuplicate?: (documentId: string) => void;
}

const ALLOWED_EXTENSIONS = [
  'pdf',
  'docx',
  'pptx',
  'xlsx',
  'html',
  'htm',
  'mp3',
  'wav',
  'm4a',
  'ogg',
  'flac',
  'mp4',
  'mov',
  'mkv',
  'webm',
  'png',
  'jpg',
  'jpeg',
  'webp',
  'tiff',
  'tif',
];
const MAX_SIZE_BYTES = 25 * 1024 * 1024; // Matches backend DOCUMENT_MAX_UPLOAD_BYTES default (25 MB)
const POLL_INTERVAL_MS = 1500;

let fileIdCounter = 0;

const validateFile = (
  file: File
): { valid: boolean; error?: string } => {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return {
      valid: false,
      error: `Unsupported format. Supported: PDF, DOCX, PPTX, XLSX, HTML, Audio, Video, and Images (got .${ext || 'unknown'}).`,
    };
  }
  if (file.size > MAX_SIZE_BYTES) {
    return { valid: false, error: 'File exceeds 25 MB upload limit.' };
  }
  return { valid: true };
};

const isValidPublicHttpUrl = (raw: string): boolean => {
  try {
    const parsed = new URL(raw.trim());
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
};

const mapServerDocumentStatus = (
  doc: Pick<Document, 'status' | 'processingError'>
): { status: FileItemStatus; errorMessage?: string } => {
  if (doc.status === 'failed') {
    return {
      status: 'failed',
      errorMessage: doc.processingError || 'Couldn’t process this file.',
    };
  }
  if (isDocumentPending(doc)) {
    return { status: 'processing' };
  }
  return { status: 'done' };
};

const StatusIcon: React.FC<{ status: FileItemStatus }> = ({ status }) => {
  switch (status) {
    case 'done':
      return <CheckCircle2 className="w-4 h-4 text-accent" />;
    case 'duplicate':
      return <AlertCircle className="w-4 h-4 text-warning" />;
    case 'failed':
      return <AlertCircle className="w-4 h-4 text-danger" />;
    case 'uploading':
    case 'processing':
      return (
        <span className="w-4 h-4 border-2 border-accent/30 border-t-accent rounded-full animate-spin block" />
      );
    default:
      return <Clock className="w-4 h-4 text-ink-muted" />;
  }
};

const STATUS_LABELS: Record<FileItemStatus, string> = {
  waiting: 'Waiting',
  uploading: 'Uploading…',
  processing: 'Preparing…',
  done: 'Ready',
  duplicate: 'Already added',
  failed: 'Couldn’t upload',
};

export const ProjectUploadModal: React.FC<ProjectUploadModalProps> = ({
  isOpen,
  projectId,
  onClose,
  onUploaded,
  onDuplicate,
}) => {
  const { addToast } = useToast();
  const cache = useSessionDataCache();
  const [mode, setMode] = useState<'files' | 'url'>('files');
  const [dragOver, setDragOver] = useState(false);
  const [queue, setQueue] = useState<QueuedItem[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [urlInput, setUrlInput] = useState('');
  const [urlTitle, setUrlTitle] = useState('');
  const [isAddingUrl, setIsAddingUrl] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setMode('files');
      setQueue([]);
      setIsRunning(false);
      setUrlInput('');
      setUrlTitle('');
      setIsAddingUrl(false);
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isRunning && !isAddingUrl) onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isOpen, isRunning, isAddingUrl, onClose]);

  const applyResolvedDocuments = useCallback(
    (resolvedById: Map<string, Document>) => {
      if (resolvedById.size === 0) return;
      let anyFinished = false;
      setQueue((prev) =>
        prev.map((item) => {
          if (item.status !== 'processing' || !item.documentId) return item;
          const fresh = resolvedById.get(item.documentId);
          if (!fresh) return item;
          if (isDocumentPending(fresh)) {
            const stepLabel = ingestionStep(fresh).label;
            return stepLabel === item.stepLabel ? item : { ...item, stepLabel };
          }
          anyFinished = true;
          const mapped = mapServerDocumentStatus(fresh);
          return {
            ...item,
            status: mapped.status,
            errorMessage: mapped.errorMessage,
          };
        })
      );
      if (anyFinished) {
        cache?.markDocumentsStale();
      }
    },
    [cache]
  );

  // Sync queued items while open so "Preparing…" transitions cleanly to "Ready" or "Couldn't upload".
  const pendingDocumentIds = queue
    .filter((item) => item.status === 'processing' && item.documentId)
    .map((item) => item.documentId as string);
  const pendingKey = pendingDocumentIds.join(',');

  useEffect(() => {
    if (!isOpen || !pendingKey) return;
    const ids = pendingKey.split(',').filter(Boolean);
    let cancelled = false;

    const syncFromCache = () => {
      if (!cache) return;
      const scopeKey = projectId ? `p:${projectId}::` : 'all::';
      const entry = cache.getDocuments(scopeKey);
      if (!entry) return;
      const map = new Map(entry.documents.map((d) => [d.id, d]));
      applyResolvedDocuments(map);
    };

    syncFromCache();
    const unsub = cache?.subscribeDocuments(syncFromCache);

    const pollOnce = async () => {
      if (typeof documentsService.getDocument !== 'function') return;
      const settled = await Promise.allSettled(
        ids.map((id) => documentsService.getDocument(id))
      );
      if (cancelled) return;
      const resolved = new Map<string, Document>();
      for (const res of settled) {
        if (res.status === 'fulfilled') {
          resolved.set(res.value.id, res.value);
        }
      }
      applyResolvedDocuments(resolved);
    };

    const timer = window.setInterval(() => {
      void pollOnce();
    }, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
      unsub?.();
    };
  }, [isOpen, pendingKey, projectId, cache, applyResolvedDocuments]);

  if (!isOpen) return null;

  const addFiles = (files: FileList | File[]) => {
    const newItems: QueuedItem[] = [];
    for (const file of Array.from(files)) {
      const { valid, error } = validateFile(file);
      newItems.push({
        id: `file-${++fileIdCounter}`,
        label: file.name,
        file,
        status: valid ? 'waiting' : 'failed',
        errorMessage: error,
      });
    }
    setQueue((prev) => [...prev, ...newItems]);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.length) addFiles(e.target.files);
    e.target.value = '';
  };

  const handleUploadResult = (
    itemId: string,
    label: string,
    action: () => Promise<Document>,
    duplicateNotice: (existingId: string | null) => string
  ) =>
    action()
      .then((doc) => {
        const mapped = mapServerDocumentStatus(doc);
        setQueue((prev) =>
          prev.map((q) =>
            q.id === itemId
              ? {
                  ...q,
                  documentId: doc.id,
                  status: mapped.status,
                  errorMessage: mapped.errorMessage,
                }
              : q
          )
        );
        onUploaded(doc);
      })
      .catch((err: unknown) => {
        if (isDuplicateDocumentError(err)) {
          const existingId = duplicateDocumentIdFromError(err);
          if (existingId && onDuplicate) onDuplicate(existingId);
          setQueue((prev) =>
            prev.map((q) =>
              q.id === itemId
                ? {
                    ...q,
                    status: 'duplicate',
                    errorMessage: duplicateNotice(existingId),
                  }
                : q
            )
          );
          addToast({
            type: 'warning',
            title: 'Already added',
            description:
              existingId && onDuplicate
                ? `“${label}” is already in your library, so that copy will be used.`
                : `“${label}” is already ${projectId ? 'in this project' : 'in your library'}.`,
          });
        } else {
          const msg = getDocumentErrorMessage(err, 'Upload failed.');
          setQueue((prev) =>
            prev.map((q) =>
              q.id === itemId
                ? { ...q, status: 'failed', errorMessage: msg }
                : q
            )
          );
          addToast({ type: 'error', title: 'Upload failed', description: msg });
        }
      });

  const runQueue = async () => {
    setIsRunning(true);
    const waiting = queue.filter((q) => q.status === 'waiting' && q.file);

    for (const item of waiting) {
      const file = item.file!;
      setQueue((prev) =>
        prev.map((q) =>
          q.id === item.id ? { ...q, status: 'uploading' } : q
        )
      );

      await handleUploadResult(
        item.id,
        file.name,
        () =>
          projectId
            ? documentsService.uploadProjectDocument(projectId, file)
            : documentsService.uploadDocument(file),
        () =>
          projectId
            ? 'This file is already in this project.'
            : 'This file is already in your library.'
      );
    }

    setIsRunning(false);
  };

  const handleAddUrl = async (e: React.FormEvent) => {
    e.preventDefault();
    const rawUrl = urlInput.trim();
    if (!isValidPublicHttpUrl(rawUrl)) {
      addToast({
        type: 'error',
        title: 'Invalid URL',
        description: 'Enter a valid http:// or https:// website or YouTube link.',
      });
      return;
    }
    const label = urlTitle.trim() || rawUrl;
    const itemId = `url-${++fileIdCounter}`;
    setIsAddingUrl(true);
    setQueue((prev) => [
      ...prev,
      { id: itemId, label, status: 'uploading' },
    ]);
    await handleUploadResult(
      itemId,
      label,
      () => documentsService.addUrlDocument(rawUrl, urlTitle.trim() || undefined, projectId),
      () =>
        projectId
          ? 'This URL is already in this project.'
          : 'This URL is already in your library.'
    );
    setUrlInput('');
    setUrlTitle('');
    setIsAddingUrl(false);
  };

  const waitingCount = queue.filter((q) => q.status === 'waiting').length;
  const allDone =
    queue.length > 0 &&
    queue.every(
      (q) =>
        q.status === 'done' ||
        q.status === 'processing' ||
        q.status === 'duplicate' ||
        q.status === 'failed'
    );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 overlay-enter"
      onMouseDown={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="upload-modal-title"
        className="w-full max-w-lg bg-panel rounded-xl shadow-xl border border-line overflow-hidden dialog-enter"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-4 border-b border-line flex items-center justify-between">
          <div>
            <h3
              id="upload-modal-title"
              className="font-semibold text-base text-ink"
            >
              Upload files
            </h3>
            <p className="text-xs text-ink-soft mt-0.5">
              Documents, slides, sheets, HTML, audio, video, images (up to 25 MB), or web &amp; YouTube links.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close upload dialog"
            className="text-ink-muted hover:text-ink p-1.5 rounded-md hover:bg-subtle transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-6 pt-4">
          <div className="inline-flex rounded-lg border border-line bg-canvas p-0.5 text-xs font-medium">
            <button
              type="button"
              onClick={() => setMode('files')}
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 transition-colors ${
                mode === 'files'
                  ? 'bg-panel text-ink shadow-xs'
                  : 'text-ink-soft hover:text-ink'
              }`}
            >
              <UploadCloud className="h-3.5 w-3.5" />
              Files
            </button>
            <button
              type="button"
              onClick={() => setMode('url')}
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 transition-colors ${
                mode === 'url'
                  ? 'bg-panel text-ink shadow-xs'
                  : 'text-ink-soft hover:text-ink'
              }`}
            >
              <Link2 className="h-3.5 w-3.5" />
              Web / YouTube URL
            </button>
          </div>
        </div>

        <div className="p-6 space-y-4">
          {mode === 'files' ? (
            <div
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={(e) => { e.preventDefault(); setDragOver(false); }}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  fileInputRef.current?.click();
                }
              }}
              role="button"
              tabIndex={0}
              aria-label="Choose files to upload"
              className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed px-6 py-8 text-center transition-colors duration-150 ${
                dragOver
                  ? 'border-accent bg-accent-soft'
                  : 'border-line-strong bg-subtle/40 hover:border-ink-muted hover:bg-subtle'
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.pptx,.xlsx,.html,.htm,.mp3,.wav,.m4a,.ogg,.flac,.mp4,.mov,.mkv,.webm,.png,.jpg,.jpeg,.webp,.tiff,.tif"
                multiple
                onChange={handleFileChange}
                className="hidden"
              />
              <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg border border-line bg-panel text-ink-soft shadow-xs">
                <UploadCloud className="h-5 w-5" strokeWidth={1.75} />
              </div>
              <p className="font-medium text-sm text-ink mb-1">
                Drop files here or click to browse
              </p>
              <p className="text-xs text-ink-muted">
                PDF, Word, Slides, Sheets, HTML, Audio (MP3, WAV, M4A, OGG, FLAC), Video (MP4, MOV, MKV, WEBM) &amp; Images
              </p>
            </div>
          ) : (
            <form onSubmit={(e) => void handleAddUrl(e)} className="space-y-3">
              <div>
                <label htmlFor="source-url-input" className="block text-xs font-medium text-ink mb-1">
                  Website or YouTube URL
                </label>
                <input
                  id="source-url-input"
                  type="url"
                  required
                  value={urlInput}
                  onChange={(e) => setUrlInput(e.target.value)}
                  placeholder="https://www.youtube.com/watch?v=... or https://example.com/article"
                  className="field h-9 w-full text-[13px]"
                />
              </div>
              <div>
                <label htmlFor="source-url-title" className="block text-xs font-medium text-ink mb-1">
                  Optional title
                </label>
                <input
                  id="source-url-title"
                  type="text"
                  maxLength={500}
                  value={urlTitle}
                  onChange={(e) => setUrlTitle(e.target.value)}
                  placeholder="Leave blank to detect title automatically"
                  className="field h-9 w-full text-[13px]"
                />
              </div>
              <PrimaryButton
                type="submit"
                disabled={!urlInput.trim() || isAddingUrl}
                isLoading={isAddingUrl}
              >
                {isAddingUrl ? 'Adding link…' : 'Add URL source'}
              </PrimaryButton>
            </form>
          )}

          {queue.length > 0 && (
            <div className="space-y-2 max-h-52 overflow-y-auto">
              {queue.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center gap-3 px-3 py-2 bg-canvas border border-line rounded-lg"
                >
                  <StatusIcon status={item.status} />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-ink truncate">
                      {item.label}
                    </p>
                    {item.errorMessage && (
                      <p className="text-[11px] text-danger leading-snug mt-0.5">
                        {item.errorMessage}
                      </p>
                    )}
                  </div>
                  <span
                    className={`text-[10px] font-medium shrink-0 ${
                      item.status === 'done'
                        ? 'text-accent'
                        : item.status === 'failed'
                        ? 'text-danger'
                        : item.status === 'duplicate'
                        ? 'text-warning'
                        : 'text-ink-muted'
                    }`}
                  >
                    {item.status === 'processing' && item.stepLabel ? item.stepLabel : STATUS_LABELS[item.status]}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="px-6 py-3.5 bg-canvas border-t border-line flex items-center justify-end gap-2.5">
          <button
            type="button"
            onClick={onClose}
            className="text-xs font-medium text-ink-soft hover:text-ink px-3.5 py-2 rounded-md hover:bg-panel transition-colors"
          >
            {allDone ? 'Done' : 'Cancel'}
          </button>
          {mode === 'files' && !allDone && (
            <PrimaryButton
              onClick={() => void runQueue()}
              disabled={waitingCount === 0 || isRunning}
              isLoading={isRunning}
            >
              {isRunning
                ? 'Uploading…'
                : `Upload ${waitingCount} file${waitingCount !== 1 ? 's' : ''}`}
            </PrimaryButton>
          )}
        </div>
      </div>
    </div>
  );
};
