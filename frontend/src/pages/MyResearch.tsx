import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Clock, Search } from 'lucide-react';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';
import { CenteredLoadingState } from '../components/common/LoadingState';
import { PrimaryButton } from '../components/common/PrimaryButton';
import { StatusBadge } from '../components/common/StatusBadge';
import { TopBar } from '../components/layout/TopBar';
import {
  getResearchErrorMessage,
  researchService,
} from '../services/research.service';
import { ResearchResponse, ResearchStatus } from '../types/research';

const PAGE_SIZE = 20;

const formatUpdatedAt = (value: string): string =>
  new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: new Date(value).getFullYear() === new Date().getFullYear() ? undefined : 'numeric',
  }).format(new Date(value));

export const MyResearchPage: React.FC = () => {
  const navigate = useNavigate();
  const [researchList, setResearchList] = useState<ResearchResponse[]>([]);
  const [totalResearch, setTotalResearch] = useState(0);
  const [domainOptions, setDomainOptions] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDomain, setSelectedDomain] = useState('all');
  const [selectedStatus, setSelectedStatus] = useState('all');
  const [offset, setOffset] = useState(0);
  const [retryKey, setRetryKey] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setLoadError(null);

    const timer = window.setTimeout(async () => {
      try {
        const response = await researchService.listResearch({
          search: searchQuery || undefined,
          domain: selectedDomain === 'all' ? undefined : selectedDomain,
          status:
            selectedStatus === 'all'
              ? undefined
              : (selectedStatus as ResearchStatus),
          limit: PAGE_SIZE,
          offset,
        });
        if (cancelled) return;

        setResearchList(response.items);
        setTotalResearch(response.total);
        setDomainOptions((current) =>
          Array.from(
            new Set([
              ...current,
              ...response.items.flatMap((item) =>
                item.domain ? [item.domain] : []
              ),
            ])
          ).sort((left, right) => left.localeCompare(right))
        );
      } catch (error) {
        if (cancelled) return;
        setResearchList([]);
        setTotalResearch(0);
        setLoadError(
          getResearchErrorMessage(error, 'We could not load your research.')
        );
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }, searchQuery ? 300 : 0);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [offset, retryKey, searchQuery, selectedDomain, selectedStatus]);

  const hasFilters =
    Boolean(searchQuery) || selectedDomain !== 'all' || selectedStatus !== 'all';
  const firstVisible = totalResearch === 0 ? 0 : offset + 1;
  const lastVisible = Math.min(offset + researchList.length, totalResearch);
  const hasPrevious = offset > 0;
  const hasNext = offset + PAGE_SIZE < totalResearch;

  const clearFilters = () => {
    setSearchQuery('');
    setSelectedDomain('all');
    setSelectedStatus('all');
    setOffset(0);
  };

  return (
    <div className="min-h-screen bg-canvas flex flex-col">
      <TopBar
        breadcrumbs={
          <div className="flex items-center gap-2">
            <span className="text-ink-soft">Archive</span>
            <span className="text-ink-muted">/</span>
            <span className="text-ink font-medium">My Research</span>
          </div>
        }
      />

      <main className="flex-1 pt-14 pb-16 px-4 sm:px-6">
        <div className="max-w-5xl mx-auto py-8">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
            <div>
              <h1 className="font-serif text-2xl sm:text-3xl text-ink font-normal tracking-tight">
                My Research
              </h1>
              <p className="text-xs sm:text-sm text-ink-soft mt-1">
                Persisted research records across every domain and lifecycle state.
              </p>
            </div>

            <PrimaryButton showArrow onClick={() => navigate('/research/new')}>
              New Research
            </PrimaryButton>
          </div>

          <div className="p-3 bg-panel border border-line rounded-xl mb-6 flex flex-wrap items-center justify-between gap-3 shadow-xs">
            <div className="relative flex-1 min-w-[240px]">
              <Search className="w-4 h-4 text-ink-muted absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                aria-label="Search research"
                value={searchQuery}
                onChange={(event) => {
                  setSearchQuery(event.target.value);
                  setOffset(0);
                }}
                placeholder="Search investigations by title or question…"
                className="w-full bg-canvas border border-line rounded-md pl-9 pr-3 py-1.5 text-xs text-ink placeholder:text-ink-muted focus:outline-none focus:ring-1 focus:ring-accent focus:border-accent transition-colors"
              />
            </div>

            <div className="flex items-center gap-2">
              <select
                aria-label="Filter research by domain"
                value={selectedDomain}
                onChange={(event) => {
                  setSelectedDomain(event.target.value);
                  setOffset(0);
                }}
                className="bg-canvas border border-line text-ink-soft hover:text-ink text-xs rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-accent"
              >
                <option value="all">All domains</option>
                {domainOptions.map((domain) => (
                  <option key={domain} value={domain}>
                    {domain}
                  </option>
                ))}
              </select>

              <select
                aria-label="Filter research by status"
                value={selectedStatus}
                onChange={(event) => {
                  setSelectedStatus(event.target.value);
                  setOffset(0);
                }}
                className="bg-canvas border border-line text-ink-soft hover:text-ink text-xs rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-accent"
              >
                <option value="all">All statuses</option>
                <option value="completed">Completed</option>
                <option value="researching">Researching</option>
                <option value="draft">Draft</option>
                <option value="failed">Failed</option>
              </select>
            </div>
          </div>

          {isLoading ? (
            <CenteredLoadingState label="Loading your research…" />
          ) : loadError ? (
            <ErrorState
              title="Research unavailable"
              message={loadError}
              onRetry={() => setRetryKey((value) => value + 1)}
            />
          ) : researchList.length === 0 ? (
            <EmptyState
              title={hasFilters ? 'No research investigations found' : 'No research yet'}
              description={
                hasFilters
                  ? 'No investigations match your active filters.'
                  : 'Create your first persisted research record.'
              }
              primaryActionLabel={hasFilters ? 'Clear filters' : 'New research'}
              onPrimaryAction={hasFilters ? clearFilters : () => navigate('/research/new')}
            />
          ) : (
            <div className="bg-panel border border-line rounded-xl overflow-hidden shadow-xs divide-y divide-line">
              {researchList.map((item) => {
                const targetUrl =
                  item.status === 'researching'
                    ? `/research/${item.id}/progress`
                    : item.status === 'completed'
                      ? `/research/${item.id}`
                      : `/research/${item.id}/progress`;

                return (
                  <Link
                    key={item.id}
                    to={targetUrl}
                    className="p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-canvas transition-colors group cursor-pointer"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2 mb-1.5">
                        <span className="text-[11px] font-medium text-accent bg-accent-soft border border-accent-line px-2 py-0.5 rounded">
                          {item.domain || 'General research'}
                        </span>
                        <StatusBadge status={item.status} size="sm" />
                      </div>

                      <h3 className="text-sm sm:text-[15px] font-semibold text-ink group-hover:text-accent transition-colors leading-snug">
                        {item.title}
                      </h3>
                      <p className="text-xs text-ink-soft line-clamp-1 mt-1 leading-relaxed">
                        {item.question}
                      </p>
                    </div>

                    <div className="flex items-center justify-between sm:justify-end gap-5 shrink-0 text-xs text-ink-soft pt-2 sm:pt-0 border-t sm:border-t-0 border-line">
                      <div className="text-right">
                        <span className="font-medium text-ink block">
                          {item.sourceCount} sources
                        </span>
                        <span className="text-[11px] text-ink-muted flex items-center justify-end gap-1 mt-0.5">
                          <Clock className="w-3 h-3" />
                          <span>{formatUpdatedAt(item.updatedAt)}</span>
                        </span>
                      </div>

                      <div className="w-8 h-8 rounded-full flex items-center justify-center text-ink-muted group-hover:text-accent group-hover:bg-accent-soft transition-all">
                        <ChevronRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>
          )}

          <div className="mt-3 flex items-center justify-between gap-4 text-xs text-ink-muted">
            <span>
              Showing {firstVisible}–{lastVisible} of {totalResearch} investigations
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={!hasPrevious || isLoading}
                onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}
                className="inline-flex items-center gap-1 rounded-md border border-line bg-panel px-2.5 py-1.5 text-ink-soft hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
                Previous
              </button>
              <button
                type="button"
                disabled={!hasNext || isLoading}
                onClick={() => setOffset((value) => value + PAGE_SIZE)}
                className="inline-flex items-center gap-1 rounded-md border border-line bg-panel px-2.5 py-1.5 text-ink-soft hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};
