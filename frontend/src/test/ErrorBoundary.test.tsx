import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React, { useState } from 'react';
import { ErrorBoundary } from '../components/common/ErrorBoundary';

let shouldThrow = true;
const Bomb: React.FC = () => {
  if (shouldThrow) throw new Error('kaboom');
  return <p>Recovered content</p>;
};

describe('ErrorBoundary', () => {
  beforeEach(() => {
    shouldThrow = true;
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });
  afterEach(() => vi.restoreAllMocks());

  it('shows a recoverable message instead of a blank screen', () => {
    render(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong');
    expect(screen.queryByText('kaboom')).not.toBeInTheDocument();

    shouldThrow = false;
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(screen.getByText('Recovered content')).toBeInTheDocument();
  });

  it('asks for a reload when a lazy chunk fails to load', () => {
    const ChunkBomb: React.FC = () => {
      throw new Error('Failed to fetch dynamically imported module: /assets/Page.js');
    };
    render(
      <ErrorBoundary>
        <ChunkBomb />
      </ErrorBoundary>,
    );
    expect(screen.getByText('A new version is available')).toBeInTheDocument();
  });

  it('resets when its key changes', () => {
    const Harness: React.FC = () => {
      const [page, setPage] = useState('a');
      return (
        <>
          <button type="button" onClick={() => setPage('b')}>go</button>
          <ErrorBoundary key={page}>{page === 'a' ? <Bomb /> : <p>Page B</p>}</ErrorBoundary>
        </>
      );
    };
    render(<Harness />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
    fireEvent.click(screen.getByText('go'));
    expect(screen.getByText('Page B')).toBeInTheDocument();
  });
});
