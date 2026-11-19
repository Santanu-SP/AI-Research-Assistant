import React, { useState } from 'react';
import { Archive, Settings2, Users } from 'lucide-react';
import { ResearchProject } from '../../types/project';
import { PresenceMember } from '../../types/collaboration';
import type { RealtimeConnectionState } from '../../hooks/useRealtimeRoom';
import { EditProjectDialog } from './EditProjectDialog';
import { ArchiveProjectDialog } from './ArchiveProjectDialog';
import { ShareDialog } from '../collaboration/ShareDialog';
import { PresenceBar } from '../collaboration/PresenceBar';

interface ProjectHeaderProps {
  project: ResearchProject;
  onUpdated: () => void;
  onArchived: () => void;
  presence?: PresenceMember[];
  connectionState?: RealtimeConnectionState;
  currentUserId?: string | null;
}

const formatDate = (iso: string): string =>
  new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(new Date(iso));

export const ProjectHeader: React.FC<ProjectHeaderProps> = ({
  project,
  onUpdated,
  onArchived,
  presence = [],
  connectionState = 'idle',
  currentUserId = null,
}) => {
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isArchiveOpen, setIsArchiveOpen] = useState(false);
  const [isShareOpen, setIsShareOpen] = useState(false);
  const isArchived = Boolean(project.archivedAt);
  const myRole = project.myRole ?? 'owner';
  const isOwner = myRole === 'owner';
  const canEdit = myRole === 'owner' || myRole === 'editor';

  return (
    <>
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-[22px] font-semibold leading-tight tracking-[-0.015em] text-ink sm:text-2xl">
              {project.name}
            </h1>
            {project.isShared && (
              <span className="inline-flex items-center gap-1 rounded-full border border-accent-line bg-accent-soft px-2 py-0.5 text-[11px] font-medium text-accent">
                <Users className="h-3 w-3" />
                {myRole === 'owner'
                  ? `Shared (${project.memberCount ?? 2})`
                  : myRole === 'editor'
                    ? 'Shared · Can edit'
                    : 'Shared · View only'}
              </span>
            )}
          </div>
          {project.description && (
            <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-ink-soft">
              {project.description}
            </p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-muted">
            <span>Created {formatDate(project.createdAt)}</span>
            <span>·</span>
            <span>Updated {formatDate(project.updatedAt)}</span>
            {project.ownerName && myRole !== 'owner' && (
              <>
                <span>·</span>
                <span>Owner: {project.ownerName}</span>
              </>
            )}
            {isArchived && project.archivedAt && (
              <>
                <span>·</span>
                <span className="flex items-center gap-1 text-warning">
                  <Archive className="w-3 h-3" />
                  Archived {formatDate(project.archivedAt)}
                </span>
              </>
            )}
            <PresenceBar
              presence={presence}
              currentUserId={currentUserId}
              connectionState={connectionState}
            />
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {!isArchived && (
            <button
              type="button"
              aria-label={isOwner ? 'Share project' : 'View project members'}
              onClick={() => setIsShareOpen(true)}
              className="inline-flex h-9 items-center gap-1.5 rounded-md border border-line-strong bg-panel px-3 text-[13px] font-medium text-ink shadow-xs transition-colors hover:bg-subtle"
            >
              <Users className="h-4 w-4 text-accent" />
              <span className="hidden sm:inline">{isOwner ? 'Share' : 'Members'}</span>
            </button>
          )}
          {canEdit && (
            <button
              type="button"
              aria-label="Edit project settings"
              onClick={() => setIsEditOpen(true)}
              className="inline-flex h-9 items-center gap-1.5 rounded-md border border-line-strong bg-panel px-3 text-[13px] font-medium text-ink shadow-xs transition-colors hover:bg-subtle"
            >
              <Settings2 className="h-4 w-4" />
              <span className="hidden sm:inline">Settings</span>
            </button>
          )}
          {!isArchived && isOwner && (
            <button
              type="button"
              aria-label="Archive this project"
              onClick={() => setIsArchiveOpen(true)}
              className="inline-flex h-9 items-center gap-1.5 rounded-md px-3 text-[13px] font-medium text-ink-soft transition-colors hover:bg-danger-soft hover:text-danger"
            >
              <Archive className="h-4 w-4" />
              <span className="hidden sm:inline">Archive</span>
            </button>
          )}
        </div>
      </div>

      {isArchived && (
        <div className="mt-5 flex items-start gap-3 rounded-lg border border-warning-line bg-warning-soft px-4 py-3 text-[13px] text-warning">
          <Archive className="w-4 h-4 mt-0.5 shrink-0" />
          <p>
            <strong>This project is archived.</strong> You can view existing
            files and research results, but cannot upload new files or
            run new research.
          </p>
        </div>
      )}

      {!isArchived && myRole === 'viewer' && (
        <div className="mt-4 flex items-center gap-2 rounded-lg border border-line bg-subtle/50 px-3.5 py-2.5 text-xs text-ink-soft">
          <Users className="h-3.5 w-3.5 shrink-0 text-ink-muted" />
          <span>
            <strong>View-only access.</strong> You can read files, reports, and live updates, but only editors or the owner can upload files or ask questions.
          </span>
        </div>
      )}

      <ShareDialog
        isOpen={isShareOpen}
        resourceType="project"
        resourceId={project.id}
        resourceTitle={project.name}
        onClose={() => setIsShareOpen(false)}
        onChanged={onUpdated}
      />

      <EditProjectDialog
        project={isEditOpen ? project : null}
        onClose={() => setIsEditOpen(false)}
        onUpdated={() => {
          setIsEditOpen(false);
          onUpdated();
        }}
      />

      <ArchiveProjectDialog
        project={isArchiveOpen ? project : null}
        onClose={() => setIsArchiveOpen(false)}
        onArchived={() => {
          setIsArchiveOpen(false);
          onArchived();
        }}
      />
    </>
  );
};
