import React, { useEffect, useRef } from 'react';
import {
  Check,
  ExternalLink,
  Globe,
  Loader2,
  Search,
  ShieldCheck,
  X,
} from 'lucide-react';
import { PrimaryButton } from '../common/PrimaryButton';
import { useSourceDiscovery } from '../../hooks/useSourceDiscovery';
import { DiscoveredSourceCandidate, DiscoveryScope } from '../../types/discovery';
import { Document } from '../../types/document';
import { useToast } from '../../app/ToastContext';

interface SourceDiscoveryDialogProps {
  isOpen: boolean;
  initialQuery?: string;
  projectId?: string | null;
  onClose: () => void;
  onImported: (documents: Document[]) => void;
}

const SCOPES: { id: DiscoveryScope; label: string }[] = [
  { id: 'all', label: 'All trusted' },
  { id: 'scholarly', label: 'Scholarly papers' },
  { id: 'web', label: 'Wikipedia & web' },
];

const PROVIDER_LABELS: Record<DiscoveredSourceCandidate['provider'], string> = {
  openalex: 'OpenAlex',
  crossref: 'Crossref',
  arxiv: 'arXiv',
  wikipedia: 'Wikipedia',
  news: 'News',
};

const TRUST_BADGE: Record<
  DiscoveredSourceCandidate['trustTier'],
  { label: string; className: string }
> = {
  'peer-reviewed': {
    label: 'Peer-reviewed',
    className: 'border-accent-line bg-accent-soft text-accent',
  },
  preprint: {
    label: 'Preprint',
    className: 'border-line bg-subtle text-ink-soft',
  },
  institutional: {
    label: 'Encyclopedia',
    className: 'border-line bg-subtle text-ink-soft',
  },
  'official-documentation': {
    label: 'Official docs',
    className: 'border-accent-line bg-accent-soft text-accent',
  },
  news: {
    label: 'News',
    className: 'border-line bg-subtle text-ink-soft',
  },
};

const contentLevelBadge = (candidate: DiscoveredSourceCandidate): string => {
  if (candidate.openAccessPdfUrl || candidate.contentLevel === 'full_text') {
    return 'Open-access PDF';
  }
  if (candidate.contentLevel === 'web_page') {
    return 'Full article';
  }
  return 'Abstract only';
};

export const SourceDiscoveryDialog: React.FC<SourceDiscoveryDialogProps> = ({
  isOpen,
  initialQuery = '',
  projectId = null,
  onClose,
  onImported,
}) => {
  const { addToast } = useToast();
  const discovery = useSourceDiscovery(initialQuery);
  const inputRef = useRef<HTMLInputElement>(null);
  const wasOpenRef = useRef(false);
  const actionsRef = useRef({ reset: discovery.reset, search: discovery.search });
  actionsRef.current = { reset: discovery.reset, search: discovery.search };

  useEffect(() => {
    if (!isOpen) {
      wasOpenRef.current = false;
      return;
    }
    if (wasOpenRef.current) return;
    wasOpenRef.current = true;
    actionsRef.current.reset(initialQuery);
    const trimmed = initialQuery.trim();
    if (trimmed.length >= 2) {
      void actionsRef.current.search(trimmed, 'all');
    }
    const timer = window.setTimeout(() => inputRef.current?.focus(), 0);
    return () => window.clearTimeout(timer);
  }, [isOpen, initialQuery]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !discovery.isImporting) onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [isOpen, discovery.isImporting, onClose]);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void discovery.search();
  };

  const handleScopeChange = (nextScope: DiscoveryScope) => {
    discovery.setScope(nextScope);
    if (discovery.query.trim().length >= 2) {
      void discovery.search(discovery.query, nextScope);
    }
  };

  const handleImport = async () => {
    const res = await discovery.importSelected({ projectId, fetchFullText: true });
    if (!res || res.documents.length === 0) return;

    onImported(res.documents);
    const failedCount = res.failed.length;
    addToast({
      type: failedCount > 0 ? 'warning' : 'success',
      title: 'Sources ready',
      description:
        failedCount > 0
          ? `Added ${res.documents.length} source${res.documents.length === 1 ? '' : 's'} (${failedCount} could not be extracted).`
          : `Added ${res.documents.length} verified source${res.documents.length === 1 ? '' : 's'} to search.`,
    });
    onClose();
  };

  const selectedCount = discovery.selectedIds.size;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 overlay-enter"
      onMouseDown={() => {
        if (!discovery.isImporting) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="source-discovery-title"
        onMouseDown={(e) => e.stopPropagation()}
        className="flex max-h-[min(680px,calc(100vh-2rem))] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-line bg-panel shadow-xl dialog-enter"
      >
        <header className="flex items-start justify-between gap-3 border-b border-line px-6 py-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-accent shrink-0" />
              <h3 id="source-discovery-title" className="text-base font-semibold text-ink">
                Discover trusted sources
              </h3>
            </div>
            <p className="mt-0.5 text-xs text-ink-soft">
              Searches curated scholarly and encyclopedia APIs (OpenAlex, Crossref, arXiv, Wikipedia) with provenance &amp; SSRF checks.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={discovery.isImporting}
            aria-label="Close discovery dialog"
            className="rounded-md p-1.5 text-ink-muted transition-colors hover:bg-subtle hover:text-ink disabled:opacity-50"
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="space-y-3 border-b border-line bg-canvas/60 px-6 py-3.5">
          <form onSubmit={handleSubmit} role="search" className="flex gap-2">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" />
              <input
                ref={inputRef}
                type="search"
                aria-label="Search trusted sources"
                value={discovery.query}
                onChange={(e) => discovery.setQuery(e.target.value)}
                placeholder="Search papers, DOIs, algorithms, or concepts…"
                className="field h-9 w-full pl-9 pr-3 text-[13px]"
              />
            </div>
            <PrimaryButton type="submit" disabled={discovery.isSearching || discovery.query.trim().length < 2}>
              {discovery.isSearching ? 'Searching…' : 'Search'}
            </PrimaryButton>
          </form>

          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="inline-flex rounded-lg border border-line bg-panel p-0.5 text-xs font-medium">
              {SCOPES.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => handleScopeChange(tab.id)}
                  className={`rounded-md px-2.5 py-1 transition-colors ${
                    discovery.scope === tab.id
                      ? 'bg-solid text-on-solid shadow-xs'
                      : 'text-ink-soft hover:text-ink'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {discovery.items.length > 0 && (
              <div className="flex items-center gap-2 text-xs">
                <button
                  type="button"
                  onClick={discovery.selectAll}
                  className="font-medium text-accent hover:underline"
                >
                  Select all
                </button>
                {selectedCount > 0 && (
                  <button
                    type="button"
                    onClick={discovery.clearSelection}
                    className="text-ink-muted hover:text-ink"
                  >
                    Clear
                  </button>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="min-h-[220px] flex-1 overflow-y-auto px-6 py-4">
          {discovery.searchError && (
            <div className="mb-3 rounded-lg border border-danger-line bg-danger-soft px-3.5 py-2.5 text-xs text-danger">
              {discovery.searchError}
            </div>
          )}

          {discovery.importError && (
            <div className="mb-3 rounded-lg border border-danger-line bg-danger-soft px-3.5 py-2.5 text-xs text-danger">
              {discovery.importError}
            </div>
          )}

          {discovery.providerErrors.length > 0 && (
            <div className="mb-3 rounded-lg border border-line bg-subtle px-3 py-2 text-[11px] text-ink-muted">
              Note: {discovery.providerErrors.join('; ')}.
            </div>
          )}

          {discovery.isSearching ? (
            <div className="flex flex-col items-center justify-center py-14 text-center">
              <Loader2 className="h-6 w-6 animate-spin text-accent" />
              <p className="mt-2.5 text-[13px] font-medium text-ink">
                Querying curated academic &amp; encyclopedia APIs…
              </p>
              <p className="mt-1 text-xs text-ink-muted">
                Deduplicating by DOI and checking open-access availability.
              </p>
            </div>
          ) : discovery.items.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-14 text-center">
              <Globe className="h-7 w-7 text-ink-muted" strokeWidth={1.5} />
              <p className="mt-3 text-sm font-medium text-ink">
                {discovery.hasSearched
                  ? 'No trusted sources matched that query'
                  : 'Search verified academic and encyclopedia sources'}
              </p>
              <p className="mt-1 max-w-md text-xs leading-relaxed text-ink-muted">
                {discovery.hasSearched
                  ? 'Try broader keywords, switch to All trusted, or upload your own files directly.'
                  : 'Every discovered paper shows its DOI/source, citation count, and whether open-access full text or abstract only is available.'}
              </p>
            </div>
          ) : (
            <ul className="space-y-2.5" aria-label="Discovered trusted sources">
              {discovery.items.map((item) => {
                const selected = discovery.selectedIds.has(item.candidateId);
                const badge = TRUST_BADGE[item.trustTier];
                const contentBadge = contentLevelBadge(item);
                const externalHref = item.openAccessPdfUrl || item.url;
                return (
                  <li key={item.candidateId}>
                    <div
                      onClick={() => discovery.toggleSelected(item.candidateId)}
                      role="checkbox"
                      aria-checked={selected}
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === ' ' || e.key === 'Enter') {
                          e.preventDefault();
                          discovery.toggleSelected(item.candidateId);
                        }
                      }}
                      className={`group flex cursor-pointer items-start gap-3 rounded-lg border p-3.5 transition-colors ${
                        selected
                          ? 'border-accent bg-accent-soft/40'
                          : 'border-line bg-canvas/40 hover:border-line-strong hover:bg-subtle/50'
                      }`}
                    >
                      <span
                        aria-hidden="true"
                        className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors ${
                          selected
                            ? 'border-accent bg-solid text-on-solid'
                            : 'border-line-strong bg-panel group-hover:border-ink-muted'
                        }`}
                      >
                        {selected && <Check className="h-3 w-3" strokeWidth={2.5} />}
                      </span>

                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                          <span className={`rounded border px-1.5 py-0.5 font-medium ${badge.className}`}>
                            {item.provider === 'news' && item.publisher
                              ? `${item.publisher} · News`
                              : `${PROVIDER_LABELS[item.provider]} · ${badge.label}`}
                          </span>
                          <span className="rounded border border-line bg-panel px-1.5 py-0.5 text-ink-soft">
                            {contentBadge}
                          </span>
                          {item.alreadyInLibrary && (
                            <span className="rounded border border-accent-line bg-panel px-1.5 py-0.5 font-medium text-accent">
                              In library
                            </span>
                          )}
                          {item.citationCount !== null && item.citationCount > 0 && (
                            <span className="text-ink-muted tabular-nums">
                              {item.citationCount.toLocaleString()} cited
                            </span>
                          )}
                        </div>

                        <div className="mt-1.5 flex items-start justify-between gap-2">
                          <h4 className="text-[13.5px] font-semibold leading-snug text-ink">
                            {item.title}
                          </h4>
                          <a
                            href={externalHref}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            aria-label={`Open ${item.title} in new tab`}
                            className="shrink-0 rounded p-1 text-ink-muted hover:bg-subtle hover:text-ink"
                          >
                            <ExternalLink className="h-3.5 w-3.5" />
                          </a>
                        </div>

                        <p className="mt-0.5 truncate text-xs text-ink-soft">
                          {[
                            item.authors.slice(0, 3).join(', ') + (item.authors.length > 3 ? ' et al.' : ''),
                            item.publisher,
                            item.publicationYear,
                            item.doi ? `DOI: ${item.doi}` : null,
                          ]
                            .filter(Boolean)
                            .join(' · ') || item.url}
                        </p>

                        {item.abstract && (
                          <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-ink-muted">
                            {item.abstract}
                          </p>
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <footer className="flex items-center justify-between gap-3 border-t border-line bg-canvas px-6 py-3.5">
          <span className="text-xs tabular-nums text-ink-muted">
            {selectedCount === 0
              ? 'Select sources to import & verify'
              : `${selectedCount} selected (max 8 per batch)`}
          </span>
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={onClose}
              disabled={discovery.isImporting}
              className="rounded-md px-3.5 py-2 text-xs font-medium text-ink-soft transition-colors hover:bg-panel hover:text-ink disabled:opacity-50"
            >
              Cancel
            </button>
            <PrimaryButton
              onClick={() => void handleImport()}
              disabled={selectedCount === 0 || selectedCount > 8 || discovery.isImporting}
              isLoading={discovery.isImporting}
            >
              {discovery.isImporting
                ? 'Importing…'
                : selectedCount > 0
                  ? `Import ${selectedCount} source${selectedCount === 1 ? '' : 's'}`
                  : 'Import sources'}
            </PrimaryButton>
          </div>
        </footer>
      </div>
    </div>
  );
};
