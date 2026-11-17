import { useCallback, useState } from 'react';
import { Document } from '../types/document';
import { documentsService, getDocumentErrorMessage } from '../services/documents.service';
import { useToast } from '../app/ToastContext';

/** Open, retry and remove actions shared by every document list. */
export function useDocumentActions(onChange: () => void) {
  const { addToast } = useToast();
  const [viewing, setViewing] = useState<Document | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [retryingId, setRetryingId] = useState<string | null>(null);

  const remove = useCallback(
    async (id: string) => {
      if (!window.confirm('Delete this file? This can’t be undone.')) return;
      setDeletingId(id);
      try {
        await documentsService.deleteDocument(id);
        onChange();
        addToast({ type: 'success', title: 'File deleted' });
      } catch {
        addToast({
          type: 'error',
          title: 'Couldn’t delete the file',
          description: 'Please try again.',
        });
      } finally {
        setDeletingId(null);
      }
    },
    [onChange, addToast],
  );

  const retry = useCallback(
    async (id: string) => {
      setRetryingId(id);
      try {
        await documentsService.retryDocument(id);
        onChange();
      } catch (err) {
        addToast({
          type: 'error',
          title: 'Couldn’t try again',
          description: getDocumentErrorMessage(err, 'Please remove the file and upload it again.'),
        });
      } finally {
        setRetryingId(null);
      }
    },
    [onChange, addToast],
  );

  const open = useCallback((doc: Document) => setViewing(doc), []);
  const close = useCallback(() => setViewing(null), []);

  return { viewing, open, close, remove, retry, deletingId, retryingId };
}
