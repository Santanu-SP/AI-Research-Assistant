import type { Document } from '../types/document';

type ProgressFields = Pick<Document, 'status' | 'processingStage' | 'processingProgress' | 'pageCount' | 'type'>;

const STAGE_LABELS: Record<string, string> = {
  reading: 'Reading and splitting the file',
  ocr: 'Reading text from images (OCR)',
  embedding: 'Making it searchable',
  saving: 'Saving',
};

/** Rough share of the work done at each step, for a small progress bar. */
const STAGE_START: Record<string, number> = {
  reading: 10,
  ocr: 10,
  embedding: 55,
  saving: 95,
};

export interface IngestionStep {
  /** Plain words for the current step, e.g. "Making it searchable · 40%". */
  label: string;
  /** 0-100 when the step is known, otherwise null. */
  percent: number | null;
}

/** What a file that is still being prepared is doing right now. */
export const ingestionStep = (doc: ProgressFields): IngestionStep => {
  if (doc.status === 'uploaded') return { label: 'Waiting to start', percent: 3 };
  const stage = doc.processingStage ?? null;
  if (!stage || !(stage in STAGE_LABELS)) return { label: 'Preparing…', percent: null };

  const parts = [STAGE_LABELS[stage]];
  let percent = STAGE_START[stage];
  if (stage === 'embedding' && typeof doc.processingProgress === 'number') {
    const done = Math.max(0, Math.min(100, doc.processingProgress));
    percent = Math.round(STAGE_START.embedding + (done / 100) * (STAGE_START.saving - STAGE_START.embedding));
    parts.push(`${done}%`);
  }
  if (doc.pageCount && doc.pageCount > 0 && (doc.type === 'pdf' || doc.type === 'docx' || !doc.type)) {
    parts.push(`${doc.pageCount} page${doc.pageCount === 1 ? '' : 's'}`);
  }
  return { label: parts.join(' · '), percent };
};
