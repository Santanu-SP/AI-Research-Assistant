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
import { documentsService, getDocumentErrorMessage } from '../../services/documents.service';
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
  const [retryingId, setRetryingId] = useState<string | null>(null);

  const params = {
    search: searchQuery.trim() || undefined,
    status: statusFilter !== 'all' ? statusFilter : undefined,
  };

  const { documents, total, isLoading, error, pollingStopped, reload } = useProjectDocuments(
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

  const handleRetry = useCallback(
    async (id: string) => {
      setRetryingId(id);
      try {
        await documentsService.retryDocument(id);
        reload();
        addToast({ type: 'success', title: 'Processing restarted' });
      } catch (err) {
        addToast({
          type: 'error',
          title: 'Retry failed',
          description: getDocumentErrorMessage(err, 'Could not retry this document.'),
        });
      } finally {
        setRetryingId(null);
      }
    },
    [reload, addToast]
  );

  const hasFilters = Boolean(searchQuery) || statusFilter !== 'all';

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative w-full sm:max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" />
          <input
            type="search"
            aria-label="Search documents"
            id="sources-search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search documents"
            className="field h-9 pl-9 pr-8 text-[13px]"
          />
          {searchQuery && (
            <button
              type="button"
              aria-label="Clear search"
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-muted hover:text-ink"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        <select
          aria-label="Filter by ingestion status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="field h-9 w-auto pr-8 text-[13px]"
        >
          <option value="all">All statuses</option>
          <option value="uploaded">Uploaded</option>
          <option value="processing">Processing</option>
          <option value="indexed">Indexed</option>
          <option value="failed">Failed</option>
        </select>

        {!isArchived && (
          <PrimaryButton
            id="upload-document-btn"
            onClick={() => setIsUploadOpen(true)}
            className="sm:ml-auto"
          >
            <Upload className="h-4 w-4" />
            Upload
          </PrimaryButton>
        )}
      </div>

      {!isLoading && !error && (
        <p className="text-xs tabular-nums text-ink-muted">
          {total} document{total !== 1 ? 's' : ''}
          {hasFilters && ' matching filters'}
        </p>
      )}

      {pollingStopped && (
        <p role="status" className="text-xs text-warning">
          Some documents are taking longer than expected. Automatic refresh has
          paused.{' '}
          <button type="button" onClick={reload} className="underline font-medium">
            Refresh now
          </button>
        </p>
      )}

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
              : 'Upload PDF or DOCX papers. Questions in this project will only search these documents.'
          }
          primaryActionLabel={isArchived ? undefined : 'Upload document'}
          onPrimaryAction={isArchived ? undefined : () => setIsUploadOpen(true)}
        />
      ) : (
        <div
          role="list"
          aria-label="Project documents"
          className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-panel shadow-xs"
        >
          {documents.map((doc) => (
            <div key={doc.id} role="listitem">
              <SourceCard
                document={doc}
                onDelete={!isArchived ? handleDelete : undefined}
                onRetry={!isArchived ? handleRetry : undefined}
                isRetrying={retryingId === doc.id}
                isArchived={isArchived}
              />
              {isDeletingId === doc.id && (
                <p className="px-5 pb-3 text-xs text-ink-muted">
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
