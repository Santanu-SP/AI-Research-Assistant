import React from 'react';

export type BadgeStatus =
  | 'completed'
  | 'ready'
  | 'researching'
  | 'processing'
  | 'draft'
  | 'failed';

interface StatusBadgeProps {
  status: BadgeStatus | string;
  label?: string;
  size?: 'sm' | 'md';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  label,
  size = 'md',
}) => {
  const normalized = status.toLowerCase();

  let bgClass = 'bg-[#f3f4f6] text-[#6b706c] border-[#e5e7e4]';
  let dotClass = 'bg-[#929792]';
  let showPulse = false;
  let defaultLabel = 'Draft';

  if (normalized === 'completed' || normalized === 'ready') {
    bgClass = 'bg-[#f1f6f3] text-[#173d31] border-[#d8e5df]';
    dotClass = 'bg-[#173d31]';
    defaultLabel = normalized === 'completed' ? 'Completed' : 'Ready';
  } else if (normalized === 'researching' || normalized === 'processing') {
    bgClass = 'bg-[#fef3c7] text-[#b45309] border-[#fde68a]';
    dotClass = 'bg-[#b45309]';
    showPulse = true;
    defaultLabel = normalized === 'researching' ? 'Researching' : 'Processing';
  } else if (normalized === 'failed') {
    bgClass = 'bg-[#fee2e2] text-[#b91c1c] border-[#fecaca]';
    dotClass = 'bg-[#b91c1c]';
    defaultLabel = 'Failed';
  }

  const text = label || defaultLabel;
  const paddingClass = size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-0.5 text-[11.5px]';

  return (
    <span
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
