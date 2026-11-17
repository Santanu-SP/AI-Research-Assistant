import React, { useEffect, useState } from 'react';
import { Search } from 'lucide-react';
import { TopBar } from '../components/layout/TopBar';
import { PageHeader } from '../components/common/PageHeader';
import { DocumentsPanel } from '../components/documents/DocumentsPanel';
import { useDocumentLibrary } from '../hooks/useDocumentLibrary';
import type { DocumentKind } from '../types/document';

const ALL_FILES = { all: true } as const;
const SEARCH_DELAY_MS = 300;

const KINDS: { id: DocumentKind | 'all'; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'documents', label: 'Documents' },
  { id: 'images', label: 'Images' },
  { id: 'audio', label: 'Audio' },
  { id: 'video', label: 'Video' },
  { id: 'links', label: 'Links' },
];

/** Every file the user has added (documents, images, audio, video, links), to open, retry or delete. */
export const LibraryPage: React.FC = () => {
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [kind, setKind] = useState<DocumentKind | 'all'>('all');

  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(query.trim()), SEARCH_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [query]);

  const library = useDocumentLibrary(ALL_FILES, search || undefined, kind === 'all' ? undefined : kind);
  const isFiltered = Boolean(search) || kind !== 'all';

  const toolbar = (
    <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center">
      <div className="relative w-full sm:max-w-[16rem]">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" />
        <input
          type="search"
          aria-label="Search files"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by name or title"
          className="field h-8 pl-9 text-[13px]"
        />
      </div>
      <div role="group" aria-label="File type" className="flex flex-wrap gap-1.5">
        {KINDS.map(({ id, label }) => {
          const selected = kind === id;
          return (
            <button
              key={id}
              type="button"
              aria-pressed={selected}
              onClick={() => setKind(id)}
              className={`h-7 rounded-full border px-2.5 text-xs transition-colors ${
                selected
                  ? 'border-accent-line bg-accent-soft font-medium text-ink'
                  : 'border-line text-ink-soft hover:bg-subtle hover:text-ink'
              }`}
            >
              {label}
            </button>
          );
        })}
      </div>
    </div>
  );

  return (
    <div className="min-h-screen flex flex-col">
      <TopBar breadcrumbs={<span className="font-medium text-ink">Library</span>} />
      <main className="flex-1 px-4 pb-16 pt-14 sm:px-6 lg:px-10">
        <div className="mx-auto max-w-3xl py-10">
          <PageHeader
            title="Library"
            description="All your files in one place: documents, images, audio, video and web links. A new research reads only the files you add to it, and a project reads its own files."
          />
          <DocumentsPanel
            library={library}
            title="Your files"
            className="mt-6 max-h-[calc(100vh-14rem)]"
            toolbar={toolbar}
            isFiltered={isFiltered}
            onClearFilters={() => {
              setQuery('');
              setSearch('');
              setKind('all');
            }}
            showUsage
          />
        </div>
      </main>
    </div>
  );
};
