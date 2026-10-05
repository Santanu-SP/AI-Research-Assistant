/**
 * Tests for CreateProjectDialog component.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { CreateProjectDialog } from '../components/projects/CreateProjectDialog';
import { ToastProvider } from '../app/ToastContext';
import { makeProject } from './fixtures';

vi.mock('../services/projects.service', () => ({
  projectsService: {
    createProject: vi.fn(),
  },
  getProjectErrorMessage: vi.fn((_err: unknown, fallback: string) => fallback),
}));

import { projectsService } from '../services/projects.service';

const renderDialog = (
  props: Partial<React.ComponentProps<typeof CreateProjectDialog>> = {}
) => {
  const onClose = vi.fn();
  const onCreated = vi.fn();

  return {
    onClose,
    onCreated,
    ...render(
      <ToastProvider>
        <CreateProjectDialog
          isOpen={true}
          onClose={onClose}
          onCreated={onCreated}
          {...props}
        />
      </ToastProvider>
    ),
  };
};

describe('CreateProjectDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders with accessible dialog role and title', () => {
    renderDialog();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('New Research Project')).toBeInTheDocument();
  });

  it('disables submit when name is empty', () => {
    renderDialog();
    const submit = screen.getByRole('button', { name: /Create project/i });
    expect(submit).toBeDisabled();
  });

  it('enables submit when valid name is entered', async () => {
    renderDialog();
    const nameInput = screen.getByLabelText(/Project name/i);
    fireEvent.change(nameInput, { target: { value: 'My New Project' } });

    const submit = screen.getByRole('button', { name: /Create project/i });
    expect(submit).not.toBeDisabled();
  });

  it('calls projectsService.createProject on submit', async () => {
    const fixture = makeProject({ name: 'New Project' });
    vi.mocked(projectsService.createProject).mockResolvedValue(fixture);

    const { onCreated } = renderDialog();
    const nameInput = screen.getByLabelText(/Project name/i);
    fireEvent.change(nameInput, { target: { value: 'New Project' } });

    fireEvent.submit(screen.getByRole('dialog').querySelector('form')!);

    await waitFor(() => {
      expect(projectsService.createProject).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'New Project' })
      );
      expect(onCreated).toHaveBeenCalledWith(fixture);
    });
  });

  it('shows error message on API failure', async () => {
    vi.mocked(projectsService.createProject).mockRejectedValue(
      new Error('Server error')
    );

    renderDialog();
    const nameInput = screen.getByLabelText(/Project name/i);
    fireEvent.change(nameInput, { target: { value: 'New Project' } });

    fireEvent.submit(screen.getByRole('dialog').querySelector('form')!);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
  });

  it('does not render when isOpen=false', () => {
    renderDialog({ isOpen: false });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('calls onClose when Cancel is clicked', async () => {
    const { onClose } = renderDialog();
    fireEvent.click(screen.getByText('Cancel'));
    expect(onClose).toHaveBeenCalled();
  });
});
