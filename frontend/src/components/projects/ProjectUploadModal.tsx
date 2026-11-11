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
  projectId: string;
  onClose: () => void;
  onUploaded: (document: Document) => void;
}

const ALLOWED_EXTENSIONS = ['pdf', 'docx'];
const MAX_SIZE_BYTES = 100 * 1024 * 1024; // 100 MB

let fileIdCounter = 0;

const validateFile = (
  file: File
): { valid: boolean; error?: string } => {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return {
      valid: false,
      error: `Unsupported format. Please use PDF or DOCX (got .${ext || 'unknown'}).`,
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
  processing: 'Uploaded · processing',
  done: 'Indexed',
  duplicate: 'Already exists',
  failed: 'Failed',
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
        const doc = await documentsService.uploadProjectDocument(
          projectId,
          item.file
        );

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
                      ? doc.processingError || 'Processing failed.'
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
                    errorMessage: 'This document already exists in this project.',
                  }
                : q
            )
          );
          addToast({
            type: 'warning',
            title: 'Duplicate document',
            description: `"${item.file.name}" already exists in this project.`,
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
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs"
      onMouseDown={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="upload-modal-title"
        className="w-full max-w-lg bg-panel rounded-xl shadow-xl border border-line overflow-hidden animate-in fade-in zoom-in-95 duration-150"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-4 border-b border-line flex items-center justify-between">
          <div>
            <h3
              id="upload-modal-title"
              className="font-semibold text-base text-ink"
            >
              Upload Documents
            </h3>
            <p className="text-xs text-ink-soft mt-0.5">
              PDF and DOCX files supported · Max 100 MB per file
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
            aria-label="Choose PDF or DOCX documents"
            className={`border-2 border-dashed rounded-xl p-8 flex flex-col items-center justify-center text-center cursor-pointer transition-all duration-150 ${
              dragOver
                ? 'border-accent bg-accent-soft/60 scale-[1.01]'
                : 'border-line-strong hover:border-accent/50 hover:bg-canvas'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx"
              multiple
              onChange={handleFileChange}
              className="hidden"
            />
            <div className="w-12 h-12 rounded-full bg-accent-soft text-accent flex items-center justify-center mb-3">
              <UploadCloud className="w-6 h-6 stroke-[1.75]" />
            </div>
            <p className="font-medium text-sm text-ink mb-1">
              Click to browse or drag and drop
            </p>
            <p className="text-xs text-ink-muted">PDF and DOCX</p>
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
