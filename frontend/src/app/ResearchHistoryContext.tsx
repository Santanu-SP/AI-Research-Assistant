import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { researchService } from '../services/research.service';
import { ResearchResponse } from '../types/research';

const PAGE_SIZE = 100;
const MAX_ITEMS = 500;

interface ResearchHistoryState {
  items: ResearchResponse[];
  total: number;
  loading: boolean;
  error: boolean;
  /** True when every research item the user has is loaded, so filtering can stay client-side. */
  complete: boolean;
  reload: () => void;
  rename: (id: string, title: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
  /** Brings back a research removed with ``remove``. */
  restore: (id: string) => Promise<void>;
}

const ResearchHistoryContext = createContext<ResearchHistoryState | null>(null);

const byUpdatedDesc = (a: ResearchResponse, b: ResearchResponse) =>
  new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime();

export const ResearchHistoryProvider: React.FC<React.PropsWithChildren> = ({ children }) => {
  const [items, setItems] = useState<ResearchResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setError(false);
    try {
      const collected: ResearchResponse[] = [];
      let offset = 0;
      let grandTotal = 0;
      do {
        const page = await researchService.listResearch({ limit: PAGE_SIZE, offset });
        collected.push(...page.items);
        grandTotal = page.total;
        offset += page.items.length;
        if (page.items.length === 0) break;
      } while (offset < grandTotal && collected.length < MAX_ITEMS);
      if (id !== requestId.current) return;
      setItems(collected.sort(byUpdatedDesc));
      setTotal(grandTotal);
    } catch {
      if (id === requestId.current) setError(true);
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, []);

  // Load once on mount and refresh on explicit mutations rather than every route transition.
  useEffect(() => {
    void load();
    const onRefresh = () => void load();
    window.addEventListener('research-history:refresh', onRefresh);
    return () => window.removeEventListener('research-history:refresh', onRefresh);
  }, [load]);

  const reload = useCallback(() => void load(), [load]);

  const rename = useCallback(async (id: string, title: string) => {
    const updated = await researchService.updateResearch(id, { title });
    setItems((current) => current.map((item) => (item.id === id ? { ...item, ...updated } : item)));
  }, []);

  const remove = useCallback(async (id: string) => {
    await researchService.archiveResearch(id);
    setItems((current) => current.filter((item) => item.id !== id));
    setTotal((current) => Math.max(0, current - 1));
  }, []);

  const restore = useCallback(async (id: string) => {
    const restored = await researchService.restoreResearch(id);
    let added = false;
    setItems((current) => {
      if (current.some((item) => item.id === id)) return current;
      added = true;
      return [...current, restored].sort(byUpdatedDesc);
    });
    if (added) setTotal((current) => current + 1);
  }, []);

  const value = useMemo(
    () => ({
      items,
      total,
      loading,
      error,
      complete: items.length >= total,
      reload,
      rename,
      remove,
      restore,
    }),
    [items, total, loading, error, reload, rename, remove, restore],
  );

  return <ResearchHistoryContext.Provider value={value}>{children}</ResearchHistoryContext.Provider>;
};

export const useResearchHistory = (): ResearchHistoryState | null => useContext(ResearchHistoryContext);

export type HistoryGroup = { label: string; items: ResearchResponse[] };

/** Buckets research by when it was last updated, newest first. */
export const groupByDate = (items: ResearchResponse[], now = new Date()): HistoryGroup[] => {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const day = 24 * 60 * 60 * 1000;
  const buckets: HistoryGroup[] = [
    { label: 'Today', items: [] },
    { label: 'Yesterday', items: [] },
    { label: 'Previous 7 days', items: [] },
    { label: 'Previous 30 days', items: [] },
    { label: 'Older', items: [] },
  ];
  for (const item of items) {
    const time = new Date(item.updatedAt).getTime();
    const index =
      time >= startOfToday
        ? 0
        : time >= startOfToday - day
          ? 1
          : time >= startOfToday - 7 * day
            ? 2
            : time >= startOfToday - 30 * day
              ? 3
              : 4;
    buckets[index].items.push(item);
  }
  return buckets.filter((bucket) => bucket.items.length > 0);
};
