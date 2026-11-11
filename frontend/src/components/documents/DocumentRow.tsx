import React from 'react';
import { FileText, RotateCcw, Trash2 } from 'lucide-react';
import { Document } from '../../types/document';
import { StatusBadge } from '../common/StatusBadge';
import { LoadingOrb } from '../common/LoadingOrb';

interface DocumentRowProps {
  document: Document;
  onDelete: (id: string) => void;
  onOpen: (document: Document) => void;
  onRetry?: (id: string) => void;
  isRetrying?: boolean;
}

export const DocumentRow: React.FC<DocumentRowProps> = ({
  document,
  onDelete,
  onOpen,
  onRetry,
  isRetrying = false,
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
    <div className="p-4 bg-panel border border-line rounded-lg hover:border-line-strong hover:shadow-xs transition-all duration-150 flex flex-col sm:flex-row sm:items-center justify-between gap-3 group">
      <div className="flex items-start gap-3 min-w-0">
        <div
          className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 border ${
            isPdf
              ? 'bg-danger-soft text-danger border-danger-line'
              : isDocx
              ? 'bg-info-soft text-info border-info-line'
              : 'bg-subtle text-ink-soft border-line'
          }`}
        >
          <FileText className="w-5 h-5 stroke-[1.75]" />
        </div>

        <div className="min-w-0 flex-1">
          <h4 className="text-[13.5px] font-semibold text-ink truncate leading-tight group-hover:text-accent transition-colors">
            {document.title || document.name}
          </h4>
          
          {document.title && document.title !== document.name && (
            <div className="text-[11px] text-ink-muted truncate mt-0.5">
              {document.name}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-1.5 mt-1.5 text-xs text-ink-soft">
            <span className="font-medium text-ink uppercase">{document.type}</span>
            <span className="text-ink-muted">·</span>
            <span>{formatSize(document.size)}</span>
            <span className="text-ink-muted">·</span>
            <span>{new Date(document.uploadedAt || document.createdAt).toLocaleDateString()}</span>
            
            {document.pageCount ? (
              <>
                <span className="text-ink-muted">·</span>
                <span>{document.pageCount} pages</span>
              </>
            ) : null}
            
            {document.authors && document.authors.length > 0 ? (
              <>
                <span className="text-ink-muted">·</span>
                <span className="truncate max-w-[180px]" title={document.authors.join(', ')}>
                  By {document.authors.join(', ')}
                </span>
              </>
            ) : null}

            {document.doi ? (
              <>
                <span className="text-ink-muted">·</span>
                <span className="truncate max-w-[120px]" title={document.doi}>
                  DOI: {document.doi}
                </span>
              </>
            ) : null}
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between sm:justify-end gap-3 shrink-0 pt-2 sm:pt-0 border-t sm:border-t-0 border-line">
        <StatusBadge 
          status={document.status} 
          title={document.status === 'failed' && document.processingError ? document.processingError : undefined}
        />

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onOpen(document)}
            className="text-xs font-medium text-accent bg-accent-soft hover:bg-accent-muted border border-accent-line px-3 py-1.5 rounded-md transition-colors cursor-pointer"
          >
            View details
          </button>

          {document.status === 'failed' && onRetry && (
            <button
              type="button"
              onClick={() => onRetry(document.id)}
              disabled={isRetrying}
              aria-label={`Retry processing ${document.name}`}
              className="inline-flex items-center gap-1 text-xs font-medium text-accent bg-panel hover:bg-accent-soft border border-accent-line px-2.5 py-1.5 rounded-md transition-colors cursor-pointer disabled:opacity-50"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${isRetrying ? 'animate-spin' : ''}`} />
              Retry
            </button>
          )}

          {document.status === 'processing' && (
            <span className="inline-flex items-center gap-1.5 text-xs text-warning font-medium px-2 py-1">
              <LoadingOrb size={15} />
              Processing…
            </span>
          )}

          <button
            type="button"
            onClick={() => onDelete(document.id)}
            title="Delete document"
            aria-label={`Delete ${document.name}`}
            className="p-1.5 rounded-md text-ink-muted hover:text-danger hover:bg-danger-soft transition-colors cursor-pointer"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};
