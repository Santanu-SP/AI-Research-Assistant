import React from 'react';
import { ErrorState } from './ErrorState';

interface ErrorBoundaryProps {
  children: React.ReactNode;
  /** Optional custom fallback. Receives the error and a reset callback. */
  fallback?: (error: Error, reset: () => void) => React.ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

const isChunkLoadError = (error: Error): boolean =>
  /Loading chunk|dynamically imported module|Importing a module script failed/i.test(
    error.message,
  );

/**
 * Catches render errors so one broken page shows a recoverable message
 * instead of a blank screen. Give it a `key` (for example the route path)
 * to reset it on navigation.
 */
export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    console.error('Unhandled UI error', error, info.componentStack);
  }

  reset = (): void => {
    this.setState({ error: null });
  };

  render(): React.ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    if (this.props.fallback) return this.props.fallback(error, this.reset);

    // After a new deploy, old lazy chunks disappear; a reload fetches the new ones.
    const chunkError = isChunkLoadError(error);
    return (
      <div className="max-w-xl mx-auto py-16 px-4" role="alert">
        <ErrorState
          title={chunkError ? 'A new version is available' : 'Something went wrong'}
          message={
            chunkError
              ? 'Reload the page to get the latest version of the app.'
              : 'This page hit an unexpected error. Try again, or reload the page if it keeps happening.'
          }
          onRetry={chunkError ? () => window.location.reload() : this.reset}
        />
      </div>
    );
  }
}
