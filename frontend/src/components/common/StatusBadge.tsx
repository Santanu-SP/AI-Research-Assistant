import React from 'react';

export type BadgeStatus =
  | 'completed'
  | 'ready'
  | 'uploaded'
  | 'indexed'
  | 'researching'
  | 'processing'
  | 'draft'
  | 'failed';

interface StatusBadgeProps {
  status: BadgeStatus | string;
  label?: string;
  size?: 'sm' | 'md';
  title?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  label,
  size = 'md',
  title,
}) => {
  const normalized = status.toLowerCase();

  let bgClass = 'bg-subtle text-ink-soft border-line';
  let dotClass = 'bg-ink-muted';
  let showPulse = false;
  let defaultLabel = 'Draft';

  if (normalized === 'completed' || normalized === 'ready' || normalized === 'indexed') {
    bgClass = 'bg-accent-soft text-accent border-accent-line';
    dotClass = 'bg-solid';
    defaultLabel = normalized === 'completed' ? 'Completed' : normalized === 'indexed' ? 'Indexed' : 'Ready';
  } else if (normalized === 'uploaded') {
    bgClass = 'bg-subtle text-ink-soft border-line';
    dotClass = 'bg-ink-muted';
    defaultLabel = 'Uploaded';
  } else if (normalized === 'researching' || normalized === 'processing') {
    bgClass = 'bg-warning-soft text-warning border-warning-line';
    dotClass = 'bg-warning';
    showPulse = true;
    defaultLabel = normalized === 'researching' ? 'Researching' : 'Processing';
  } else if (normalized === 'failed') {
    bgClass = 'bg-danger-soft text-danger border-danger-line';
    dotClass = 'bg-danger';
    defaultLabel = 'Failed';
  }

  const text = label || defaultLabel;
  const paddingClass = size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-0.5 text-[11.5px]';

  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1.5 font-medium rounded-full border ${bgClass} ${paddingClass} tracking-normal`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${dotClass} ${
          showPulse ? 'animate-pulse' : ''
        }`}
      />
      <span>{text}</span>
    </span>
  );
};
