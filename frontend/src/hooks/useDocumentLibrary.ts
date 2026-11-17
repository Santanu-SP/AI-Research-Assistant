import { useCallback, useEffect, useRef, useState } from 'react';
import { Document, DocumentKind, DocumentListResponse } from '../types/document';
import { documentsService, getDocumentErrorMessage } from '../services/documents.service';
import { activeIngestionKey, useBackoffPolling } from './useBackoffPolling';
import { useSessionDataCache } from '../app/SessionDataCacheContext';

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
const DOCUMENT_CACHE_TTL_MS = 30_000;

const documentsListEqual = (a: Document[], b: Document[]): boolean => {
  if (a === b) return true;
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) {
    const left = a[i];
    const right = b[i];
    if (
      left.id !== right.id ||
      left.name !== right.name ||
      left.status !== right.status ||
      left.ingestionStatus !== right.ingestionStatus ||
      left.updatedAt !== right.updatedAt ||
      left.processingError !== right.processingError ||
      left.processingStage !== right.processingStage ||
      left.processingProgress !== right.processingProgress ||
      left.projectId !== right.projectId ||
      left.projectName !== right.projectName ||
      left.usedInCount !== right.usedInCount ||
      (left.usedIn ?? []).map((u) => u.id).join() !== (right.usedIn ?? []).map((u) => u.id).join() ||
      left.size !== right.size ||
      left.chunkCount !== right.chunkCount
    ) {
      return false;
    }
  }
  return true;
};

const fetchScope = (
  scope: DocumentScope,
  search: string | undefined,
  kind: DocumentKind | undefined,
  signal?: AbortSignal,
) =>
  'projectId' in scope
    ? documentsService.getProjectDocuments(scope.projectId, { search, kind, limit: LIST_LIMIT }, signal)
    : documentsService.getDocuments({ search, kind, limit: LIST_LIMIT }, signal);

/**
 * Lists documents and keeps them current. While any file is still being
 * prepared it polls quietly with backoff, so a file becomes usable on its
 * own once the server has finished with it.
 */
export function useDocumentLibrary(
  scope: DocumentScope | null,
  search?: string,
  kind?: DocumentKind,
): DocumentLibrary {
  const cache = useSessionDataCache();
  const scopeKey = scope ? ('projectId' in scope ? `p:${scope.projectId}` : 'all') : '';
  const term = search?.trim() || undefined;
  const cacheKey = scopeKey ? `${scopeKey}::${term ?? ''}${kind ? `::${kind}` : ''}` : '';
  const initialCached = cacheKey && cache ? cache.getDocuments(cacheKey) : undefined;

  const [documents, setDocuments] = useState<Document[]>(() => initialCached?.documents ?? []);
  const [total, setTotal] = useState(() => initialCached?.total ?? 0);
  const [isLoading, setIsLoading] = useState(() => Boolean(scope) && initialCached === undefined);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const forceReloadRef = useRef(false);
  const loadedKeyRef = useRef<string | null>(initialCached ? cacheKey : null);
  const abortRef = useRef<AbortController | null>(null);
  const scopeRef = useRef(scope);
  scopeRef.current = scope;

  const reload = useCallback(() => {
    forceReloadRef.current = true;
    setReloadKey((key) => key + 1);
  }, []);

  useEffect(() => {
    if (!cache || !cacheKey) return;
    return cache.subscribeDocuments(() => {
      const updated = cache.getDocuments(cacheKey);
      if (!updated) return;
      setDocuments((prev) => (documentsListEqual(prev, updated.documents) ? prev : updated.documents));
      setTotal(updated.total);
    });
  }, [cache, cacheKey]);

  useEffect(() => {
    const current = scopeRef.current;
    if (!current || !cacheKey) {
      loadedKeyRef.current = null;
      setDocuments([]);
      setTotal(0);
      setIsLoading(false);
      return;
    }

    const cached = cache?.getDocuments(cacheKey);
    const hasSameKeyLoaded = loadedKeyRef.current === cacheKey;

    if (cached) {
      setDocuments((prev) => (documentsListEqual(prev, cached.documents) ? prev : cached.documents));
      setTotal(cached.total);
      setIsLoading(false);
      setError(null);
      loadedKeyRef.current = cacheKey;

      const hasPending = activeIngestionKey(cached.documents) !== '';
      const isFresh = !cached.stale && Date.now() - cached.fetchedAt < DOCUMENT_CACHE_TTL_MS;
      if (!forceReloadRef.current && isFresh && !hasPending) {
        return;
      }
    } else if (!hasSameKeyLoaded) {
      setDocuments([]);
      setTotal(0);
      setIsLoading(true);
    }

    setError(null);
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    fetchScope(current, term, kind, controller.signal)
      .then((res: DocumentListResponse) => {
        if (controller.signal.aborted) return;
        forceReloadRef.current = false;
        cache?.setDocuments(cacheKey, res.items, res.total);
        loadedKeyRef.current = cacheKey;
        setDocuments((prev) => (documentsListEqual(prev, res.items) ? prev : res.items));
        setTotal(res.total);
        setError(null);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        forceReloadRef.current = false;
        if (!cached && !hasSameKeyLoaded) {
          setDocuments([]);
          setTotal(0);
        }
        setError(getDocumentErrorMessage(err, 'Your files could not be loaded.'));
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });
    return () => controller.abort();
  }, [scopeKey, term, kind, reloadKey, cacheKey, cache]);

  const refresh = useCallback(async () => {
    const current = scopeRef.current;
    if (!current || !cacheKey) return;
    const res = await fetchScope(current, term, kind);
    cache?.setDocuments(cacheKey, res.items, res.total);
    loadedKeyRef.current = cacheKey;
    setDocuments((prev) => (documentsListEqual(prev, res.items) ? prev : res.items));
    setTotal(res.total);
  }, [cache, cacheKey, term, kind]);

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
