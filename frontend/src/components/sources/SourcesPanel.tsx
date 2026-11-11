import React, { useState, useEffect, useRef } from 'react';
import { Search, X, BookOpen, StickyNote, ChevronDown } from 'lucide-react';
import { SourceResponse } from '../../types/report';
import { ExpandedSource } from './ExpandedSource';
import { SourceRow } from './SourceRow';
import { useAuth } from '../../app/AuthContext';

interface SourcesPanelProps {
  reportId: string;
  sources: SourceResponse[];
  selectedSourceNumber: number;
  onSelectSource: (number: number) => void;
  onCloseMobileDrawer?: () => void;
  isMobileDrawer?: boolean;
}

export const SourcesPanel: React.FC<SourcesPanelProps> = ({
  reportId,
  sources,
  selectedSourceNumber,
  onSelectSource,
  onCloseMobileDrawer,
  isMobileDrawer = false,
}) => {
  const { user } = useAuth();
  const notesKey = `research-notes:${user?.id}:${reportId}`;
  const [activeTab, setActiveTab] = useState<'sources' | 'notes'>('sources');
  const [searchQuery, setSearchQuery] = useState('');
  const [showAllSources, setShowAllSources] = useState(false);
  const [notes, setNotes] = useState(() => {
    try { return window.localStorage.getItem(notesKey) || ''; } catch { return ''; }
  });

  useEffect(() => {
    try { window.localStorage.setItem(notesKey, notes); } catch { /* Storage may be unavailable. */ }
  }, [notes, notesKey]);

  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll selected source into view when selected
  useEffect(() => {
    if (selectedSourceNumber) {
      const el = document.getElementById(`source-${selectedSourceNumber}`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }
  }, [selectedSourceNumber]);

  const filteredSources = sources.filter((s) => {
    if (!searchQuery.trim()) return true;
    const query = searchQuery.toLowerCase();
    return (
      s.title?.toLowerCase().includes(query) ||
      s.publisher?.toLowerCase().includes(query) ||
      s.authors.some((a) => a.toLowerCase().includes(query)) ||
      s.number.toString() === query
    );
  });

  // By default show first 7 or expanded set
  const displayedSources = showAllSources
    ? filteredSources
    : filteredSources.slice(0, 7);

  const hasMore = filteredSources.length > 7 && !showAllSources;

  return (
    <div
      ref={containerRef}
      className={`h-full flex flex-col bg-panel border-l border-line ${
        isMobileDrawer ? 'w-full' : 'w-full max-w-[420px]'
      }`}
    >
      <div className="p-4 border-b border-line shrink-0 bg-panel">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-medium text-ink">
              Sources <span className="tabular-nums text-ink-muted">{sources.length}</span>
            </h3>
          </div>

          {isMobileDrawer && onCloseMobileDrawer && (
            <button
              type="button"
              onClick={onCloseMobileDrawer}
              aria-label="Close sources panel"
              className="p-1 rounded-md text-ink-soft hover:bg-subtle"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        <div className="flex items-center gap-4 text-xs border-b border-line pb-2 mb-3">
          <button
            type="button"
            onClick={() => setActiveTab('sources')}
            className={`font-medium pb-1 relative transition-colors ${
              activeTab === 'sources'
                ? 'text-ink'
                : 'text-ink-muted hover:text-ink'
            }`}
          >
            <span className="flex items-center gap-1.5">
              <BookOpen className="w-3.5 h-3.5" />
              <span>Sources</span>
            </span>
            {activeTab === 'sources' && (
              <div className="absolute bottom-[-9px] left-0 right-0 h-[2px] bg-ink rounded-full" />
            )}
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('notes')}
            className={`font-medium pb-1 relative transition-colors ${
              activeTab === 'notes'
                ? 'text-ink'
                : 'text-ink-muted hover:text-ink'
            }`}
          >
            <span className="flex items-center gap-1.5">
              <StickyNote className="w-3.5 h-3.5" />
              <span>Notes</span>
            </span>
            {activeTab === 'notes' && (
              <div className="absolute bottom-[-9px] left-0 right-0 h-[2px] bg-ink rounded-full" />
            )}
          </button>
        </div>

        {activeTab === 'sources' && (
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-ink-muted absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              aria-label="Filter sources"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filter sources"
              className="field h-9 pl-8 text-[13px]"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                aria-label="Clear source filter"
                className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-muted hover:text-ink"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === 'notes' ? (
          <div className="h-full flex flex-col">
            <textarea
              aria-label="Research notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="field flex-1 text-xs leading-relaxed resize-none"
              placeholder="Notes for yourself: open questions, things to check, follow-ups…"
            />
            <div className="text-[11px] text-ink-muted mt-2 flex items-center justify-between">
              <span>Saved in this browser</span>
              <span>{notes.length} characters</span>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            {displayedSources.length === 0 ? (
              <div className="py-12 text-center text-xs text-ink-soft">
                No sources match &ldquo;{searchQuery}&rdquo;
              </div>
            ) : (
              displayedSources.map((source) => {
                const isSelected = source.number === selectedSourceNumber;
                return isSelected ? (
                  <ExpandedSource key={source.id} source={source} />
                ) : (
                  <SourceRow
                    key={source.id}
                    source={source}
                    onSelect={onSelectSource}
                  />
                );
              })
            )}

            {hasMore && (
              <button
                type="button"
                onClick={() => setShowAllSources(true)}
                className="mt-2 flex h-8 w-full cursor-pointer items-center justify-center gap-1.5 rounded-md border border-line text-xs font-medium text-ink-soft transition-colors hover:bg-subtle hover:text-ink"
              >
                <span>Show {filteredSources.length - 7} more</span>
                <ChevronDown className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
