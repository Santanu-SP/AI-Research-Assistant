import { useCallback, useEffect, useRef, useState } from 'react';
import { Document, DocumentListResponse } from '../types/document';
import { documentsService, getDocumentErrorMessage } from '../services/documents.service';
import { activeIngestionKey, useBackoffPolling } from './useBackoffPolling';

/** Which documents to list: one project's, or every document the user has. */
export type DocumentScope = { projectId: string } | { all: true };

export interface DocumentLibrary {
  documents: Document[];
  total: number;
  isLoading: boolean;
  error: string | null;
  readyCount: number;
  preparingCount: number;
  /** True when files are still being prepared but the quiet refresh has stopped. */
  refreshPaused: boolean;
  reload: () => void;
  /** Re-fetch without showing a loading state. */
  refresh: () => Promise<void>;
}

const LIST_LIMIT = 100;

const fetchScope = (scope: DocumentScope, search: string | undefined, signal?: AbortSignal) =>
  'projectId' in scope
    ? documentsService.getProjectDocuments(scope.projectId, { search, limit: LIST_LIMIT }, signal)
    : documentsService.getDocuments({ search, limit: LIST_LIMIT });

/**
 * Lists documents and keeps them current. While any file is still being
 * prepared it polls quietly with backoff, so a file becomes usable on its
 * own once the server has finished with it.
 */
export function useDocumentLibrary(scope: DocumentScope | null, search?: string): DocumentLibrary {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(Boolean(scope));
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const scopeKey = scope ? ('projectId' in scope ? `p:${scope.projectId}` : 'all') : '';
  const scopeRef = useRef(scope);
  scopeRef.current = scope;
  const term = search?.trim() || undefined;

  const reload = useCallback(() => setReloadKey((key) => key + 1), []);

  useEffect(() => {
    const current = scopeRef.current;
    if (!current) {
      setDocuments([]);
      setTotal(0);
      setIsLoading(false);
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setIsLoading(true);
    setError(null);
    fetchScope(current, term, controller.signal)
      .then((res: DocumentListResponse) => {
        if (controller.signal.aborted) return;
        setDocuments(res.items);
        setTotal(res.total);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setDocuments([]);
        setTotal(0);
        setError(getDocumentErrorMessage(err, 'Your documents could not be loaded.'));
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });
    return () => controller.abort();
  }, [scopeKey, term, reloadKey]);

  const refresh = useCallback(async () => {
    const current = scopeRef.current;
    if (!current) return;
    const res = await fetchScope(current, term);
    setDocuments(res.items);
    setTotal(res.total);
  }, [term]);

  const pendingKey = activeIngestionKey(documents);
  const { timedOut } = useBackoffPolling(Boolean(scope) && pendingKey !== '', refresh, `${scopeKey}:${pendingKey}`);

  const preparingCount = pendingKey ? pendingKey.split(',').length : 0;
  const readyCount = documents.filter((doc) => doc.status === 'indexed').length;

  return {
    documents,
    total,
    isLoading,
    error,
    readyCount,
    preparingCount,
    refreshPaused: timedOut,
    reload,
    refresh,
  };
}
