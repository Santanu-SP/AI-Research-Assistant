import React, { useEffect, useState, useRef } from 'react';
import { X, UploadCloud, Check, AlertCircle } from 'lucide-react';
import { PrimaryButton } from '../common/PrimaryButton';
import { apiErrorMessage } from '../../services/api';

interface UploadDocumentModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUploadFile: (file: File) => Promise<void>;
}

export const UploadDocumentModal: React.FC<UploadDocumentModalProps> = ({
  isOpen,
  onClose,
  onUploadFile,
}) => {
  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      validateAndSetFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      validateAndSetFile(e.target.files[0]);
    }
  };

  const validateAndSetFile = (file: File) => {
    const validExtensions = ['pdf', 'docx'];
    const ext = file.name.split('.').pop()?.toLowerCase();

    if (!ext || !validExtensions.includes(ext)) {
      setUploadError('Unsupported file type. Please select a PDF or DOCX document.');
      setSelectedFile(null);
      return;
    }

    setUploadError(null);
    setSelectedFile(file);
  };

  const handleSubmit = async () => {
    if (!selectedFile || isUploading) return;
    setIsUploading(true);
    try {
      await onUploadFile(selectedFile);
      setSelectedFile(null);
      setIsUploading(false);
      onClose();
    } catch (error) {
      setUploadError(apiErrorMessage(error, 'Failed to upload document. Please try again.'));
      setIsUploading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 overlay-enter"
      onMouseDown={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="upload-document-title"
        className="w-full max-w-lg bg-panel rounded-xl shadow-xl border border-line overflow-hidden dialog-enter"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-4 border-b border-line flex items-center justify-between">
          <div>
            <h3 id="upload-document-title" className="font-semibold text-base text-ink">
              Upload Knowledge Document
            </h3>
            <p className="text-xs text-ink-soft mt-0.5">
              Add internal whitepapers, memos, or empirical studies to your workspace.
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

        <div className="p-6">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx"
            onChange={handleFileChange}
            className="hidden"
          />

          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                fileInputRef.current?.click();
              }
            }}
            role="button"
            tabIndex={0}
            aria-label="Choose a PDF or DOCX document"
            className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed px-6 py-8 text-center transition-colors duration-150 ${
              dragOver
                ? 'border-accent bg-accent-soft'
                : selectedFile
                ? 'border-accent/40 bg-accent-soft/30'
                : 'border-line-strong bg-subtle/40 hover:border-ink-muted hover:bg-subtle'
            }`}
          >
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg border border-line bg-panel text-ink-soft shadow-xs">
              <UploadCloud className="h-5 w-5" strokeWidth={1.75} />
            </div>

            {selectedFile ? (
              <div>
                <span className="font-semibold text-sm text-ink block mb-1">
                  {selectedFile.name}
                </span>
                <span className="text-xs text-ink-soft">
                  {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB · Ready to add
                </span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedFile(null);
                  }}
                  className="mt-2 text-xs text-danger underline block mx-auto"
                >
                  Choose a different file
                </button>
              </div>
            ) : (
              <div>
                <span className="font-medium text-sm text-ink block mb-1">
                  Drop files here or click to browse document
                </span>
                <p className="text-xs text-ink-muted max-w-xs">
                  Supported formats: PDF and DOCX
                </p>
              </div>
            )}
          </div>

          {uploadError && (
            <div className="mt-3 flex items-center gap-2 text-xs text-danger bg-danger-soft p-2.5 rounded-lg border border-danger-line">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{uploadError}</span>
            </div>
          )}

          <div className="mt-4 p-3 bg-canvas border border-line rounded-lg text-xs text-ink-soft flex items-start gap-2">
            <Check className="w-4 h-4 text-accent shrink-0 mt-0.5" />
            <div>
              <span className="font-medium text-ink">Secure upload:</span>{' '}
              Documents are processed securely and used only for your research.
            </div>
          </div>
        </div>

        <div className="px-6 py-3.5 bg-canvas border-t border-line flex items-center justify-end gap-2.5">
          <button
            type="button"
            onClick={onClose}
            className="text-xs font-medium text-ink-soft hover:text-ink px-3.5 py-2 rounded-md hover:bg-panel transition-colors"
          >
            Cancel
          </button>

          <PrimaryButton
            onClick={handleSubmit}
            disabled={!selectedFile || isUploading}
            isLoading={isUploading}
          >
            {isUploading ? 'Adding document…' : 'Upload document'}
          </PrimaryButton>
        </div>
      </div>
    </div>
  );
};
