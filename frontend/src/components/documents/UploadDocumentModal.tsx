import React, { useEffect, useState, useRef } from 'react';
import { X, UploadCloud, Check, AlertCircle, Link2, BookOpen } from 'lucide-react';
import { PrimaryButton } from '../common/PrimaryButton';
import { apiErrorMessage } from '../../services/api';

interface UploadDocumentModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUploadFile: (file: File) => Promise<void>;
  onAddUrl: (url: string) => Promise<void>;
  onAddDoi: (doi: string) => Promise<void>;
  projectSelected: boolean;
}

export const UploadDocumentModal: React.FC<UploadDocumentModalProps> = ({
  isOpen,
  onClose,
  onUploadFile,
  onAddUrl,
  onAddDoi,
  projectSelected,
}) => {
  const [mode, setMode] = useState<'file' | 'url' | 'doi'>('file');
  const [sourceValue, setSourceValue] = useState('');
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
    const validExtensions = ['pdf', 'docx', 'pptx', 'html', 'htm', 'md', 'markdown'];
    const ext = file.name.split('.').pop()?.toLowerCase();

    if (!ext || !validExtensions.includes(ext)) {
      setUploadError('Choose a PDF, DOCX, PPTX, HTML, or Markdown document.');
      setSelectedFile(null);
      return;
    }

    setUploadError(null);
    setSelectedFile(file);
  };

  const handleSubmit = async () => {
    if (isUploading) return;
    if (mode === 'file' && !selectedFile) return;
    if (mode !== 'file' && (!projectSelected || !sourceValue.trim())) return;
    setIsUploading(true);
    try {
      if (mode === 'file' && selectedFile) await onUploadFile(selectedFile);
      if (mode === 'url') await onAddUrl(sourceValue.trim());
      if (mode === 'doi') await onAddDoi(sourceValue.trim());
      setSelectedFile(null);
      setSourceValue('');
      setIsUploading(false);
      onClose();
    } catch (error) {
      setUploadError(apiErrorMessage(error, 'Failed to upload document. Please try again.'));
      setIsUploading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs"
      onMouseDown={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="upload-document-title"
        className="w-full max-w-lg bg-white rounded-xl shadow-xl border border-[#e5e7e4] overflow-hidden animate-in fade-in zoom-in-95 duration-150"
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-[#e5e7e4] flex items-center justify-between">
          <div>
            <h3 id="upload-document-title" className="font-semibold text-base text-[#181a18]">
              Add research source
            </h3>
            <p className="text-xs text-[#6b706c] mt-0.5">
              Add a local file, research webpage, or scholarly DOI.
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

        {/* Modal Body */}
        <div className="p-6">
          <div className="mb-4 grid grid-cols-3 rounded-lg border border-[#e5e7e4] bg-[#fafaf8] p-1">
            {(['file', 'url', 'doi'] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => { setMode(value); setUploadError(null); }}
                className={`rounded-md px-3 py-2 text-xs font-medium capitalize ${mode === value ? 'bg-white text-[#163328] shadow-sm' : 'text-[#6b706c]'}`}
              >
                {value}
              </button>
            ))}
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.pptx,.html,.htm,.md,.markdown"
            onChange={handleFileChange}
            className="hidden"
          />

          {mode === 'file' ? <div
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
            aria-label="Choose a supported research document"
            className={`border-2 border-dashed rounded-xl p-8 flex flex-col items-center justify-center text-center cursor-pointer transition-all duration-150 ${
              dragOver
                ? 'border-[#163328] bg-[#f1f6f3]/60 scale-[1.01]'
                : selectedFile
                ? 'border-[#163328]/40 bg-[#f1f6f3]/30'
                : 'border-[#d0d7d2] hover:border-[#163328]/50 hover:bg-[#fafaf8]'
            }`}
          >
            <div className="w-12 h-12 rounded-full bg-[#f1f6f3] text-[#163328] flex items-center justify-center mb-3">
              <UploadCloud className="w-6 h-6 stroke-[1.75]" />
            </div>

            {selectedFile ? (
              <div>
                <span className="font-semibold text-sm text-[#181a18] block mb-1">
                  {selectedFile.name}
                </span>
                <span className="text-xs text-[#6b706c]">
                  {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB · Ready to add
                </span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedFile(null);
                  }}
                  className="mt-2 text-xs text-[#b91c1c] underline block mx-auto"
                >
                  Choose a different file
                </button>
              </div>
            ) : (
              <div>
                <span className="font-medium text-sm text-[#181a18] block mb-1">
                  Click to browse or drag and drop document
                </span>
                <p className="text-xs text-[#929792] max-w-xs">
                  PDF, DOCX, PPTX, HTML, or Markdown
                </p>
              </div>
            )}
          </div> : (
            <div className="rounded-xl border border-[#d0d7d2] bg-[#fafaf8] p-5">
              <div className="mb-3 flex items-center gap-2 text-[#163328]">
                {mode === 'url' ? <Link2 className="h-5 w-5" /> : <BookOpen className="h-5 w-5" />}
                <span className="text-sm font-semibold">{mode === 'url' ? 'Research URL' : 'DOI lookup'}</span>
              </div>
              <input
                type={mode === 'url' ? 'url' : 'text'}
                value={sourceValue}
                onChange={(event) => setSourceValue(event.target.value)}
                disabled={!projectSelected}
                placeholder={mode === 'url' ? 'https://example.org/research' : '10.1000/example'}
                aria-label={mode === 'url' ? 'Research source URL' : 'Digital object identifier'}
                className="w-full rounded-md border border-[#d0d7d2] bg-white px-3 py-2.5 text-sm text-[#181a18] focus:border-[#163328] focus:outline-none focus:ring-1 focus:ring-[#163328] disabled:bg-[#f1f1ee]"
              />
              {!projectSelected && <p className="mt-2 text-xs text-[#b45309]">Select a research project before adding URL or DOI sources.</p>}
            </div>
          )}

          {/* Error notice */}
          {uploadError && (
            <div className="mt-3 flex items-center gap-2 text-xs text-[#b91c1c] bg-[#fee2e2]/50 p-2.5 rounded-lg border border-[#fecaca]">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{uploadError}</span>
            </div>
          )}

          {/* Information badge */}
          <div className="mt-4 p-3 bg-[#fafaf8] border border-[#e5e7e4] rounded-lg text-xs text-[#6b706c] flex items-start gap-2">
            <Check className="w-4 h-4 text-[#163328] shrink-0 mt-0.5" />
            <div>
              <span className="font-medium text-[#181a18]">Source integrity:</span>{' '}
              URLs are security checked and DOI records show whether evidence is full text, abstract, or metadata only.
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3.5 bg-[#fafaf8] border-t border-[#e5e7e4] flex items-center justify-end gap-2.5">
          <button
            type="button"
            onClick={onClose}
            className="text-xs font-medium text-[#6b706c] hover:text-[#181a18] px-3.5 py-2 rounded-md hover:bg-white transition-colors"
          >
            Cancel
          </button>

          <PrimaryButton
            onClick={handleSubmit}
            disabled={isUploading || (mode === 'file' ? !selectedFile : !projectSelected || !sourceValue.trim())}
            isLoading={isUploading}
          >
            {isUploading ? 'Adding source…' : mode === 'file' ? 'Upload file' : mode === 'url' ? 'Add URL' : 'Resolve DOI'}
          </PrimaryButton>
        </div>
      </div>
    </div>
  );
};
