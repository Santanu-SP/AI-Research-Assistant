import React from 'react';
import { FileText, Trash2, RotateCw } from 'lucide-react';
import { Document } from '../../types/document';
import { StatusBadge } from '../common/StatusBadge';
import { LoadingOrb } from '../common/LoadingOrb';

interface DocumentRowProps {
  document: Document;
  onDelete: (id: string) => void;
  onUseInResearch?: (document: Document) => void;
}

export const DocumentRow: React.FC<DocumentRowProps> = ({
  document,
  onDelete,
  onUseInResearch,
}) => {
  const formatSize = (bytes: number): string => {
    if (bytes >= 1024 * 1024) {
      return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }
    return `${Math.round(bytes / 1024)} KB`;
  };

  const isPdf = document.type === 'pdf';
  const isDocx = document.type === 'docx';

  return (
    <div className="p-4 bg-white border border-[#e5e7e4] rounded-lg hover:border-[#cbd0ca] hover:shadow-xs transition-all duration-150 flex flex-col sm:flex-row sm:items-center justify-between gap-3 group">
      {/* File Icon + Info */}
      <div className="flex items-start gap-3 min-w-0">
        <div
          className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 border ${
            isPdf
              ? 'bg-[#fee2e2]/40 text-[#b91c1c] border-[#fecaca]'
              : isDocx
              ? 'bg-[#e0f2fe]/50 text-[#0369a1] border-[#bae6fd]'
              : 'bg-[#f5f5f2] text-[#6b706c] border-[#e5e7e4]'
          }`}
        >
          <FileText className="w-5 h-5 stroke-[1.75]" />
        </div>

        <div className="min-w-0">
          <h4 className="text-[13.5px] font-semibold text-[#181a18] truncate leading-tight group-hover:text-[#163328] transition-colors">
            {document.name}
          </h4>

          <div className="flex flex-wrap items-center gap-2 mt-1 text-xs text-[#6b706c]">
            <span className="font-medium text-[#181a18] uppercase">{document.type}</span>
            <span className="text-[#929792]">·</span>
            <span>Size: {formatSize(document.size)}</span>
            <span className="text-[#929792]">·</span>
            <span>{new Date(document.created_at).toLocaleDateString()}</span>
          </div>
        </div>
      </div>

      {/* Status & Actions */}
      <div className="flex items-center justify-between sm:justify-end gap-3 shrink-0 pt-2 sm:pt-0 border-t sm:border-t-0 border-[#f5f5f2]">
        <StatusBadge status={document.status} />

        <div className="flex items-center gap-2">
          {document.status === 'ready' && onUseInResearch && (
            <button
              type="button"
              onClick={() => onUseInResearch(document)}
              className="text-xs font-medium text-[#163328] bg-[#f1f6f3] hover:bg-[#e4eee7] border border-[#d8e5df] px-3 py-1.5 rounded-md transition-colors cursor-pointer"
            >
              Use in research
            </button>
          )}

          {document.status === 'processing' && (
            <span className="inline-flex items-center gap-1.5 text-xs text-[#b45309] font-medium px-2 py-1">
              <LoadingOrb size={15} />
              Processing…
            </span>
          )}

          <button
            type="button"
            onClick={() => onDelete(document.id)}
            title="Delete document"
            aria-label={`Delete ${document.name}`}
            className="p-1.5 rounded-md text-[#929792] hover:text-[#b91c1c] hover:bg-[#fee2e2]/40 transition-colors cursor-pointer"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};
