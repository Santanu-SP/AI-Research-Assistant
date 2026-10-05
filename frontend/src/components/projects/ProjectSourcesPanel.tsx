/**
 * ProjectSourcesPanel: Displays and manages documents for a project.
 *
 * - Lists project-scoped documents from /api/v1/projects/{id}/documents
 * - Supports search filter (wired to backend) and status filter (local)
 * - Upload button (disabled for archived projects)
 * - Polling for ingestion status updates
 * - Empty state, loading skeleton, error retry
 */
import React, { useCallback, useState } from 'react';
import {
  Upload,
  Search,
  FolderUp,
  X,
} from 'lucide-react';
import { ResearchProject } from '../../types/project';
import { Document } from '../../types/document';
import { SourceCard } from './SourceCard';
import { ProjectUploadModal } from './ProjectUploadModal';
import { EmptyState } from '../common/EmptyState';
import { ErrorState } from '../common/ErrorState';
import { LoadingState } from '../common/LoadingState';
import { PrimaryButton } from '../common/PrimaryButton';
import { useProjectDocuments } from '../../hooks/useProjectDocuments';
import { documentsService } from '../../services/documents.service';
import { useToast } from '../../app/ToastContext';

interface ProjectSourcesPanelProps {
  project: ResearchProject;
  isArchived: boolean;
}

export const ProjectSourcesPanel: React.FC<ProjectSourcesPanelProps> = ({
  project,
  isArchived,
}) => {
  const { addToast } = useToast();
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isDeletingId, setIsDeletingId] = useState<string | null>(null);

  const params = {
    search: searchQuery.trim() || undefined,
    status: statusFilter !== 'all' ? statusFilter : undefined,
  };

  const { documents, total, isLoading, error, reload } = useProjectDocuments(
    project.id,
    params
  );

  const handleUploaded = useCallback(
    (doc: Document) => {
      reload();
      addToast({
        type: 'success',
        title: 'Document uploaded',
        description: doc.name,
      });
    },
    [reload, addToast]
  );

  const handleDelete = useCallback(
    async (id: string) => {
      if (
        !window.confirm(
          'Delete this document? This action cannot be undone.'
        )
      )
        return;

      setIsDeletingId(id);
      try {
        await documentsService.deleteDocument(id);
        reload();
        addToast({ type: 'success', title: 'Document deleted' });
      } catch {
        addToast({
          type: 'error',
          title: 'Delete failed',
          description: 'Could not delete the document. Please try again.',
        });
      } finally {
        setIsDeletingId(null);
      }
    },
    [reload, addToast]
  );

  const hasFilters = Boolean(searchQuery) || statusFilter !== 'all';

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Search */}
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-[#929792] absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            aria-label="Search documents"
            id="sources-search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search documents…"
            className="w-full bg-white border border-[#e5e7e4] rounded-lg pl-9 pr-8 py-2 text-xs text-[#181a18] placeholder:text-[#929792] focus:outline-none focus:ring-1 focus:ring-[#163328] focus:border-[#163328] transition-colors"
          />
          {searchQuery && (
            <button
              type="button"
              aria-label="Clear search"
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#929792] hover:text-[#181a18]"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Status filter */}
        <select
          aria-label="Filter by ingestion status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="bg-white border border-[#e5e7e4] text-[#6b706c] text-xs rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-[#163328]"
        >
          <option value="all">All statuses</option>
          <option value="uploaded">Uploaded</option>
          <option value="processing">Processing</option>
          <option value="indexed">Indexed</option>
          <option value="failed">Failed</option>
        </select>

        {/* Upload button */}
        {!isArchived && (
          <PrimaryButton
            id="upload-document-btn"
            onClick={() => setIsUploadOpen(true)}
            className="gap-1.5 shrink-0"
          >
            <Upload className="w-3.5 h-3.5" />
            <span>Upload</span>
          </PrimaryButton>
        )}
      </div>

      {/* Document count */}
      {!isLoading && !error && (
        <p className="text-xs text-[#929792]">
          {total} document{total !== 1 ? 's' : ''}
          {hasFilters && ' matching filters'}
        </p>
      )}

      {/* Content */}
      {isLoading ? (
        <LoadingState rows={3} />
      ) : error ? (
        <ErrorState
          title="Could not load documents"
          message={error}
          onRetry={reload}
        />
      ) : documents.length === 0 && hasFilters ? (
        <EmptyState
          icon={FolderUp}
          title="No documents match filters"
          description="Try clearing your search or status filter."
          primaryActionLabel="Clear filters"
          onPrimaryAction={() => {
            setSearchQuery('');
            setStatusFilter('all');
          }}
        />
      ) : documents.length === 0 ? (
        <EmptyState
          icon={FolderUp}
          title="No documents yet"
          description={
            isArchived
              ? 'This project is archived. Documents cannot be added.'
              : 'Upload PDF or DOCX documents to include them in project research.'
          }
          primaryActionLabel={isArchived ? undefined : 'Upload document'}
          onPrimaryAction={isArchived ? undefined : () => setIsUploadOpen(true)}
        />
      ) : (
        <div
          role="list"
          aria-label="Project documents"
          className="space-y-3"
        >
          {documents.map((doc) => (
            <div key={doc.id} role="listitem">
              <SourceCard
                document={doc}
                onDelete={!isArchived ? handleDelete : undefined}
                isArchived={isArchived}
              />
              {isDeletingId === doc.id && (
                <p className="text-xs text-[#929792] mt-1 pl-1">
                  Deleting…
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      <ProjectUploadModal
        isOpen={isUploadOpen}
        projectId={project.id}
        onClose={() => setIsUploadOpen(false)}
        onUploaded={handleUploaded}
      />
    </div>
  );
};
