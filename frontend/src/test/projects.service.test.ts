/**
 * Tests for projectsService – API layer correctness.
 * All network calls are intercepted with vi.stubGlobal / fetch mocking.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { projectsService, getProjectErrorMessage } from '../services/projects.service';
import { ApiError } from '../services/api';
import { makeProject, makeProjectList } from './fixtures';

// Minimal fetch mock factory
const mockFetch = (body: unknown, status = 200) => {
  const json = () => Promise.resolve(body);
  const text = () => Promise.resolve(JSON.stringify(body));
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : String(status),
    json,
    text,
  });
};

describe('projectsService', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', undefined);
  });

  describe('listProjects', () => {
    it('returns a project list response on success', async () => {
      const fixture = makeProjectList([makeProject()]);
      vi.stubGlobal('fetch', mockFetch(fixture));

      const result = await projectsService.listProjects();
      expect(result.items).toHaveLength(1);
      expect(result.items[0].name).toBe('Project Alpha');
    });

    it('includes search param in URL when provided', async () => {
      const fixture = makeProjectList([]);
      const fetchMock = mockFetch(fixture);
      vi.stubGlobal('fetch', fetchMock);

      await projectsService.listProjects({ search: 'membrane' });
      const url: string = (fetchMock.mock.calls[0][0] as string);
      expect(url).toContain('search=membrane');
    });

    it('includes includeArchived param when true', async () => {
      const fixture = makeProjectList([]);
      const fetchMock = mockFetch(fixture);
      vi.stubGlobal('fetch', fetchMock);

      await projectsService.listProjects({ includeArchived: true });
      const url: string = (fetchMock.mock.calls[0][0] as string);
      expect(url).toContain('includeArchived=true');
    });
  });

  describe('getProject', () => {
    it('returns a project on success', async () => {
      const fixture = makeProject();
      vi.stubGlobal('fetch', mockFetch(fixture));

      const result = await projectsService.getProject('proj-alpha-123');
      expect(result.id).toBe('proj-alpha-123');
    });

    it('throws ApiError on 404', async () => {
      vi.stubGlobal(
        'fetch',
        mockFetch({ detail: 'Project not found' }, 404)
      );

      await expect(
        projectsService.getProject('nonexistent')
      ).rejects.toBeInstanceOf(ApiError);
    });
  });

  describe('createProject', () => {
    it('sends POST with name and description', async () => {
      const fixture = makeProject({ name: 'New Project' });
      const fetchMock = mockFetch(fixture, 201);
      vi.stubGlobal('fetch', fetchMock);

      const result = await projectsService.createProject({
        name: 'New Project',
        description: 'Test description',
      });
      expect(result.name).toBe('New Project');

      const [, opts] = fetchMock.mock.calls[0] as [string, RequestInit];
      const body = JSON.parse(opts.body as string);
      expect(body.name).toBe('New Project');
      expect(body.description).toBe('Test description');
    });
  });

  describe('updateProject', () => {
    it('sends PATCH and returns updated project', async () => {
      const fixture = makeProject({ name: 'Renamed Project' });
      const fetchMock = mockFetch(fixture);
      vi.stubGlobal('fetch', fetchMock);

      const result = await projectsService.updateProject('proj-alpha-123', {
        name: 'Renamed Project',
      });
      expect(result.name).toBe('Renamed Project');

      const [, opts] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(opts.method).toBe('PATCH');
    });
  });

  describe('archiveProject', () => {
    it('sends DELETE and resolves', async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 204,
        statusText: 'No Content',
        json: () => Promise.resolve(undefined),
        text: () => Promise.resolve(''),
      });
      vi.stubGlobal('fetch', fetchMock);

      await expect(
        projectsService.archiveProject('proj-alpha-123')
      ).resolves.toBeUndefined();

      const [, opts] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(opts.method).toBe('DELETE');
    });
  });
});

describe('getProjectErrorMessage', () => {
  it('returns "Project not found." for 404', () => {
    const err = new ApiError('Not found', 404);
    expect(getProjectErrorMessage(err, 'fallback')).toBe('Project not found.');
  });

  it('returns "You do not have access" for 403', () => {
    const err = new ApiError('Forbidden', 403);
    expect(getProjectErrorMessage(err, 'fallback')).toBe(
      'You do not have access to this project.'
    );
  });

  it('returns fallback for unknown errors', () => {
    expect(getProjectErrorMessage(new Error('Network error'), 'fallback')).toBe(
      'fallback'
    );
  });

  it('returns fallback for ApiError with unrecognized status', () => {
    const err = new ApiError('Server error', 500);
    expect(getProjectErrorMessage(err, 'fallback')).toBe('fallback');
  });
});
