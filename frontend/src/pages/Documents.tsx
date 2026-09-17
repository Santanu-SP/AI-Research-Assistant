import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { TopBar } from '../components/layout/TopBar';
import { DocumentRow } from '../components/documents/DocumentRow';
import { UploadDocumentModal } from '../components/documents/UploadDocumentModal';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';
import { PrimaryButton } from '../components/common/PrimaryButton';
import { CenteredLoadingState } from '../components/common/LoadingState';
import { documentsService } from '../services/documents.service';
import { Document } from '../types/document';
import { Search, Upload, FolderUp } from 'lucide-react';

export const DocumentsPage: React.FC = () => {
  const navigate = useNavigate();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [totalDocuments, setTotalDocuments] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedFormat, setSelectedFormat] = useState('all');
  const [selectedStatus, setSelectedStatus] = useState('all');
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => {
      loadDocuments();
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery, selectedFormat, selectedStatus, retryKey]);

  const loadDocuments = async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const response = await documentsService.getDocuments({
        search: searchQuery || undefined,
        status: selectedStatus !== 'all' ? selectedStatus : undefined,
        type: selectedFormat !== 'all' ? selectedFormat : undefined,
      });
      setDocuments(response.items);
      setTotalDocuments(response.total);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : 'Failed to load documents');
      setDocuments([]);
      setTotalDocuments(0);
    } finally {
      setIsLoading(false);
    }
  };

  const handleUploadFile = async (file: File) => {
    await documentsService.uploadDocument(file);
    await loadDocuments();
  };

  const handleDeleteDocument = async (id: string) => {
    await documentsService.deleteDocument(id);
    await loadDocuments();
  };

  const handleUseInResearch = () => {
    // Navigate to new research with document pre-selected or referenced
    navigate('/research/new');
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
                <option value="DOCX">DOCX</option>
                <option value="TXT">TXT</option>
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
          ) : (
            <div className="flex flex-col gap-2.5">
              {documents.map((doc) => (
                <DocumentRow
                  key={doc.id}
                  document={doc}
                  onDelete={handleDeleteDocument}
                  onUseInResearch={handleUseInResearch}
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
    </div>
  );
};
