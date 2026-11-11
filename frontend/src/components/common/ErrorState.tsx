import React from 'react';
import { AlertCircle, RotateCw } from 'lucide-react';
import { PrimaryButton } from './PrimaryButton';

interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = 'Something went wrong',
  message = 'We couldn’t load this content.',
  onRetry,
}) => (
  <div
    className="flex w-full flex-col items-center justify-center rounded-lg border border-line bg-panel px-6 py-12 text-center"
  >
    <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg border border-danger-line bg-danger-soft text-danger">
      <AlertCircle className="h-5 w-5" strokeWidth={1.75} />
    </div>
    <h3 className="text-sm font-semibold text-ink">{title}</h3>
    <p className="mt-1 max-w-sm text-[13px] leading-relaxed text-ink-soft">{message}</p>
    {onRetry && (
      <PrimaryButton variant="outline" className="mt-5" onClick={onRetry}>
        <RotateCw className="h-3.5 w-3.5" />
        Retry
      </PrimaryButton>
    )}
  </div>
);
