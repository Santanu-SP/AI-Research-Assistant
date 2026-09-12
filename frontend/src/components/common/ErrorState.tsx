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
    <div className="w-full py-12 px-4 flex flex-col items-center justify-center text-center bg-white border border-[#e5e7e4] rounded-lg">
      <div className="w-10 h-10 rounded-full bg-[#fafaf8] text-[#6b706c] flex items-center justify-center mb-3 border border-[#e5e7e4]">
        <AlertCircle className="w-5 h-5 stroke-[1.5]" />
      </div>
      <h3 className="text-sm font-semibold text-[#181a18] mb-1">{title}</h3>
      <p className="text-xs text-[#6b706c] max-w-sm mb-5 leading-relaxed">
        {message}
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="bg-transparent border border-[#e5e7e4] hover:bg-[#fafaf8] text-[#181a18] text-xs font-medium px-4 py-1.5 rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-[#163328] focus:ring-offset-2"
        >
          Retry
        </button>
      )}
    </div>
  );
};
