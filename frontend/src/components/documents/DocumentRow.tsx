import React from 'react';
import { FileText, Trash2 } from 'lucide-react';
import { Document } from '../../types/document';
import { StatusBadge } from '../common/StatusBadge';
import { LoadingOrb } from '../common/LoadingOrb';

interface DocumentRowProps {
  document: Document;
  onDelete: (id: string) => void;
  onOpen: (document: Document) => void;
}

export const DocumentRow: React.FC<DocumentRowProps> = ({
  document,
  onDelete,
  onOpen,
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

        <div className="min-w-0 flex-1">
          <h4 className="text-[13.5px] font-semibold text-[#181a18] truncate leading-tight group-hover:text-[#163328] transition-colors">
            {document.title || document.name}
          </h4>
          
          {document.title && document.title !== document.name && (
            <div className="text-[11px] text-[#929792] truncate mt-0.5">
              {document.name}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-1.5 mt-1.5 text-xs text-[#6b706c]">
            <span className="font-medium text-[#181a18] uppercase">{document.type}</span>
            <span className="text-[#929792]">·</span>
            <span>{formatSize(document.size)}</span>
            <span className="text-[#929792]">·</span>
            <span>{new Date(document.uploadedAt || document.createdAt).toLocaleDateString()}</span>
            
            {document.pageCount ? (
              <>
                <span className="text-[#929792]">·</span>
                <span>{document.pageCount} pages</span>
              </>
            ) : null}
            
            {document.authors && document.authors.length > 0 ? (
              <>
                <span className="text-[#929792]">·</span>
                <span className="truncate max-w-[180px]" title={document.authors.join(', ')}>
                  By {document.authors.join(', ')}
                </span>
              </>
            ) : null}

            {document.doi ? (
              <>
                <span className="text-[#929792]">·</span>
                <span className="truncate max-w-[120px]" title={document.doi}>
                  DOI: {document.doi}
                </span>
              </>
            ) : null}
          </div>
        </div>
      </div>

      {/* Status & Actions */}
      <div className="flex items-center justify-between sm:justify-end gap-3 shrink-0 pt-2 sm:pt-0 border-t sm:border-t-0 border-[#f5f5f2]">
        <StatusBadge 
          status={document.status} 
          title={document.status === 'failed' && document.processingError ? document.processingError : undefined}
        />

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onOpen(document)}
            className="text-xs font-medium text-[#163328] bg-[#f1f6f3] hover:bg-[#e4eee7] border border-[#d8e5df] px-3 py-1.5 rounded-md transition-colors cursor-pointer"
          >
            View details
          </button>

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
