import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  documentsService,
  getDocumentErrorMessage,
  isDuplicateDocumentError,
} from '../services/documents.service';
import { ApiError } from '../services/api';
import { makeDocument, makeDocumentList } from './fixtures';

const mockFetch = (body: unknown, status = 200) => {
  const json = () => Promise.resolve(body);
  const text = () => Promise.resolve(JSON.stringify(body));
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: String(status),
    json,
    text,
  });
};

describe('documentsService', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', undefined);
  });

  describe('getProjectDocuments', () => {
    it('fetches from project-scoped endpoint', async () => {
      const fixture = makeDocumentList([makeDocument()]);
      const fetchMock = mockFetch(fixture);
      vi.stubGlobal('fetch', fetchMock);

      await documentsService.getProjectDocuments('proj-alpha-123');
      const url: string = fetchMock.mock.calls[0][0] as string;
      expect(url).toContain('/projects/proj-alpha-123/documents');
    });

    it('appends search param when provided', async () => {
      const fixture = makeDocumentList([]);
      const fetchMock = mockFetch(fixture);
      vi.stubGlobal('fetch', fetchMock);

      await documentsService.getProjectDocuments('proj-alpha-123', {
        search: 'membrane',
      });
      const url: string = fetchMock.mock.calls[0][0] as string;
      expect(url).toContain('search=membrane');
    });
  });

  describe('uploadProjectDocument', () => {
    it('sends POST with FormData to project endpoint', async () => {
      const fixture = makeDocument();
      const fetchMock = mockFetch(fixture, 201);
      vi.stubGlobal('fetch', fetchMock);

      const file = new File(['content'], 'test.pdf', { type: 'application/pdf' });
      const result = await documentsService.uploadProjectDocument(
        'proj-alpha-123',
        file
      );

      expect(result.id).toBe('doc-001');
      const [url, opts] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toContain('/projects/proj-alpha-123/documents');
      expect(opts.method).toBe('POST');
      expect(opts.body).toBeInstanceOf(FormData);
    });

    it('throws ApiError on 409 (duplicate)', async () => {
      vi.stubGlobal(
        'fetch',
        mockFetch({ detail: 'Duplicate document' }, 409)
      );

      const file = new File(['content'], 'dup.pdf', { type: 'application/pdf' });
      await expect(
        documentsService.uploadProjectDocument('proj-alpha-123', file)
      ).rejects.toBeInstanceOf(ApiError);
    });
  });
});

describe('isDuplicateDocumentError', () => {
  it('returns true for 409 ApiError', () => {
    const err = new ApiError('Conflict', 409);
    expect(isDuplicateDocumentError(err)).toBe(true);
  });

  it('returns false for 500 ApiError', () => {
    const err = new ApiError('Server error', 500);
    expect(isDuplicateDocumentError(err)).toBe(false);
  });

  it('returns false for non-ApiError', () => {
    expect(isDuplicateDocumentError(new Error('Network error'))).toBe(false);
  });
});

describe('getDocumentErrorMessage', () => {
  it('returns duplicate message for 409', () => {
    const err = new ApiError('Conflict', 409);
    expect(getDocumentErrorMessage(err, 'fallback')).toBe(
      'This document already exists in this project.'
    );
  });

  it('returns permission message for 403', () => {
    const err = new ApiError('Forbidden', 403);
    expect(getDocumentErrorMessage(err, 'fallback')).toBe(
      'You do not have permission to upload to this project.'
    );
  });

  it('returns size message for 413', () => {
    const err = new ApiError('Too large', 413);
    expect(getDocumentErrorMessage(err, 'fallback')).toBe(
      'File is too large to upload.'
    );
  });

  it('returns fallback for unknown errors', () => {
    expect(getDocumentErrorMessage(new Error('timeout'), 'fallback')).toBe(
      'fallback'
    );
  });
});

describe('retryDocument', () => {
  it('posts to the retry endpoint', async () => {
    const failed = makeDocument({ id: 'doc-9', status: 'uploaded', ingestionStatus: 'uploaded' });
    const fetchMock = mockFetch(failed, 202);
    vi.stubGlobal('fetch', fetchMock);
    const result = await documentsService.retryDocument('doc-9');
    expect(result.status).toBe('uploaded');
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/documents\/doc-9\/retry$/);
    expect((init as RequestInit).method).toBe('POST');
  });
});

describe('409 codes other than duplicates', () => {
  it('are not treated as duplicates', () => {
    const err = new ApiError('Conflict', 409, {
      error: { code: 'document_not_retryable', message: 'Only failed documents can be retried.' },
    });
    expect(isDuplicateDocumentError(err)).toBe(false);
    expect(getDocumentErrorMessage(err, 'fallback')).toBe(
      'Only documents that failed processing can be retried.'
    );
  });

  it('explains upload rate limits', () => {
    expect(getDocumentErrorMessage(new ApiError('Too many', 429), 'fallback')).toMatch(
      /too many uploads/i
    );
  });
});
