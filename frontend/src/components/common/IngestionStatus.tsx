/**
 * Status badge for the ingestion lifecycle. Callers pass a short summary;
 * the raw processing error is not rendered here.
 */
import React from 'react';
import { Clock, Loader2, CheckCircle2, AlertCircle, HelpCircle } from 'lucide-react';
import { DocumentStatus } from '../../types/document';

interface IngestionStatusProps {
  status: DocumentStatus | string;
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
    className: 'text-ink-soft bg-subtle border-line',
  },
  processing: {
    label: 'Processing',
    icon: Loader2,
    className: 'text-warning bg-warning-soft border-warning-line',
  },
  indexed: {
    label: 'Indexed',
    icon: CheckCircle2,
    className: 'text-accent bg-accent-soft border-accent-line',
  },
  failed: {
    label: 'Failed',
    icon: AlertCircle,
    className: 'text-danger bg-danger-soft border-danger-line',
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
    className: 'text-ink-muted bg-subtle border-line',
  };

  const Icon = config.icon;
  const iconSize = size === 'sm' ? 'w-3 h-3' : 'w-3.5 h-3.5';
  const textSize = size === 'sm' ? 'text-[11px]' : 'text-xs';
  const padding = size === 'sm' ? 'h-5 px-1.5' : 'h-[22px] px-2';

  return (
    <div className="inline-flex flex-col items-start gap-0.5">
      <span
        className={`inline-flex items-center gap-1 whitespace-nowrap rounded-md border font-medium ${config.className} ${textSize} ${padding}`}
        aria-label={`Ingestion status: ${config.label}`}
      >
        <Icon
          className={`${iconSize} shrink-0 ${status === 'processing' ? 'animate-spin' : ''}`}
        />
        {config.label}
      </span>
      {status === 'failed' && errorSummary && (
        <span className="max-w-md text-xs leading-snug text-danger">
          {errorSummary}
        </span>
      )}
    </div>
  );
};
