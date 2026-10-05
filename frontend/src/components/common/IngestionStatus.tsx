/**
 * IngestionStatus: A reusable badge for document ingestion lifecycle states.
 *
 * Supports all current backend statuses (uploaded | processing | indexed | failed)
 * with safe fallback for unknown future statuses.
 * Does NOT display Python stack traces or raw processing_error strings.
 */
import React from 'react';
import { Clock, Loader2, CheckCircle2, AlertCircle, HelpCircle } from 'lucide-react';
import { DocumentStatus } from '../../types/document';

interface IngestionStatusProps {
  status: DocumentStatus | string;
  /** If status is 'failed', an optional user-safe error summary. */
  errorSummary?: string | null;
  size?: 'sm' | 'md';
}

const STATUS_CONFIG: Record<
  string,
  {
    label: string;
    icon: React.ElementType;
    className: string;
  }
> = {
  uploaded: {
    label: 'Uploaded',
    icon: Clock,
    className: 'text-[#b45309] bg-[#fef3c7] border-[#fde68a]',
  },
  processing: {
    label: 'Processing',
    icon: Loader2,
    className: 'text-[#0369a1] bg-[#e0f2fe]/50 border-[#bae6fd]',
  },
  indexed: {
    label: 'Indexed',
    icon: CheckCircle2,
    className: 'text-[#163328] bg-[#f1f6f3] border-[#d8e5df]',
  },
  failed: {
    label: 'Failed',
    icon: AlertCircle,
    className: 'text-[#b91c1c] bg-[#fee2e2]/60 border-[#fecaca]',
  },
};

export const IngestionStatus: React.FC<IngestionStatusProps> = ({
  status,
  errorSummary,
  size = 'sm',
}) => {
  const config = STATUS_CONFIG[status] ?? {
    label: String(status),
    icon: HelpCircle,
    className: 'text-[#929792] bg-[#f5f5f2] border-[#e5e7e4]',
  };

  const Icon = config.icon;
  const iconSize = size === 'sm' ? 'w-3 h-3' : 'w-3.5 h-3.5';
  const textSize = size === 'sm' ? 'text-[10px]' : 'text-xs';
  const padding = size === 'sm' ? 'px-1.5 py-0.5' : 'px-2 py-1';

  return (
    <div className="inline-flex flex-col items-start gap-0.5">
      <span
        className={`inline-flex items-center gap-1 font-medium rounded border ${config.className} ${textSize} ${padding}`}
        aria-label={`Ingestion status: ${config.label}`}
      >
        <Icon
          className={`${iconSize} shrink-0 ${status === 'processing' ? 'animate-spin' : ''}`}
        />
        {config.label}
      </span>
      {status === 'failed' && errorSummary && (
        <span className="text-[10px] text-[#b91c1c] max-w-xs leading-snug">
          {errorSummary}
        </span>
      )}
    </div>
  );
};
