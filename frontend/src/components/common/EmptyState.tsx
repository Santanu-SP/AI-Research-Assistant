import React from 'react';
import { LucideIcon, FolderSearch } from 'lucide-react';

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon: Icon = FolderSearch,
  title,
  description,
  actionLabel,
  onAction,
}) => {
  return (
    <div className="w-full py-16 px-4 flex flex-col items-center justify-center text-center bg-white border border-[#e5e7e4] rounded-lg">
      <div className="w-12 h-12 rounded-full bg-[#f1f6f3] text-[#163328] flex items-center justify-center mb-3">
        <Icon className="w-6 h-6 stroke-[1.5]" />
      </div>
      <h3 className="text-sm font-semibold text-[#181a18] mb-1">{title}</h3>
      <p className="text-xs text-[#6b706c] max-w-sm mb-5 leading-relaxed">
        {description}
      </p>
      {actionLabel && onAction && (
        <button
          onClick={onAction}
          className="bg-[#163328] hover:bg-[#214f40] text-white text-xs font-medium px-3.5 py-1.5 rounded-md transition-colors"
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
};
