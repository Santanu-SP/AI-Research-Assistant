import React, { useCallback, useState, useEffect } from 'react';
import { TopBar } from '../components/layout/TopBar';
import { DocumentRow } from '../components/documents/DocumentRow';
import { UploadDocumentModal } from '../components/documents/UploadDocumentModal';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';
import { PrimaryButton } from '../components/common/PrimaryButton';
import { PageHeader } from '../components/common/PageHeader';
import { LoadingState } from '../components/common/LoadingState';
import { documentsService, getDocumentErrorMessage } from '../services/documents.service';
import { activeIngestionKey, useBackoffPolling } from '../hooks/useBackoffPolling';
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
  const [retryingId, setRetryingId] = useState<string | null>(null);

  const loadDocuments = useCallback(async (silent = false) => {
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
  }, [searchQuery, selectedFormat, selectedStatus]);

  useEffect(() => {
    const timer = setTimeout(() => {
      void loadDocuments();
    }, 300);
    return () => clearTimeout(timer);
  }, [loadDocuments, retryKey]);

  // Poll with backoff while any document is still being ingested.
  const pendingKey = activeIngestionKey(documents);
  const refreshSilently = useCallback(() => loadDocuments(true), [loadDocuments]);
  const { timedOut: pollingStopped } = useBackoffPolling(
    pendingKey !== '',
    refreshSilently,
    pendingKey,
  );

  const handleRetryDocument = async (id: string) => {
    setRetryingId(id);
    try {
      await documentsService.retryDocument(id);
      setActionError(null);
      await loadDocuments(true);
    } catch (error) {
      setActionError(getDocumentErrorMessage(error, 'Could not retry this document.'));
    } finally {
      setRetryingId(null);
    }
  };

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
    <div className="min-h-screen flex flex-col">
      <TopBar
        breadcrumbs={<span className="font-medium text-ink">Documents</span>}
      />

      <main className="flex-1 px-4 pb-16 pt-14 sm:px-6 lg:px-10">
        <div className="mx-auto max-w-5xl py-8 sm:py-10">
          <PageHeader
            title="Documents"
            description="Every PDF and DOCX you have uploaded, across all projects. Only indexed documents are searched."
            actions={
              <PrimaryButton onClick={() => setIsUploadOpen(true)}>
                <Upload className="h-4 w-4" />
                Upload
              </PrimaryButton>
            }
          />

          <div className="mb-4 mt-8 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative w-full sm:max-w-xs">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" />
              <input
                type="search"
                aria-label="Search documents"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search by file name or title"
                className="field h-9 pl-9 text-[13px]"
              />
            </div>

            <div className="flex items-center gap-2">
              <select
                aria-label="Filter documents by type"
                value={selectedFormat}
                onChange={(e) => setSelectedFormat(e.target.value)}
                className="field h-9 w-auto pr-8 text-[13px]"
              >
                <option value="all">All formats</option>
                <option value="pdf">PDF</option>
                <option value="docx">DOCX</option>
              </select>

              <select
                aria-label="Filter documents by status"
                value={selectedStatus}
                onChange={(e) => setSelectedStatus(e.target.value)}
                className="field h-9 w-auto pr-8 text-[13px]"
              >
                <option value="all">All statuses</option>
                <option value="uploaded">Uploaded</option>
                <option value="processing">Processing</option>
                <option value="indexed">Indexed</option>
                <option value="failed">Failed</option>
              </select>
            </div>
          </div>

          {actionError && <p role="alert" className="mb-3 rounded-md border border-danger-line bg-danger-soft p-3 text-xs text-danger">{actionError}</p>}
          {pollingStopped && (
            <p role="status" className="mb-3 text-xs text-warning">
              Some documents are taking longer than expected. Automatic refresh has paused.{' '}
              <button type="button" onClick={() => setRetryKey((k) => k + 1)} className="underline font-medium">
                Refresh now
              </button>
            </p>
          )}
          {isLoading ? (
            <LoadingState rows={4} />
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
              description="Try a different search term, format or status."
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
              description="Upload PDF or DOCX papers. They are parsed and indexed in the background, then included in your questions."
              primaryActionLabel="Upload documents"
              onPrimaryAction={() => setIsUploadOpen(true)}
            />
          ) : (
            <div className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-panel shadow-xs">
              {documents.map((doc) => (
                <DocumentRow
                  key={doc.id}
                  document={doc}
                  onDelete={handleDeleteDocument}
                  onOpen={setSelectedDocument}
                  onRetry={handleRetryDocument}
                  isRetrying={retryingId === doc.id}
                />
              ))}
            </div>
          )}

          {!isLoading && !loadError && totalDocuments > 0 && (
            <div className="mt-3 text-right text-xs tabular-nums text-ink-muted">
              {documents.length} of {totalDocuments} documents
            </div>
          )}
        </div>
      </main>

      <UploadDocumentModal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        onUploadFile={handleUploadFile}
      />
      {selectedDocument && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 overlay-enter" onMouseDown={() => setSelectedDocument(null)}>
          <div role="dialog" aria-modal="true" aria-labelledby="document-details-title" className="dialog-enter w-full max-w-md overflow-hidden rounded-xl border border-line bg-panel shadow-xl" onMouseDown={(event) => event.stopPropagation()}>
            <div className="border-b border-line px-6 py-4">
              <p className="eyebrow">Document</p>
              <h2 id="document-details-title" className="mt-1 text-base font-semibold leading-snug text-ink">{selectedDocument.title || selectedDocument.name}</h2>
            </div>
            <dl className="grid grid-cols-[96px_minmax(0,1fr)] gap-x-4 gap-y-2.5 px-6 py-5 text-[13px]">
              <dt className="text-ink-muted">File</dt><dd className="truncate text-ink">{selectedDocument.name}</dd>
              <dt className="text-ink-muted">Status</dt><dd className="capitalize text-ink">{selectedDocument.status}</dd>
              <dt className="text-ink-muted">Pages</dt><dd className="tabular-nums text-ink">{selectedDocument.pageCount ?? 'Unavailable'}</dd>
              <dt className="text-ink-muted">Chunks</dt><dd className="tabular-nums text-ink">{selectedDocument.chunkCount}</dd>
              {selectedDocument.doi && <><dt className="text-ink-muted">DOI</dt><dd className="truncate font-mono text-xs text-ink">{selectedDocument.doi}</dd></>}
            </dl>
            <div className="flex items-center justify-end gap-2 border-t border-line bg-subtle/50 px-6 py-3">
              <button type="button" onClick={() => setSelectedDocument(null)} className="inline-flex h-9 items-center rounded-md px-3.5 text-[13px] font-medium text-ink-soft hover:bg-subtle hover:text-ink">Close</button>
              <a href={`${API_BASE_URL}/documents/${selectedDocument.id}/file`} target="_blank" rel="noopener noreferrer" className="inline-flex h-9 items-center rounded-md bg-solid px-3.5 text-[13px] font-medium text-on-solid shadow-xs hover:bg-solid-hover">Open document</a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
