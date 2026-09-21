import React, { useState, useEffect } from 'react';
import { TopBar } from '../components/layout/TopBar';
import { DocumentRow } from '../components/documents/DocumentRow';
import { UploadDocumentModal } from '../components/documents/UploadDocumentModal';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';
import { PrimaryButton } from '../components/common/PrimaryButton';
import { CenteredLoadingState } from '../components/common/LoadingState';
import { documentsService } from '../services/documents.service';
import { Document } from '../types/document';
import { apiErrorMessage } from '../services/api';
import { API_BASE_URL } from '../services/api';
import { Search, Upload, FolderUp } from 'lucide-react';

export const DocumentsPage: React.FC = () => {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [totalDocuments, setTotalDocuments] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedFormat, setSelectedFormat] = useState('all');
  const [selectedStatus, setSelectedStatus] = useState('all');
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [selectedDocument, setSelectedDocument] = useState<Document | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      loadDocuments();
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery, selectedFormat, selectedStatus, retryKey]);

  const loadDocuments = async (silent = false) => {
    if (!silent) {
      setIsLoading(true);
      setLoadError(null);
    }
    try {
      const response = await documentsService.getDocuments({
        search: searchQuery || undefined,
        status: selectedStatus !== 'all' ? selectedStatus : undefined,
        type: selectedFormat !== 'all' ? selectedFormat : undefined,
      });
      setDocuments(response.items);
      setTotalDocuments(response.total);
    } catch (error) {
      if (!silent) {
        setLoadError(apiErrorMessage(error, 'Failed to load documents. Please try again.'));
        setDocuments([]);
        setTotalDocuments(0);
      }
    } finally {
      if (!silent) {
        setIsLoading(false);
      }
    }
  };

  // Poll for status updates if any document is processing
  useEffect(() => {
    const hasProcessingDocs = documents.some(
      (doc) => doc.status === 'uploaded' || doc.status === 'processing'
    );

    if (!hasProcessingDocs) return;

    const intervalId = setInterval(() => {
      loadDocuments(true);
    }, 4000);

    return () => clearInterval(intervalId);
  }, [documents, searchQuery, selectedFormat, selectedStatus]);

  const handleUploadFile = async (file: File) => {
    try {
      await documentsService.uploadDocument(file);
      setActionError(null);
    } finally {
      await loadDocuments();
    }
  };

  const handleDeleteDocument = async (id: string) => {
    if (!window.confirm('Are you sure you want to delete this document? This action cannot be undone.')) {
      return;
    }
    
    setIsLoading(true);
    try {
      await documentsService.deleteDocument(id);
      setActionError(null);
      await loadDocuments();
    } catch (error) {
      setActionError(apiErrorMessage(error, 'Failed to delete document. Please try again.'));
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#fafaf8] flex flex-col">
      {/* TopBar */}
      <TopBar
        breadcrumbs={
          <div className="flex items-center gap-2">
            <span className="text-[#6b706c]">Research</span>
            <span className="text-[#929792]">/</span>
            <span className="text-[#181a18] font-medium">Documents</span>
          </div>
        }
      />

      {/* Main Content */}
      <main className="flex-1 pt-14 pb-16 px-4 sm:px-6">
        <div className="max-w-5xl mx-auto py-8">
          {/* Header Row */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
            <div>
              <h1 className="font-serif text-2xl sm:text-3xl text-[#181a18] font-normal tracking-tight">
                Documents
              </h1>
              <p className="text-xs sm:text-sm text-[#6b706c] mt-1">
                Internal whitepapers, empirical benchmarks, and uploaded datasets available for cross-synthesis.
              </p>
            </div>

            <PrimaryButton
              onClick={() => setIsUploadOpen(true)}
              className="gap-1.5"
            >
              <Upload className="w-3.5 h-3.5" />
              <span>Upload document</span>
            </PrimaryButton>
          </div>

          {/* Filter / Search Bar */}
          <div className="p-3 bg-white border border-[#e5e7e4] rounded-xl mb-6 flex flex-wrap items-center justify-between gap-3 shadow-xs">
            <div className="relative flex-1 min-w-[240px]">
              <Search className="w-4 h-4 text-[#929792] absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                aria-label="Search documents"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search documents by name or keyword…"
                className="w-full bg-[#fafaf8] border border-[#e5e7e4] rounded-md pl-9 pr-3 py-1.5 text-xs text-[#181a18] placeholder:text-[#929792] focus:outline-none focus:ring-1 focus:ring-[#163328] focus:border-[#163328] transition-colors"
              />
            </div>

            <div className="flex items-center gap-2">
              <select
                aria-label="Filter documents by type"
                value={selectedFormat}
                onChange={(e) => setSelectedFormat(e.target.value)}
                className="bg-[#fafaf8] border border-[#e5e7e4] text-[#6b706c] hover:text-[#181a18] text-xs rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-[#163328]"
              >
                <option value="all">All formats</option>
                <option value="PDF">PDF</option>
              </select>

              <select
                aria-label="Filter documents by status"
                value={selectedStatus}
                onChange={(e) => setSelectedStatus(e.target.value)}
                className="bg-[#fafaf8] border border-[#e5e7e4] text-[#6b706c] hover:text-[#181a18] text-xs rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-[#163328]"
              >
                <option value="all">All statuses</option>
                <option value="uploaded">Uploaded</option>
                <option value="processing">Processing</option>
                <option value="indexed">Indexed</option>
                <option value="failed">Failed</option>
              </select>
            </div>
          </div>

          {/* Document Rows List */}
          {actionError && <p role="alert" className="mb-3 rounded-md border border-[#fecaca] bg-[#fee2e2]/50 p-3 text-xs text-[#b91c1c]">{actionError}</p>}
          {isLoading ? (
            <CenteredLoadingState label="Loading workspace documents…" />
          ) : loadError ? (
            <ErrorState
              title="Failed to load documents"
              message={loadError}
              onRetry={() => setRetryKey((prev) => prev + 1)}
            />
          ) : documents.length === 0 && (searchQuery || selectedFormat !== 'all' || selectedStatus !== 'all') ? (
            <EmptyState
              icon={FolderUp}
              title="No documents found"
              description="Adjust your filters or search query to find documents."
              primaryActionLabel="Clear filters"
              onPrimaryAction={() => {
                setSearchQuery('');
                setSelectedFormat('all');
                setSelectedStatus('all');
              }}
            />
          ) : documents.length === 0 ? (
            <EmptyState
              icon={FolderUp}
              title="No documents yet"
              description="Upload documents to include your own material in research."
              primaryActionLabel="Upload documents"
              onPrimaryAction={() => setIsUploadOpen(true)}
            />
          ) : (
            <div className="flex flex-col gap-2.5">
              {documents.map((doc) => (
                <DocumentRow
                  key={doc.id}
                  document={doc}
                  onDelete={handleDeleteDocument}
                  onOpen={setSelectedDocument}
                />
              ))}
            </div>
          )}

          <div className="mt-3 text-right text-xs text-[#929792]">
            Showing {documents.length} of {totalDocuments} documents
          </div>
        </div>
      </main>

      {/* Upload Modal */}
      <UploadDocumentModal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        onUploadFile={handleUploadFile}
      />
      {selectedDocument && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onMouseDown={() => setSelectedDocument(null)}>
        <div role="dialog" aria-modal="true" aria-labelledby="document-details-title" className="w-full max-w-md rounded-xl border border-[#e5e7e4] bg-white p-6 shadow-xl" onMouseDown={(event) => event.stopPropagation()}>
          <h2 id="document-details-title" className="font-serif text-2xl text-[#181a18]">{selectedDocument.title || selectedDocument.name}</h2>
          <dl className="mt-4 space-y-2 text-sm text-[#6b706c]">
            <div><dt className="inline font-medium text-[#181a18]">File: </dt><dd className="inline">{selectedDocument.name}</dd></div>
            <div><dt className="inline font-medium text-[#181a18]">Status: </dt><dd className="inline">{selectedDocument.status}</dd></div>
            <div><dt className="inline font-medium text-[#181a18]">Pages: </dt><dd className="inline">{selectedDocument.pageCount ?? 'Unavailable'}</dd></div>
            <div><dt className="inline font-medium text-[#181a18]">Chunks: </dt><dd className="inline">{selectedDocument.chunkCount}</dd></div>
            {selectedDocument.doi && <div><dt className="inline font-medium text-[#181a18]">DOI: </dt><dd className="inline">{selectedDocument.doi}</dd></div>}
          </dl>
          <div className="mt-6 flex items-center gap-3">
            <a href={`${API_BASE_URL}/documents/${selectedDocument.id}/file`} target="_blank" rel="noopener noreferrer" className="rounded-md bg-[#163328] px-4 py-2 text-xs font-medium text-white">Open PDF</a>
            <button type="button" onClick={() => setSelectedDocument(null)} className="rounded-md border border-[#e5e7e4] px-4 py-2 text-xs font-medium text-[#181a18]">Close</button>
          </div>
        </div>
      </div>}
    </div>
  );
};
