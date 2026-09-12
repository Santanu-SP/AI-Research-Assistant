export type SourceType =
  | 'peer-reviewed'
  | 'official-documentation'
  | 'institutional'
  | 'technical-report'
  | 'preprint';

export interface Source {
  id: string;
  number: number;
  title: string;
  publisher: string;
  authors: string[];
  year: number;
  url?: string;
  sourceType: SourceType;
  relevantExcerpt?: string;
  citationCount?: number;
  doi?: string;
  bibtex?: string;
}
