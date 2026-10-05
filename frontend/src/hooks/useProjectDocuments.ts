/**
 * useProjectDocuments: Fetch and poll project documents for a given projectId.
 *
 * Uses AbortController to cancel stale in-flight requests when projectId changes,
 * preventing stale Project A data from appearing in Project B's UI.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Document, DocumentListResponse } from '../types/document';
import {
  ProjectDocumentListParams,
  documentsService,
} from '../services/documents.service';
import { getDocumentErrorMessage } from '../services/documents.service';

const POLL_INTERVAL_MS = 4000;

export interface UseProjectDocumentsResult {
  documents: Document[];
  total: number;
  isLoading: boolean;
  error: string | null;
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

  const reload = useCallback(() => {
    setReloadKey((k) => k + 1);
  }, []);

  // Primary fetch – cancels stale requests on projectId or param change
  useEffect(() => {
    if (!projectId) {
      setDocuments([]);
      setTotal(0);
      setError(null);
      setIsLoading(false);
      return;
    }

    // Abort previous request
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsLoading(true);
    setError(null);

    documentsService
      .getProjectDocuments(projectId, params, controller.signal)
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, reloadKey, params?.search, params?.status, params?.type]);

  // Polling while any document is in UPLOADED or PROCESSING state
  useEffect(() => {
    if (!projectId) return;
    const hasActiveIngestion = documents.some(
      (d) => d.status === 'uploaded' || d.status === 'processing'
    );
    if (!hasActiveIngestion) return;

    const intervalId = window.setInterval(() => {
      void documentsService
        .getProjectDocuments(projectId, params)
        .then((res: DocumentListResponse) => {
          setDocuments(res.items);
          setTotal(res.total);
        })
        .catch(() => {
          // Silent polling failure – do not overwrite the visible error
        });
    }, POLL_INTERVAL_MS);

    return () => window.clearInterval(intervalId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, documents]);

  return { documents, total, isLoading, error, reload };
}
