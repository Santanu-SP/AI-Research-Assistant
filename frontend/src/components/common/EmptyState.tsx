import React from 'react';
import { LucideIcon, FolderSearch } from 'lucide-react';
import { PrimaryButton } from './PrimaryButton';

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description: string;
  primaryActionLabel?: string;
  onPrimaryAction?: () => void;
  secondaryActionLabel?: string;
  onSecondaryAction?: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon: Icon = FolderSearch,
  title,
  description,
  primaryActionLabel,
  onPrimaryAction,
  secondaryActionLabel,
  onSecondaryAction,
}) => (
  <div className="flex w-full flex-col items-center justify-center rounded-lg border border-dashed border-line-strong bg-panel px-6 py-14 text-center">
    <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg border border-line bg-subtle text-ink-soft">
      <Icon className="h-5 w-5" strokeWidth={1.75} />
    </div>
    <h3 className="text-sm font-semibold text-ink">{title}</h3>
    <p className="mt-1 max-w-sm text-[13px] leading-relaxed text-ink-soft">{description}</p>
    {(primaryActionLabel || secondaryActionLabel) && (
      <div className="mt-5 flex items-center gap-2">
        {secondaryActionLabel && onSecondaryAction && (
          <PrimaryButton variant="outline" onClick={onSecondaryAction}>
            {secondaryActionLabel}
          </PrimaryButton>
        )}
        {primaryActionLabel && onPrimaryAction && (
          <PrimaryButton onClick={onPrimaryAction}>{primaryActionLabel}</PrimaryButton>
        )}
      </div>
    )}
  </div>
);
