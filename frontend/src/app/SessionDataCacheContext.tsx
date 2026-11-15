import React, { createContext, useContext, useEffect, useMemo, useRef } from 'react';
import { Document } from '../types/document';
import { ModelsStatusResponse } from '../services/clientAi.service';
import type { DocumentsChangedDetail } from '../services/documents.service';

export interface CachedDocumentList {
  documents: Document[];
  total: number;
  fetchedAt: number;
  stale: boolean;
}

export interface CachedModelsStatus {
  data: ModelsStatusResponse;
  fetchedAt: number;
  stale: boolean;
}

export interface SessionDataCache {
  getDocuments: (key: string) => CachedDocumentList | undefined;
  setDocuments: (key: string, documents: Document[], total: number) => void;
  markDocumentsStale: () => void;
  subscribeDocuments: (listener: () => void) => () => void;
  getModelsStatus: () => CachedModelsStatus | undefined;
  setModelsStatus: (data: ModelsStatusResponse) => void;
  markModelsStatusStale: () => void;
}

const SessionDataCacheContext = createContext<SessionDataCache | null>(null);

const scopeMatchesUnfilteredKey = (key: string, projectId?: string | null): boolean => {
  if (key === 'all::') return true;
  return Boolean(projectId && key === `p:${projectId}::`);
};

/**
 * Keeps fetched workspace data (documents list per scope, model/quota status)
 * alive across route transitions within an authenticated session without
 * leaking state across sign-outs or isolated component tests.
 */
export const SessionDataCacheProvider: React.FC<React.PropsWithChildren> = ({ children }) => {
  const documentsMapRef = useRef<Map<string, CachedDocumentList>>(new Map());
  const documentListenersRef = useRef<Set<() => void>>(new Set());
  const modelsStatusRef = useRef<CachedModelsStatus | null>(null);

  useEffect(() => {
    const onDocumentsChanged = (event: Event) => {
      const detail = (event as CustomEvent<DocumentsChangedDetail>).detail;
      const map = documentsMapRef.current;

      map.forEach((entry, key) => {
        entry.stale = true;
        if (!detail) return;

        if (detail.action === 'delete' && detail.documentId) {
          const nextDocs = entry.documents.filter((doc) => doc.id !== detail.documentId);
          if (nextDocs.length !== entry.documents.length) {
            map.set(key, {
              ...entry,
              documents: nextDocs,
              total: Math.max(0, entry.total - 1),
              stale: true,
            });
          }
          return;
        }

        if (detail.document) {
          const updated = detail.document;
          const idx = entry.documents.findIndex((doc) => doc.id === updated.id);
          if (idx >= 0) {
            const nextDocs = entry.documents.slice();
            nextDocs[idx] = updated;
            map.set(key, { ...entry, documents: nextDocs, stale: true });
          } else if (
            detail.action === 'upload' &&
            scopeMatchesUnfilteredKey(key, updated.projectId)
          ) {
            map.set(key, {
              ...entry,
              documents: [updated, ...entry.documents],
              total: entry.total + 1,
              stale: true,
            });
          }
        }
      });

      documentListenersRef.current.forEach((listener) => listener());
    };

    const onUsageRefresh = () => {
      if (modelsStatusRef.current) {
        modelsStatusRef.current = { ...modelsStatusRef.current, stale: true };
      }
    };

    window.addEventListener('documents:changed', onDocumentsChanged);
    window.addEventListener('models-usage:refresh', onUsageRefresh);
    return () => {
      window.removeEventListener('documents:changed', onDocumentsChanged);
      window.removeEventListener('models-usage:refresh', onUsageRefresh);
    };
  }, []);

  const value = useMemo<SessionDataCache>(
    () => ({
      getDocuments: (key) => documentsMapRef.current.get(key),
      setDocuments: (key, documents, total) => {
        documentsMapRef.current.set(key, {
          documents,
          total,
          fetchedAt: Date.now(),
          stale: false,
        });
      },
      markDocumentsStale: () => {
        documentsMapRef.current.forEach((entry) => {
          entry.stale = true;
        });
      },
      subscribeDocuments: (listener) => {
        documentListenersRef.current.add(listener);
        return () => {
          documentListenersRef.current.delete(listener);
        };
      },
      getModelsStatus: () => modelsStatusRef.current ?? undefined,
      setModelsStatus: (data) => {
        modelsStatusRef.current = {
          data,
          fetchedAt: Date.now(),
          stale: false,
        };
      },
      markModelsStatusStale: () => {
        if (modelsStatusRef.current) {
          modelsStatusRef.current = { ...modelsStatusRef.current, stale: true };
        }
      },
    }),
    [],
  );

  return (
    <SessionDataCacheContext.Provider value={value}>
      {children}
    </SessionDataCacheContext.Provider>
  );
};

export const useSessionDataCache = (): SessionDataCache | null =>
  useContext(SessionDataCacheContext);
