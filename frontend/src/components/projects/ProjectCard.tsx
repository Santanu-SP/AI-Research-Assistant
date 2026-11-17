import React, { useState } from 'react';
import { Pencil, Archive, ExternalLink, Folder } from 'lucide-react';
import { ActionMenu } from '../common/ActionMenu';
import { ResearchProject } from '../../types/project';
import { EditProjectDialog } from './EditProjectDialog';
import { ArchiveProjectDialog } from './ArchiveProjectDialog';

interface ProjectCardProps {
  project: ResearchProject;
  onOpen: (project: ResearchProject) => void;
  onUpdated: (updated: ResearchProject) => void;
  onArchived: (id: string) => void;
}

export const formatProjectDate = (iso: string): string =>
  new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year:
      new Date(iso).getFullYear() === new Date().getFullYear()
        ? undefined
        : 'numeric',
  }).format(new Date(iso));

/** One active project in the projects list. Renders as a table-like row. Archived ones use ArchivedProjectRow. */
export const ProjectCard: React.FC<ProjectCardProps> = ({
  project,
  onOpen,
  onUpdated,
  onArchived,
}) => {
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isArchiveOpen, setIsArchiveOpen] = useState(false);
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.target !== e.currentTarget) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onOpen(project);
    }
  };

  return (
    <>
      <div
        className="group relative grid cursor-pointer grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-4 py-3.5 transition-colors hover:bg-subtle/60 sm:grid-cols-[minmax(0,1fr)_110px_110px_40px] sm:px-5"
        onClick={() => onOpen(project)}
        onKeyDown={handleKeyDown}
        role="button"
        tabIndex={0}
        aria-label={`Open project: ${project.name}`}
      >
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-line bg-subtle text-ink-soft">
            <Folder className="h-4 w-4" strokeWidth={1.75} />
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="truncate text-sm font-medium text-ink">{project.name}</h3>
            </div>
            <p className="mt-0.5 truncate text-[13px] text-ink-muted">
              {project.description || 'No description'}
            </p>
            <p className="mt-1 text-xs text-ink-muted sm:hidden">
              Updated {formatProjectDate(project.updatedAt)}
            </p>
          </div>
        </div>

        <span className="hidden text-[13px] tabular-nums text-ink-soft sm:block">
          {formatProjectDate(project.updatedAt)}
        </span>
        <span className="hidden text-[13px] tabular-nums text-ink-muted sm:block">
          {formatProjectDate(project.createdAt)}
        </span>

        <ActionMenu
          label={`Actions for ${project.name}`}
          className="justify-self-end"
          items={[
            { label: 'Open project', icon: ExternalLink, onSelect: () => onOpen(project) },
            { label: 'Rename or edit', icon: Pencil, onSelect: () => setIsEditOpen(true) },
            { label: 'Archive project', icon: Archive, danger: true, separated: true, onSelect: () => setIsArchiveOpen(true) },
          ]}
        />
      </div>

      <EditProjectDialog
        project={isEditOpen ? project : null}
        onClose={() => setIsEditOpen(false)}
        onUpdated={(updated) => {
          setIsEditOpen(false);
          onUpdated(updated);
        }}
      />

      <ArchiveProjectDialog
        project={isArchiveOpen ? project : null}
        onClose={() => setIsArchiveOpen(false)}
        onArchived={() => {
          setIsArchiveOpen(false);
          onArchived(project.id);
        }}
      />
    </>
  );
};
