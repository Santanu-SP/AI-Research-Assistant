import React from 'react';
import { TopBar } from '../components/layout/TopBar';
import { PageHeader } from '../components/common/PageHeader';
import { DocumentsPanel } from '../components/documents/DocumentsPanel';
import { useDocumentLibrary } from '../hooks/useDocumentLibrary';

const ALL_FILES = { all: true } as const;

/** Every file the user has added (documents, images, audio, video, links), to open, retry or delete. */
export const LibraryPage: React.FC = () => {
  const library = useDocumentLibrary(ALL_FILES);
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
          />
        </div>
      </main>
    </div>
  );
};
