import React, { useCallback, useState } from 'react';
import { FolderUp, Search, Upload, X } from 'lucide-react';
import { ResearchProject } from '../../types/project';
import { Document } from '../../types/document';
import { SourceCard } from './SourceCard';
import { ProjectUploadModal } from './ProjectUploadModal';
import { DocumentViewer } from '../documents/DocumentViewer';
import { EmptyState } from '../common/EmptyState';
import { ErrorState } from '../common/ErrorState';
import { LoadingState } from '../common/LoadingState';
import { PrimaryButton } from '../common/PrimaryButton';
import { useDocumentLibrary } from '../../hooks/useDocumentLibrary';
import { useDocumentActions } from '../../hooks/useDocumentActions';
import { useToast } from '../../app/ToastContext';

interface ProjectSourcesPanelProps {
  project: ResearchProject;
  isArchived: boolean;
}

/** The project's Documents tab: every document that belongs to this project. */
export const ProjectSourcesPanel: React.FC<ProjectSourcesPanelProps> = ({ project, isArchived }) => {
  const { addToast } = useToast();
  const [searchQuery, setSearchQuery] = useState('');
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const { documents, total, isLoading, error, readyCount, preparingCount, refreshPaused, reload } =
    useDocumentLibrary({ projectId: project.id }, searchQuery);
  const actions = useDocumentActions(reload);
  const searching = Boolean(searchQuery.trim());

  const handleUploaded = useCallback(
    (doc: Document) => {
      reload();
      addToast({ type: 'success', title: 'Uploaded', description: `${doc.name} will be ready in a moment.` });
    },
    [reload, addToast],
  );

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
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        {!isLoading && !error && total > 0 && (
          <p className="text-xs tabular-nums text-ink-muted sm:ml-1" aria-live="polite">
            {searching
              ? `${total} match${total === 1 ? '' : 'es'}`
              : [`${total} document${total === 1 ? '' : 's'}`, preparingCount > 0 && `${preparingCount} preparing`]
                  .filter(Boolean)
                  .join(' · ')}
          </p>
        )}

        {!isArchived && (
          <PrimaryButton id="upload-document-btn" onClick={() => setIsUploadOpen(true)} className="sm:ml-auto">
            <Upload className="h-4 w-4" />
            Upload
          </PrimaryButton>
        )}
      </div>

      {isLoading ? (
        <LoadingState rows={3} />
      ) : error ? (
        <ErrorState title="Couldn’t load documents" message={error} onRetry={reload} />
      ) : documents.length === 0 && searching ? (
        <EmptyState
          icon={Search}
          title="No matching documents"
          description="Try a different search."
          primaryActionLabel="Clear search"
          onPrimaryAction={() => setSearchQuery('')}
        />
      ) : documents.length === 0 ? (
        <EmptyState
          icon={FolderUp}
          title="No documents yet"
          description={
            isArchived
              ? 'This project is archived, so documents can’t be added.'
              : 'Upload PDF or DOCX papers. Questions in this project are answered only from these documents.'
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
                onOpen={actions.open}
                onDelete={!isArchived ? actions.remove : undefined}
                onRetry={!isArchived ? actions.retry : undefined}
                isRetrying={actions.retryingId === doc.id}
                isDeleting={actions.deletingId === doc.id}
                isArchived={isArchived}
              />
            </div>
          ))}
        </div>
      )}

      {refreshPaused && (
        <p className="text-xs text-ink-muted">
          Some files are taking a little longer.{' '}
          <button type="button" onClick={reload} className="font-medium text-ink-soft underline hover:text-ink">
            Refresh
          </button>
        </p>
      )}

      {readyCount === 0 && preparingCount > 0 && !searching && (
        <p className="sr-only" role="status">
          Your documents will be ready in a moment.
        </p>
      )}

      <ProjectUploadModal
        isOpen={isUploadOpen}
        projectId={project.id}
        onClose={() => setIsUploadOpen(false)}
        onUploaded={handleUploaded}
      />
      {actions.viewing && <DocumentViewer document={actions.viewing} onClose={actions.close} />}
    </div>
  );
};
