/** DELETE /projects/{id} archives the project; it does not remove the row. */
import React, { useEffect, useState } from 'react';
import { Archive, X } from 'lucide-react';
import { ResearchProject } from '../../types/project';
import {
  getProjectErrorMessage,
  projectsService,
} from '../../services/projects.service';
import { useToast } from '../../app/ToastContext';

interface ArchiveProjectDialogProps {
  project: ResearchProject | null;
  onClose: () => void;
  onArchived: () => void;
}

export const ArchiveProjectDialog: React.FC<ArchiveProjectDialogProps> = ({
  project,
  onClose,
  onArchived,
}) => {
  const { addToast } = useToast();
  const [isArchiving, setIsArchiving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isOpen = Boolean(project);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isArchiving) onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isOpen, isArchiving, onClose]);

  if (!project) return null;

  const handleArchive = async () => {
    setIsArchiving(true);
    setError(null);
    try {
      await projectsService.archiveProject(project.id);
      addToast({
        type: 'success',
        title: 'Project archived',
        description: `"${project.name}" has been archived.`,
      });
      onArchived();
    } catch (err) {
      setError(getProjectErrorMessage(err, 'Failed to archive project.'));
    } finally {
      setIsArchiving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 overlay-enter"
      onMouseDown={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="archive-project-title"
        aria-describedby="archive-project-description"
        className="w-full max-w-sm bg-panel rounded-xl shadow-xl border border-line overflow-hidden dialog-enter"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-5">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-danger-line bg-danger-soft">
              <Archive className="w-5 h-5 text-danger" />
            </div>
            <h3
              id="archive-project-title"
              className="font-semibold text-base text-ink"
            >
              Archive project?
            </h3>
            <button
              type="button"
              onClick={onClose}
              aria-label="Cancel"
              className="ml-auto text-ink-muted hover:text-ink p-1.5 rounded-md hover:bg-subtle transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <p
            id="archive-project-description"
            className="text-sm text-ink-soft leading-relaxed"
          >
            <strong className="text-ink">"{project.name}"</strong> will be
            archived. You will no longer be able to upload new documents or run
            research within it. Existing documents and reports are preserved.
          </p>

          {error && (
            <p
              role="alert"
              className="mt-3 text-xs text-danger bg-danger-soft border border-danger-line rounded-lg px-3 py-2"
            >
              {error}
            </p>
          )}

          <div className="flex items-center gap-2.5 mt-5">
            <button
              type="button"
              onClick={onClose}
              disabled={isArchiving}
              className="inline-flex h-9 flex-1 items-center justify-center rounded-md border border-line-strong bg-panel px-4 text-[13px] font-medium text-ink shadow-xs transition-colors hover:bg-subtle disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void handleArchive()}
              disabled={isArchiving}
              className="inline-flex h-9 flex-1 items-center justify-center gap-2 rounded-md bg-danger-solid px-4 text-[13px] font-medium text-on-solid shadow-xs transition-colors hover:bg-danger-solid-hover disabled:opacity-60"
            >
              {isArchiving ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                  Archiving…
                </>
              ) : (
                'Archive project'
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
