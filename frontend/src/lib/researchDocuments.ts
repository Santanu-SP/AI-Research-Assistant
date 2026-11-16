import { Document } from '../types/document';
import { isDocumentPending } from '../services/documents.service';

/** Why a new research can't start yet, given the files picked for it. */
export const documentsBlockedReason = (attached: Document[], pickedCount: number): string | null => {
  if (pickedCount === 0) return 'Upload or pick a document first';
  if (attached.some((doc) => doc.status === 'indexed')) return null;
  if (attached.some((doc) => isDocumentPending(doc)) || attached.length < pickedCount) {
    return 'Your documents are still being prepared';
  }
  return 'None of the picked files could be read. Pick another one';
};
