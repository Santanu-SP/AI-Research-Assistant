/**
 * Tests for IngestionStatus component.
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { IngestionStatus } from '../components/common/IngestionStatus';

describe('IngestionStatus', () => {
  it('renders "Indexed" for indexed status', () => {
    render(<IngestionStatus status="indexed" />);
    expect(screen.getByText('Indexed')).toBeInTheDocument();
  });

  it('renders "Processing" for processing status', () => {
    render(<IngestionStatus status="processing" />);
    expect(screen.getByText('Processing')).toBeInTheDocument();
  });

  it('renders "Uploaded" for uploaded status', () => {
    render(<IngestionStatus status="uploaded" />);
    expect(screen.getByText('Uploaded')).toBeInTheDocument();
  });

  it('renders "Failed" for failed status', () => {
    render(<IngestionStatus status="failed" />);
    expect(screen.getByText('Failed')).toBeInTheDocument();
  });

  it('shows error summary when status is failed and errorSummary is provided', () => {
    render(
      <IngestionStatus status="failed" errorSummary="Parse error" />
    );
    expect(screen.getByText('Parse error')).toBeInTheDocument();
  });

  it('does not show error summary for non-failed statuses', () => {
    render(
      <IngestionStatus status="indexed" errorSummary="Should not appear" />
    );
    expect(screen.queryByText('Should not appear')).not.toBeInTheDocument();
  });

  it('renders unknown status gracefully', () => {
    render(<IngestionStatus status="unknown_future_status" />);
    expect(screen.getByText('unknown_future_status')).toBeInTheDocument();
  });

  it('has accessible aria-label', () => {
    render(<IngestionStatus status="indexed" />);
    expect(
      screen.getByLabelText('Ingestion status: Indexed')
    ).toBeInTheDocument();
  });
});
