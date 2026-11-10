import { useCallback, useEffect, useRef, useState } from 'react';
import { Document, DocumentListResponse } from '../types/document';
import {
  ProjectDocumentListParams,
  documentsService,
  getDocumentErrorMessage,
} from '../services/documents.service';
import { activeIngestionKey, useBackoffPolling } from './useBackoffPolling';

export interface UseProjectDocumentsResult {
  documents: Document[];
  total: number;
  isLoading: boolean;
  error: string | null;
  /** True when documents are still processing but polling has given up. */
  pollingStopped: boolean;
  reload: () => void;
}

export function useProjectDocuments(
  projectId: string | null,
  params?: ProjectDocumentListParams
): UseProjectDocumentsResult {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const search = params?.search;
  const status = params?.status;
  const type = params?.type;

  const reload = useCallback(() => {
    setReloadKey((k) => k + 1);
  }, []);

  // Cancel the in-flight list when the project changes so a slow response
  // cannot replace the new project's documents.
  useEffect(() => {
    if (!projectId) {
      setDocuments([]);
      setTotal(0);
      setError(null);
      setIsLoading(false);
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsLoading(true);
    setError(null);

    documentsService
      .getProjectDocuments(projectId, { search, status, type }, controller.signal)
      .then((res: DocumentListResponse) => {
        if (controller.signal.aborted) return;
        setDocuments(res.items);
        setTotal(res.total);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setDocuments([]);
        setTotal(0);
        setError(
          getDocumentErrorMessage(err, 'Failed to load project documents.')
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });

    return () => {
      controller.abort();
    };
  }, [projectId, reloadKey, search, status, type]);

  const refreshSilently = useCallback(async () => {
    if (!projectId) return;
    const res = await documentsService.getProjectDocuments(projectId, { search, status, type });
    setDocuments(res.items);
    setTotal(res.total);
  }, [projectId, search, status, type]);

  // Poll with backoff while any document is uploaded or processing.
  const pendingKey = activeIngestionKey(documents);
  const { timedOut } = useBackoffPolling(
    Boolean(projectId) && pendingKey !== '',
    refreshSilently,
    `${projectId}:${pendingKey}`,
  );

  return { documents, total, isLoading, error, pollingStopped: timedOut, reload };
}
