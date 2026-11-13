import React, { useEffect, useRef, useState } from 'react';
import { X, UploadCloud, CheckCircle2, AlertCircle, Clock } from 'lucide-react';
import { PrimaryButton } from '../common/PrimaryButton';
import {
  documentsService,
  getDocumentErrorMessage,
  isDuplicateDocumentError,
  isDocumentPending,
} from '../../services/documents.service';
import { Document } from '../../types/document';
import { useToast } from '../../app/ToastContext';

type FileItemStatus =
  | 'waiting'
  | 'uploading'
  | 'processing'
  | 'done'
  | 'duplicate'
  | 'failed';

interface QueuedFile {
  id: string;
  file: File;
  status: FileItemStatus;
  errorMessage?: string;
}

interface ProjectUploadModalProps {
  isOpen: boolean;
  /** Uploads into this project; without one the file joins the user's general documents. */
  projectId?: string | null;
  onClose: () => void;
  onUploaded: (document: Document) => void;
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
  'png',
  'jpg',
  'jpeg',
];
const MAX_SIZE_BYTES = 100 * 1024 * 1024; // 100 MB

let fileIdCounter = 0;

const validateFile = (
  file: File
): { valid: boolean; error?: string } => {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return {
      valid: false,
      error: `Unsupported format. Supported: PDF, DOCX, PPTX, XLSX, HTML, Audio (MP3, WAV, M4A, OGG, FLAC), Video (MP4) (got .${ext || 'unknown'}).`,
    };
  }
  if (file.size > MAX_SIZE_BYTES) {
    return { valid: false, error: 'File exceeds 100 MB limit.' };
  }
  return { valid: true };
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
}) => {
  const { addToast } = useToast();
  const [dragOver, setDragOver] = useState(false);
  const [queue, setQueue] = useState<QueuedFile[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Reset on open
  useEffect(() => {
    if (isOpen) {
      setQueue([]);
      setIsRunning(false);
    }
  }, [isOpen]);

  // Escape key
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isRunning) onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isOpen, isRunning, onClose]);

  if (!isOpen) return null;

  const addFiles = (files: FileList | File[]) => {
    const newItems: QueuedFile[] = [];
    for (const file of Array.from(files)) {
      const { valid, error } = validateFile(file);
      newItems.push({
        id: `file-${++fileIdCounter}`,
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
    // Reset input so re-selecting same file works
    e.target.value = '';
  };

  const runQueue = async () => {
    setIsRunning(true);
    const waiting = queue.filter((q) => q.status === 'waiting');

    for (const item of waiting) {
      setQueue((prev) =>
        prev.map((q) =>
          q.id === item.id ? { ...q, status: 'uploading' } : q
        )
      );

      try {
        const doc = projectId
          ? await documentsService.uploadProjectDocument(projectId, item.file)
          : await documentsService.uploadDocument(item.file);

        // A 202 response means the file is stored and queued for the worker;
        // the sources list keeps polling until it is indexed or fails.
        const nextStatus: FileItemStatus = isDocumentPending(doc)
          ? 'processing'
          : doc.status === 'failed'
            ? 'failed'
            : 'done';
        setQueue((prev) =>
          prev.map((q) =>
            q.id === item.id
              ? {
                  ...q,
                  status: nextStatus,
                  errorMessage:
                    nextStatus === 'failed'
                      ? 'Couldn’t process this file.'
                      : undefined,
                }
              : q
          )
        );
        onUploaded(doc);
      } catch (err) {
        if (isDuplicateDocumentError(err)) {
          setQueue((prev) =>
            prev.map((q) =>
              q.id === item.id
                ? {
                    ...q,
                    status: 'duplicate',
                    errorMessage: projectId
                      ? 'This file is already in this project.'
                      : 'This file is already in your documents.',
                  }
                : q
            )
          );
          addToast({
            type: 'warning',
            title: 'Already added',
            description: `“${item.file.name}” is already ${projectId ? 'in this project' : 'in your documents'}.`,
          });
        } else {
          const msg = getDocumentErrorMessage(err, 'Upload failed.');
          setQueue((prev) =>
            prev.map((q) =>
              q.id === item.id
                ? { ...q, status: 'failed', errorMessage: msg }
                : q
            )
          );
          addToast({ type: 'error', title: 'Upload failed', description: msg });
        }
      }
    }

    setIsRunning(false);
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
              Upload documents
            </h3>
            <p className="text-xs text-ink-soft mt-0.5">
              PDF or DOCX, up to 100 MB each. Files are ready to use a moment after upload.
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

        <div className="p-6 space-y-4">
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
            aria-label="Choose research documents or media files"
            className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed px-6 py-8 text-center transition-colors duration-150 ${
              dragOver
                ? 'border-accent bg-accent-soft'
                : 'border-line-strong bg-subtle/40 hover:border-ink-muted hover:bg-subtle'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.pptx,.xlsx,.html,.htm,.mp3,.wav,.m4a,.ogg,.flac,.mp4,.png,.jpg,.jpeg"
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
            <p className="text-xs text-ink-muted">PDF, Word, Slides, Sheets, HTML, Audio (MP3, WAV, M4A) & Video</p>
          </div>

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
                      {item.file.name}
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
                    {STATUS_LABELS[item.status]}
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
          {!allDone && (
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
