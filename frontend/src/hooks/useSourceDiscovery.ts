import { useCallback, useEffect, useRef, useState } from 'react';
import { discoveryService, getDiscoveryErrorMessage } from '../services/discovery.service';
import {
  DiscoveredSourceCandidate,
  DiscoveryImportResponse,
  DiscoveryScope,
} from '../types/discovery';

export interface SourceDiscoveryState {
  query: string;
  setQuery: (query: string) => void;
  scope: DiscoveryScope;
  setScope: (scope: DiscoveryScope) => void;
  items: DiscoveredSourceCandidate[];
  providerErrors: string[];
  selectedIds: Set<string>;
  isSearching: boolean;
  isImporting: boolean;
  searchError: string | null;
  importError: string | null;
  hasSearched: boolean;
  search: (overrideQuery?: string, overrideScope?: DiscoveryScope) => Promise<void>;
  toggleSelected: (candidateId: string) => void;
  selectAll: () => void;
  clearSelection: () => void;
  importSelected: (options?: {
    projectId?: string | null;
    fetchFullText?: boolean;
  }) => Promise<DiscoveryImportResponse | null>;
  reset: (initialQuery?: string) => void;
}

export function useSourceDiscovery(initialQuery = ''): SourceDiscoveryState {
  const [query, setQuery] = useState(initialQuery);
  const [scope, setScope] = useState<DiscoveryScope>('all');
  const [items, setItems] = useState<DiscoveredSourceCandidate[]>([]);
  const [providerErrors, setProviderErrors] = useState<string[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [isSearching, setIsSearching] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  const searchAbortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      searchAbortRef.current?.abort();
    };
  }, []);

  const search = useCallback(
    async (overrideQuery?: string, overrideScope?: DiscoveryScope) => {
      const targetQuery = (overrideQuery ?? query).trim();
      const targetScope = overrideScope ?? scope;
      if (targetQuery.length < 2) {
        setSearchError('Enter at least 2 characters to search trusted sources.');
        return;
      }

      searchAbortRef.current?.abort();
      const controller = new AbortController();
      searchAbortRef.current = controller;

      setIsSearching(true);
      setSearchError(null);
      setImportError(null);

      try {
        const res = await discoveryService.search(
          { query: targetQuery, scope: targetScope },
          controller.signal,
        );
        if (!mountedRef.current || controller.signal.aborted) return;
        setItems(res.items);
        setProviderErrors(res.providerErrors ?? []);
        setHasSearched(true);
        // Pre-select nothing by default so users choose intentionally; drop stale ids.
        setSelectedIds((prev) => {
          const available = new Set(res.items.map((item) => item.candidateId));
          const retained = new Set([...prev].filter((id) => available.has(id)));
          return retained;
        });
      } catch (err) {
        if (controller.signal.aborted || !mountedRef.current) return;
        if (err instanceof DOMException && err.name === 'AbortError') return;
        setSearchError(getDiscoveryErrorMessage(err, 'Could not search external sources.'));
      } finally {
        if (!controller.signal.aborted && mountedRef.current) {
          setIsSearching(false);
        }
      }
    },
    [query, scope],
  );

  const toggleSelected = useCallback((candidateId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(candidateId)) next.delete(candidateId);
      else next.add(candidateId);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    setSelectedIds(new Set(items.map((item) => item.candidateId)));
  }, [items]);

  const clearSelection = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

  const importSelected = useCallback(
    async (options: { projectId?: string | null; fetchFullText?: boolean } = {}) => {
      const chosen = items.filter((item) => selectedIds.has(item.candidateId));
      if (chosen.length === 0 || isImporting) return null;

      setIsImporting(true);
      setImportError(null);
      try {
        const res = await discoveryService.importSources(chosen, options);
        if (!mountedRef.current) return res;
        if (res.documents.length === 0 && res.failed.length > 0) {
          setImportError(res.failed[0].reason || 'Selected sources could not be imported.');
        } else {
          // Mark imported candidates cleanly in the list.
          const byTitle = new Map(res.documents.map((doc) => [doc.title || doc.name, doc.id]));
          setItems((prev) =>
            prev.map((item) =>
              byTitle.has(item.title)
                ? {
                    ...item,
                    alreadyInLibrary: true,
                    existingDocumentId: byTitle.get(item.title) ?? item.existingDocumentId,
                  }
                : item,
            ),
          );
          setSelectedIds(new Set());
        }
        return res;
      } catch (err) {
        if (!mountedRef.current) return null;
        setImportError(getDiscoveryErrorMessage(err, 'Could not import the selected sources.'));
        return null;
      } finally {
        if (mountedRef.current) {
          setIsImporting(false);
        }
      }
    },
    [items, selectedIds, isImporting],
  );

  const reset = useCallback((nextInitial = '') => {
    searchAbortRef.current?.abort();
    setQuery(nextInitial);
    setScope('all');
    setItems([]);
    setProviderErrors([]);
    setSelectedIds(new Set());
    setIsSearching(false);
    setIsImporting(false);
    setSearchError(null);
    setImportError(null);
    setHasSearched(false);
  }, []);

  return {
    query,
    setQuery,
    scope,
    setScope,
    items,
    providerErrors,
    selectedIds,
    isSearching,
    isImporting,
    searchError,
    importError,
    hasSearched,
    search,
    toggleSelected,
    selectAll,
    clearSelection,
    importSelected,
    reset,
  };
}
