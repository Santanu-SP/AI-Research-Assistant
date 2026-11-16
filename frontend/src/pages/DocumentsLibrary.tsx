import React from 'react';
import { TopBar } from '../components/layout/TopBar';
import { PageHeader } from '../components/common/PageHeader';
import { DocumentsPanel } from '../components/documents/DocumentsPanel';
import { useDocumentLibrary } from '../hooks/useDocumentLibrary';

const ALL_DOCUMENTS = { all: true } as const;

/** Every file the user has uploaded, to open, retry or delete. */
export const DocumentsLibraryPage: React.FC = () => {
  const library = useDocumentLibrary(ALL_DOCUMENTS);
  return (
    <div className="min-h-screen flex flex-col">
      <TopBar breadcrumbs={<span className="font-medium text-ink">Documents</span>} />
      <main className="flex-1 px-4 pb-16 pt-14 sm:px-6 lg:px-10">
        <div className="mx-auto max-w-3xl py-10">
          <PageHeader
            title="All documents"
            description="Everything you have uploaded. A new research reads only the files you add to it, and a project reads its own files."
          />
          <DocumentsPanel
            library={library}
            title="Your library"
            className="mt-6 max-h-[calc(100vh-14rem)]"
          />
        </div>
      </main>
    </div>
  );
};
