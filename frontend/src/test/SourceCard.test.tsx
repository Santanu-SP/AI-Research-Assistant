import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { SourceCard } from '../components/projects/SourceCard';
import { makeDocument, makeProcessingDocument, makeFailedDocument } from './fixtures';

describe('SourceCard', () => {
  it('renders document title', () => {
    const doc = makeDocument({ title: 'A Study of Membrane Proteins' });
    render(<SourceCard document={doc} />);
    expect(screen.getByText('A Study of Membrane Proteins')).toBeInTheDocument();
  });

  it('falls back to filename when title is null', () => {
    const doc = makeDocument({ title: null });
    render(<SourceCard document={doc} />);
    expect(screen.getByText('paper.pdf')).toBeInTheDocument();
  });

  it('opens a ready document when its name is clicked', () => {
    const doc = makeDocument();
    const onOpen = vi.fn();
    render(<SourceCard document={doc} onOpen={onOpen} />);
    fireEvent.click(screen.getByRole('button', { name: /Open A Study of Membrane Proteins/i }));
    expect(onOpen).toHaveBeenCalledWith(doc);
  });

  it('shows a calm preparing state that cannot be opened', () => {
    const onOpen = vi.fn();
    render(<SourceCard document={makeProcessingDocument()} onOpen={onOpen} />);
    expect(screen.getByText('Preparing…')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Open/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/processing|indexed|chunk/i)).not.toBeInTheDocument();
  });

  it('treats freshly uploaded files as waiting to start', () => {
    render(<SourceCard document={makeDocument({ status: 'uploaded', ingestionStatus: 'uploaded' })} onOpen={vi.fn()} />);
    expect(screen.getByText('Waiting to start')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Open/i })).not.toBeInTheDocument();
  });

  it('shows the current step while a file is being prepared', () => {
    const { rerender } = render(
      <SourceCard document={makeProcessingDocument({ processingStage: 'ocr', pageCount: null })} />
    );
    expect(screen.getByText('Reading text from images (OCR)')).toBeInTheDocument();

    rerender(
      <SourceCard
        document={makeProcessingDocument({ processingStage: 'embedding', processingProgress: 40, pageCount: 12 })}
      />
    );
    expect(screen.getByText('Making it searchable · 40% · 12 pages')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '71');

    rerender(<SourceCard document={makeProcessingDocument({ processingStage: 'saving', pageCount: null })} />);
    expect(screen.getByText('Saving')).toBeInTheDocument();
  });

  it('shows a plain message for failed files', () => {
    render(<SourceCard document={makeFailedDocument()} onOpen={vi.fn()} />);
    expect(screen.getByText(/Couldn’t process this file/)).toBeInTheDocument();
    expect(screen.queryByText(/Failed to parse/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Open/i })).not.toBeInTheDocument();
  });

  it('does not show raw stack trace in error summary', () => {
    const doc = makeFailedDocument({
      processingError:
        'Traceback (most recent call last):\n  File "/app/parser.py", line 42\nValueError: invalid PDF\nAnother line\nYet another line\nLine 5\nLine 6\nLine 7\nLine 8',
    });
    render(<SourceCard document={doc} />);
    // Should show truncated/safe message, not the full traceback
    expect(screen.queryByText(/Traceback/)).not.toBeInTheDocument();
  });

  it('shows delete button when onDelete provided and not archived', () => {
    const doc = makeDocument();
    const onDelete = vi.fn();
    render(<SourceCard document={doc} onDelete={onDelete} isArchived={false} />);
    expect(
      screen.getByRole('button', { name: /Delete file/i })
    ).toBeInTheDocument();
  });

  it('hides delete button when isArchived=true', () => {
    const doc = makeDocument();
    const onDelete = vi.fn();
    render(<SourceCard document={doc} onDelete={onDelete} isArchived={true} />);
    expect(
      screen.queryByRole('button', { name: /Delete file/i })
    ).not.toBeInTheDocument();
  });

  it('calls onDelete with document id when delete clicked', () => {
    const doc = makeDocument({ id: 'doc-001' });
    const onDelete = vi.fn();
    render(<SourceCard document={doc} onDelete={onDelete} isArchived={false} />);
    fireEvent.click(screen.getByRole('button', { name: /Delete file/i }));
    expect(onDelete).toHaveBeenCalledWith('doc-001');
  });

  it('renders DOI link when doi is present', () => {
    const doc = makeDocument({ doi: '10.1234/test.doi' });
    render(<SourceCard document={doc} />);
    const link = screen.getByRole('link', { name: /DOI/i });
    expect(link).toHaveAttribute('href', 'https://doi.org/10.1234/test.doi');
  });

  it('renders page count when available and greater than 0', () => {
    const doc = makeDocument({ pageCount: 12 });
    render(<SourceCard document={doc} />);
    expect(screen.getByText('12 pages')).toBeInTheDocument();
  });

  it('never shows chunk counts', () => {
    render(<SourceCard document={makeDocument({ chunkCount: 48 })} />);
    expect(screen.queryByText(/chunk/i)).not.toBeInTheDocument();
  });

  it('offers a retry button only for failed documents', () => {
    const onRetry = vi.fn();
    const { rerender } = render(
      <SourceCard document={makeFailedDocument()} onRetry={onRetry} />
    );
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledWith('doc-003');

    rerender(<SourceCard document={makeDocument()} onRetry={onRetry} />);
    expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument();

    rerender(<SourceCard document={makeFailedDocument()} onRetry={onRetry} isArchived />);
    expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument();
  });
});
