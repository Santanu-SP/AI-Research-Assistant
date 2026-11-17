import React, { useState } from 'react';
import { ArchiveRestore, Folder, Trash2 } from 'lucide-react';
import { ResearchProject } from '../../types/project';
import { getProjectErrorMessage, projectsService } from '../../services/projects.service';
import { useToast } from '../../app/ToastContext';
import { ActionMenu } from '../common/ActionMenu';
import { formatProjectDate } from './ProjectCard';

interface ArchivedProjectRowProps {
  project: ResearchProject;
  onRestored: (project: ResearchProject) => void;
  onDeleteRequest: (project: ResearchProject) => void;
}

/** One archived project: when it was archived, plus Restore and Delete permanently. */
export const ArchivedProjectRow: React.FC<ArchivedProjectRowProps> = ({ project, onRestored, onDeleteRequest }) => {
  const { addToast } = useToast();
  const [restoring, setRestoring] = useState(false);

  const restore = async () => {
    setRestoring(true);
    try {
      const restored = await projectsService.restoreProject(project.id);
      addToast({ type: 'success', title: 'Project restored', description: `“${project.name}” is back in your projects.` });
      onRestored(restored);
    } catch (err) {
      addToast({
        type: 'error',
        title: 'Couldn’t restore the project',
        description: getProjectErrorMessage(err, 'Please try again.'),
      });
      setRestoring(false);
    }
  };

  return (
    <li className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-4 py-3.5 sm:grid-cols-[minmax(0,1fr)_130px_auto] sm:px-5">
      <div className="flex min-w-0 items-start gap-3">
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-line bg-subtle text-ink-muted">
          <Folder className="h-4 w-4" strokeWidth={1.75} />
        </span>
        <div className="min-w-0">
          <h3 className="truncate text-sm font-medium text-ink-soft">{project.name}</h3>
          <p className="mt-0.5 truncate text-[13px] text-ink-muted">{project.description || 'No description'}</p>
          {project.archivedAt && (
            <p className="mt-1 text-xs text-ink-muted sm:hidden">Archived {formatProjectDate(project.archivedAt)}</p>
          )}
        </div>
      </div>

      <span className="hidden text-[13px] tabular-nums text-ink-muted sm:block">
        {project.archivedAt ? formatProjectDate(project.archivedAt) : '—'}
      </span>

      <div className="flex items-center gap-1 justify-self-end">
        <button
          type="button"
          onClick={() => void restore()}
          disabled={restoring}
          className="hidden h-8 items-center gap-1.5 rounded-md border border-line-strong bg-panel px-2.5 text-[13px] font-medium text-ink shadow-xs transition-colors hover:bg-subtle disabled:opacity-60 sm:inline-flex"
        >
          <ArchiveRestore className="h-3.5 w-3.5" />
          {restoring ? 'Restoring…' : 'Restore'}
        </button>
        <ActionMenu
          label={`Actions for ${project.name}`}
          items={[
            { label: 'Restore', icon: ArchiveRestore, onSelect: () => void restore() },
            { label: 'Delete permanently', icon: Trash2, danger: true, separated: true, onSelect: () => onDeleteRequest(project) },
          ]}
        />
      </div>
    </li>
  );
};
