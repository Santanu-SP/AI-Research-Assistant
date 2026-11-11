import React from 'react';
import { LucideIcon, FolderSearch } from 'lucide-react';

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
}) => {
  return (
    <div className="w-full py-16 px-4 flex flex-col items-center justify-center text-center bg-panel border border-line rounded-lg">
      <div className="w-12 h-12 rounded-full bg-accent-soft text-accent flex items-center justify-center mb-3">
        <Icon className="w-6 h-6 stroke-[1.5]" />
      </div>
      <h3 className="text-sm font-semibold text-ink mb-1">{title}</h3>
      <p className="text-xs text-ink-soft max-w-sm mb-5 leading-relaxed">
        {description}
      </p>
      {(primaryActionLabel || secondaryActionLabel) && (
        <div className="flex items-center gap-3">
          {secondaryActionLabel && onSecondaryAction && (
            <button
              onClick={onSecondaryAction}
              className="bg-transparent border border-line hover:bg-canvas text-ink text-xs font-medium px-3.5 py-1.5 rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2"
            >
              {secondaryActionLabel}
            </button>
          )}
          {primaryActionLabel && onPrimaryAction && (
            <button
              onClick={onPrimaryAction}
              className="bg-solid hover:bg-solid-hover text-on-solid text-xs font-medium px-3.5 py-1.5 rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2"
            >
              {primaryActionLabel}
            </button>
          )}
        </div>
      )}
    </div>
  );
};
