import React from 'react';
import { AlertCircle } from 'lucide-react';

interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = "Something went wrong",
  message = "We couldn’t load this content.",
  onRetry,
}) => {
  return (
    <div className="w-full py-12 px-4 flex flex-col items-center justify-center text-center bg-panel border border-line rounded-lg">
      <div className="w-10 h-10 rounded-full bg-canvas text-ink-soft flex items-center justify-center mb-3 border border-line">
        <AlertCircle className="w-5 h-5 stroke-[1.5]" />
      </div>
      <h3 className="text-sm font-semibold text-ink mb-1">{title}</h3>
      <p className="text-xs text-ink-soft max-w-sm mb-5 leading-relaxed">
        {message}
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="bg-transparent border border-line hover:bg-canvas text-ink text-xs font-medium px-4 py-1.5 rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2"
        >
          Retry
        </button>
      )}
    </div>
  );
};
