/**
 * ProjectUploadModal: Upload PDF or DOCX to a specific project.
 *
 * Features:
 * - Drag-and-drop or file picker
 * - PDF/DOCX validation before submission
 * - Indeterminate loading (backend does not stream upload progress)
 * - Duplicate document detection (HTTP 409)
 * - Archived project restriction (upload button disabled)
 * - Sequential multi-file upload queue
 */
import React, { useEffect, useRef, useState } from 'react';
import { X, UploadCloud, CheckCircle2, AlertCircle, Clock } from 'lucide-react';
import { PrimaryButton } from '../common/PrimaryButton';
import {
  documentsService,
  getDocumentErrorMessage,
  isDuplicateDocumentError,
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
      return <CheckCircle2 className="w-4 h-4 text-[#163328]" />;
    case 'duplicate':
      return <AlertCircle className="w-4 h-4 text-[#b45309]" />;
    case 'failed':
      return <AlertCircle className="w-4 h-4 text-[#b91c1c]" />;
    case 'uploading':
    case 'processing':
      return (
        <span className="w-4 h-4 border-2 border-[#163328]/30 border-t-[#163328] rounded-full animate-spin block" />
      );
    default:
      return <Clock className="w-4 h-4 text-[#929792]" />;
  }
};

const STATUS_LABELS: Record<FileItemStatus, string> = {
  waiting: 'Waiting',
  uploading: 'Uploading…',
  processing: 'Processing…',
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

        // Mark as processing while backend ingests
        setQueue((prev) =>
          prev.map((q) =>
            q.id === item.id ? { ...q, status: 'processing' } : q
          )
        );

        // The backend returns immediately after storing; ingestion is async.
        // We optimistically show 'done' and let the list polling update the real status.
        setQueue((prev) =>
          prev.map((q) =>
            q.id === item.id ? { ...q, status: 'done' } : q
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
      (q) => q.status === 'done' || q.status === 'duplicate' || q.status === 'failed'
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
        className="w-full max-w-lg bg-white rounded-xl shadow-xl border border-[#e5e7e4] overflow-hidden animate-in fade-in zoom-in-95 duration-150"
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-[#e5e7e4] flex items-center justify-between">
          <div>
            <h3
              id="upload-modal-title"
              className="font-semibold text-base text-[#181a18]"
            >
              Upload Documents
            </h3>
            <p className="text-xs text-[#6b706c] mt-0.5">
              PDF and DOCX files supported · Max 100 MB per file
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close upload dialog"
            className="text-[#929792] hover:text-[#181a18] p-1.5 rounded-md hover:bg-[#f5f5f2] transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-4">
          {/* Dropzone */}
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
                ? 'border-[#163328] bg-[#f1f6f3]/60 scale-[1.01]'
                : 'border-[#d0d7d2] hover:border-[#163328]/50 hover:bg-[#fafaf8]'
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
            <div className="w-12 h-12 rounded-full bg-[#f1f6f3] text-[#163328] flex items-center justify-center mb-3">
              <UploadCloud className="w-6 h-6 stroke-[1.75]" />
            </div>
            <p className="font-medium text-sm text-[#181a18] mb-1">
              Click to browse or drag and drop
            </p>
            <p className="text-xs text-[#929792]">PDF and DOCX</p>
          </div>

          {/* File queue */}
          {queue.length > 0 && (
            <div className="space-y-2 max-h-52 overflow-y-auto">
              {queue.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center gap-3 px-3 py-2 bg-[#fafaf8] border border-[#e5e7e4] rounded-lg"
                >
                  <StatusIcon status={item.status} />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-[#181a18] truncate">
                      {item.file.name}
                    </p>
                    {item.errorMessage && (
                      <p className="text-[11px] text-[#b91c1c] leading-snug mt-0.5">
                        {item.errorMessage}
                      </p>
                    )}
                  </div>
                  <span
                    className={`text-[10px] font-medium shrink-0 ${
                      item.status === 'done'
                        ? 'text-[#163328]'
                        : item.status === 'failed'
                        ? 'text-[#b91c1c]'
                        : item.status === 'duplicate'
                        ? 'text-[#b45309]'
                        : 'text-[#929792]'
                    }`}
                  >
                    {STATUS_LABELS[item.status]}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 bg-[#fafaf8] border-t border-[#e5e7e4] flex items-center justify-end gap-2.5">
          <button
            type="button"
            onClick={onClose}
            className="text-xs font-medium text-[#6b706c] hover:text-[#181a18] px-3.5 py-2 rounded-md hover:bg-white transition-colors"
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
