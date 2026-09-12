import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { TopBar } from '../components/layout/TopBar';
import { DocumentRow } from '../components/documents/DocumentRow';
import { UploadDocumentModal } from '../components/documents/UploadDocumentModal';
import { EmptyState } from '../components/common/EmptyState';
import { PrimaryButton } from '../components/common/PrimaryButton';
import { documentsService } from '../services/documents.service';
import { Document } from '../types/document';
import { Search, Upload, FolderUp } from 'lucide-react';

export const DocumentsPage: React.FC = () => {
  const navigate = useNavigate();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedFormat, setSelectedFormat] = useState('all');
  const [selectedStatus, setSelectedStatus] = useState('all');
  const [isUploadOpen, setIsUploadOpen] = useState(false);

  useEffect(() => {
    loadDocuments();
  }, []);

  const loadDocuments = async () => {
    const list = await documentsService.getDocuments();
    setDocuments(list);
  };

  const handleUploadFile = async (file: File) => {
    await documentsService.uploadDocument(file);
    await loadDocuments();
  };

  const handleDeleteDocument = async (id: string) => {
    await documentsService.deleteDocument(id);
    await loadDocuments();
  };

  const handleRetryDocument = async (id: string) => {
    await documentsService.retryDocument(id);
    await loadDocuments();
  };

  const handleUseInResearch = () => {
    // Navigate to new research with document pre-selected or referenced
    navigate('/research/new');
  };

  const filtered = documents.filter((doc) => {
    const matchesSearch =
      doc.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (doc.notes && doc.notes.toLowerCase().includes(searchQuery.toLowerCase()));

    const matchesFormat =
      selectedFormat === 'all' || doc.type === selectedFormat;

    const matchesStatus =
      selectedStatus === 'all' || doc.status === selectedStatus;

    return matchesSearch && matchesFormat && matchesStatus;
  });

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
                <option value="ready">Ready</option>
                <option value="processing">Processing</option>
                <option value="failed">Failed</option>
              </select>
            </div>
          </div>

          {/* Document Rows List */}
          {documents.length === 0 ? (
            <EmptyState
              icon={FolderUp}
              title="No documents yet"
              description="Upload documents to include your own material in research."
              primaryActionLabel="Upload documents"
              onPrimaryAction={() => setIsUploadOpen(true)}
            />
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={FolderUp}
              title="No documents in workspace"
              description="Upload PDF, DOCX, or text files to enrich future research investigations with internal evidence."
              primaryActionLabel="Upload first document"
              onPrimaryAction={() => setIsUploadOpen(true)}
            />
          ) : (
            <div className="flex flex-col gap-2.5">
              {filtered.map((doc) => (
                <DocumentRow
                  key={doc.id}
                  document={doc}
                  onDelete={handleDeleteDocument}
                  onRetry={handleRetryDocument}
                  onUseInResearch={handleUseInResearch}
                />
              ))}
            </div>
          )}

          <div className="mt-3 text-right text-xs text-[#929792]">
            Showing {filtered.length} of {documents.length} documents
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
