/**
 * EditProjectDialog: Modal for renaming and updating a project's description.
 * Only modifies backend-supported fields (name, description).
 */
import React, { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { PrimaryButton } from '../common/PrimaryButton';
import { ResearchProject } from '../../types/project';
import {
  getProjectErrorMessage,
  projectsService,
} from '../../services/projects.service';
import { useToast } from '../../app/ToastContext';

interface EditProjectDialogProps {
  project: ResearchProject | null;
  onClose: () => void;
  onUpdated: (updated: ResearchProject) => void;
}

export const EditProjectDialog: React.FC<EditProjectDialogProps> = ({
  project,
  onClose,
  onUpdated,
}) => {
  const { addToast } = useToast();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const isOpen = Boolean(project);

  useEffect(() => {
    if (project) {
      setName(project.name);
      setDescription(project.description ?? '');
      setError(null);
      setTimeout(() => nameRef.current?.focus(), 50);
    }
  }, [project]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isSubmitting) onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isOpen, isSubmitting, onClose]);

  if (!project) return null;

  const trimmedName = name.trim();
  const isDirty =
    trimmedName !== project.name ||
    (description.trim() || null) !== project.description;
  const isValid = trimmedName.length >= 1 && trimmedName.length <= 200;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid || !isDirty || isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const updated = await projectsService.updateProject(project.id, {
        name: trimmedName,
        description: description.trim() || null,
      });
      addToast({ type: 'success', title: 'Project updated' });
      onUpdated(updated);
    } catch (err) {
      setError(getProjectErrorMessage(err, 'Failed to update project.'));
    } finally {
      setIsSubmitting(false);
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
        aria-labelledby="edit-project-title"
        className="w-full max-w-md bg-white rounded-xl shadow-xl border border-[#e5e7e4] overflow-hidden animate-in fade-in zoom-in-95 duration-150"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-4 border-b border-[#e5e7e4] flex items-center justify-between">
          <h3
            id="edit-project-title"
            className="font-semibold text-base text-[#181a18]"
          >
            Edit Project
          </h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="text-[#929792] hover:text-[#181a18] p-1.5 rounded-md hover:bg-[#f5f5f2] transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={(e) => void handleSubmit(e)} className="p-6 space-y-4">
          <div>
            <label
              htmlFor="edit-project-name"
              className="block text-xs font-medium text-[#181a18] mb-1.5"
            >
              Project name <span aria-hidden="true" className="text-[#b91c1c]">*</span>
            </label>
            <input
              ref={nameRef}
              id="edit-project-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={200}
              required
              autoComplete="off"
              className="w-full border border-[#e5e7e4] rounded-lg px-3 py-2 text-sm text-[#181a18] placeholder:text-[#929792] focus:outline-none focus:ring-1 focus:ring-[#163328] focus:border-[#163328] transition-colors"
            />
          </div>

          <div>
            <label
              htmlFor="edit-project-description"
              className="block text-xs font-medium text-[#181a18] mb-1.5"
            >
              Description{' '}
              <span className="text-[#929792] font-normal">(optional)</span>
            </label>
            <textarea
              id="edit-project-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={5000}
              rows={3}
              className="w-full border border-[#e5e7e4] rounded-lg px-3 py-2 text-sm text-[#181a18] placeholder:text-[#929792] focus:outline-none focus:ring-1 focus:ring-[#163328] focus:border-[#163328] transition-colors resize-none"
            />
          </div>

          {error && (
            <p
              role="alert"
              className="text-xs text-[#b91c1c] bg-[#fee2e2]/50 border border-[#fecaca] rounded-lg px-3 py-2"
            >
              {error}
            </p>
          )}

          {isDirty && !error && (
            <p className="text-[11px] text-[#929792]">
              You have unsaved changes.
            </p>
          )}

          <div className="flex items-center justify-end gap-2.5 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="text-xs font-medium text-[#6b706c] hover:text-[#181a18] px-3.5 py-2 rounded-md hover:bg-[#f5f5f2] transition-colors"
            >
              Cancel
            </button>
            <PrimaryButton
              type="submit"
              disabled={!isValid || !isDirty || isSubmitting}
              isLoading={isSubmitting}
            >
              {isSubmitting ? 'Saving…' : 'Save changes'}
            </PrimaryButton>
          </div>
        </form>
      </div>
    </div>
  );
};
