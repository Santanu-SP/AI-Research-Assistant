import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Clock, Plus, Search } from 'lucide-react';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';
import { LoadingState } from '../components/common/LoadingState';
import { PrimaryButton } from '../components/common/PrimaryButton';
import { PageHeader } from '../components/common/PageHeader';
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
    <div className="min-h-screen flex flex-col">
      <TopBar
        breadcrumbs={<span className="font-medium text-ink">My research</span>}
      />

      <main className="flex-1 px-4 pb-16 pt-14 sm:px-6 lg:px-10">
        <div className="mx-auto max-w-5xl py-8 sm:py-10">
          <PageHeader
            title="My research"
            description="Every question you have asked, with its status and the number of sources behind the answer."
            actions={
              <PrimaryButton onClick={() => navigate('/research/new')}>
                <Plus className="h-4 w-4" />
                New research
              </PrimaryButton>
            }
          />

          <div className="mb-4 mt-8 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative w-full sm:max-w-xs">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" />
              <input
                type="search"
                aria-label="Search research"
                value={searchQuery}
                onChange={(event) => {
                  setSearchQuery(event.target.value);
                  setOffset(0);
                }}
                placeholder="Search by title or question"
                className="field h-9 pl-9 text-[13px]"
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
                className="field h-9 w-auto pr-8 text-[13px]"
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
                className="field h-9 w-auto pr-8 text-[13px]"
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
            <LoadingState rows={4} />
          ) : loadError ? (
            <ErrorState
              title="Research unavailable"
              message={loadError}
              onRetry={() => setRetryKey((value) => value + 1)}
            />
          ) : researchList.length === 0 ? (
            <EmptyState
              title={hasFilters ? 'Nothing matches these filters' : 'No research yet'}
              description={
                hasFilters
                  ? 'Try a different search term, domain or status.'
                  : 'Ask a question about your uploaded papers to start.'
              }
              primaryActionLabel={hasFilters ? 'Clear filters' : 'New research'}
              onPrimaryAction={hasFilters ? clearFilters : () => navigate('/research/new')}
            />
          ) : (
            <div className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-panel shadow-xs">
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
                    className="group flex items-center gap-4 px-4 py-3.5 transition-colors hover:bg-subtle/60 sm:px-5"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="truncate text-sm font-medium text-ink">{item.title}</h3>
                      </div>
                      <p className="mt-0.5 truncate text-[13px] text-ink-muted">{item.question}</p>
                      <p className="mt-1.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-ink-muted">
                        <span className="rounded border border-line bg-subtle px-1.5 py-px text-[11px] font-medium text-ink-soft">
                          {item.domain || 'General'}
                        </span>
                        <span>{item.sourceCount} sources</span>
                        <span aria-hidden="true">·</span>
                        <span className="flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {formatUpdatedAt(item.updatedAt)}
                        </span>
                      </p>
                    </div>

                    <div className="flex shrink-0 items-center gap-3">
                      <StatusBadge status={item.status} size="sm" />
                      <ChevronRight className="hidden h-4 w-4 text-ink-muted transition-transform group-hover:translate-x-0.5 group-hover:text-ink-soft sm:block" />
                    </div>
                  </Link>
                );
              })}
            </div>
          )}

          <div className="mt-3 flex items-center justify-between gap-4 text-xs tabular-nums text-ink-muted">
            <span>
              {firstVisible}–{lastVisible} of {totalResearch}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={!hasPrevious || isLoading}
                onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}
                className="inline-flex h-8 items-center gap-1 rounded-md border border-line bg-panel px-2.5 text-[13px] text-ink-soft transition-colors hover:bg-subtle hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
                Previous
              </button>
              <button
                type="button"
                disabled={!hasNext || isLoading}
                onClick={() => setOffset((value) => value + PAGE_SIZE)}
                className="inline-flex h-8 items-center gap-1 rounded-md border border-line bg-panel px-2.5 text-[13px] text-ink-soft transition-colors hover:bg-subtle hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
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
