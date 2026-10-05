/**
 * ArchiveProjectDialog: Confirmation dialog before archiving a project.
 *
 * Backend uses DELETE /projects/{id} as a soft archive (not hard delete).
 * Archived projects can be viewed with includeArchived=true on list endpoint.
 */
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
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs"
      onMouseDown={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="archive-project-title"
        aria-describedby="archive-project-description"
        className="w-full max-w-sm bg-white rounded-xl shadow-xl border border-[#e5e7e4] overflow-hidden animate-in fade-in zoom-in-95 duration-150"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-5">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-full bg-[#fee2e2]/60 flex items-center justify-center shrink-0">
              <Archive className="w-5 h-5 text-[#b91c1c]" />
            </div>
            <h3
              id="archive-project-title"
              className="font-semibold text-base text-[#181a18]"
            >
              Archive project?
            </h3>
            <button
              type="button"
              onClick={onClose}
              aria-label="Cancel"
              className="ml-auto text-[#929792] hover:text-[#181a18] p-1.5 rounded-md hover:bg-[#f5f5f2] transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <p
            id="archive-project-description"
            className="text-sm text-[#6b706c] leading-relaxed"
          >
            <strong className="text-[#181a18]">"{project.name}"</strong> will be
            archived. You will no longer be able to upload new documents or run
            research within it. Existing documents and reports are preserved.
          </p>

          {error && (
            <p
              role="alert"
              className="mt-3 text-xs text-[#b91c1c] bg-[#fee2e2]/50 border border-[#fecaca] rounded-lg px-3 py-2"
            >
              {error}
            </p>
          )}

          <div className="flex items-center gap-2.5 mt-5">
            <button
              type="button"
              onClick={onClose}
              disabled={isArchiving}
              className="flex-1 text-sm font-medium text-[#6b706c] hover:text-[#181a18] border border-[#e5e7e4] hover:bg-[#f5f5f2] px-4 py-2 rounded-lg transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void handleArchive()}
              disabled={isArchiving}
              className="flex-1 text-sm font-medium text-white bg-[#b91c1c] hover:bg-[#991b1b] px-4 py-2 rounded-lg transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
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
