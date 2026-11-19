// @vitest-environment jsdom
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../app/ToastContext';
import { PresenceBar } from '../components/collaboration/PresenceBar';
import { ShareDialog } from '../components/collaboration/ShareDialog';
import { JoinInvitePage } from '../pages/JoinInvitePage';
import { ResearchReportPage } from '../pages/ResearchReport';
import { collaborationService } from '../services/collaboration.service';
import { reportService } from '../services/report.service';

vi.mock('../app/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'user-owner', name: 'Alice Owner', email: 'alice@example.com' },
    loading: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    refresh: vi.fn(),
  }),
}));

vi.mock('../services/byok.service', () => ({
  byokService: {
    getPreferences: vi.fn().mockResolvedValue({ localFallbackEnabled: false }),
    listKeys: vi.fn().mockResolvedValue([]),
  },
}));

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  readyState = 1;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  sent: string[] = [];

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
    setTimeout(() => {
      this.onopen?.(new Event('open'));
    }, 0);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.readyState = 3;
  }

  emit(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent);
  }
}

describe('Multi-user collaboration & realtime UI', () => {
  const originalWebSocket = window.WebSocket;

  beforeEach(() => {
    FakeWebSocket.instances = [];
    Object.defineProperty(window, 'WebSocket', {
      configurable: true,
      writable: true,
      value: FakeWebSocket,
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    Object.defineProperty(window, 'WebSocket', {
      configurable: true,
      writable: true,
      value: originalWebSocket,
    });
  });

  it('renders PresenceBar live indicator, avatars, and teammate activity', () => {
    render(
      <PresenceBar
        connectionState="connected"
        currentUserId="user-owner"
        presence={[
          {
            userId: 'user-owner',
            name: 'Alice Owner',
            email: 'alice@example.com',
            role: 'owner',
            activity: 'viewing',
            connections: 1,
          },
          {
            userId: 'user-bob',
            name: 'Bob Editor',
            email: 'bob@example.com',
            role: 'editor',
            activity: 'typing',
            connections: 1,
          },
        ]}
      />,
    );

    expect(screen.getByText('Live · 2 online')).toBeInTheDocument();
    expect(screen.getByText('AO')).toBeInTheDocument();
    expect(screen.getByText('BE')).toBeInTheDocument();
    expect(screen.getByText(/Bob is typing/i)).toBeInTheDocument();
  });

  it('ShareDialog lists members, invites by email, and creates invite links', async () => {
    const listSpy = vi.spyOn(collaborationService, 'listMembers').mockResolvedValue({
      resourceType: 'project',
      resourceId: 'proj-1',
      myRole: 'owner',
      version: 1,
      members: [
        {
          userId: 'user-owner',
          name: 'Alice Owner',
          email: 'alice@example.com',
          role: 'owner',
          isOwner: true,
          joinedAt: '2026-01-01T00:00:00Z',
        },
      ],
      invites: [],
    });
    const emailSpy = vi.spyOn(collaborationService, 'inviteByEmail').mockResolvedValue({
      memberAdded: true,
      member: {
        userId: 'user-bob',
        name: 'Bob Editor',
        email: 'bob@example.com',
        role: 'editor',
        isOwner: false,
        joinedAt: '2026-01-01T00:01:00Z',
      },
      invite: {
        id: 'inv-1',
        resourceType: 'project',
        projectId: 'proj-1',
        researchId: null,
        role: 'editor',
        targetEmail: 'bob@example.com',
        maxUses: 1,
        useCount: 1,
        expiresAt: null,
        revokedAt: null,
        acceptedAt: '2026-01-01T00:01:00Z',
        createdAt: '2026-01-01T00:01:00Z',
      },
      invitePath: '/join/tok-1',
      token: 'tok-1',
    });
    const linkSpy = vi.spyOn(collaborationService, 'createInviteLink').mockResolvedValue({
      invite: {
        id: 'inv-2',
        resourceType: 'project',
        projectId: 'proj-1',
        researchId: null,
        role: 'viewer',
        targetEmail: null,
        maxUses: null,
        useCount: 0,
        expiresAt: null,
        revokedAt: null,
        acceptedAt: null,
        createdAt: '2026-01-01T00:02:00Z',
      },
      invitePath: '/join/share-tok-2',
      token: 'share-tok-2',
    });

    render(
      <ToastProvider>
        <ShareDialog
          isOpen
          resourceType="project"
          resourceId="proj-1"
          resourceTitle="Shared Team Study"
          onClose={vi.fn()}
        />
      </ToastProvider>,
    );

    expect(await screen.findByText(/Alice Owner/i)).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText('teammate@example.com'), {
      target: { value: 'bob@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Invite$/i }));

    await waitFor(() =>
      expect(emailSpy).toHaveBeenCalledWith('project', 'proj-1', 'bob@example.com', 'editor'),
    );

    fireEvent.change(screen.getByLabelText('Invite link role'), {
      target: { value: 'viewer' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Create link/i }));

    await waitFor(() =>
      expect(linkSpy).toHaveBeenCalledWith('project', 'proj-1', 'viewer'),
    );
    expect(screen.getByLabelText('Generated invite link')).toHaveValue(
      `${window.location.origin}/join/share-tok-2`,
    );
    expect(listSpy).toHaveBeenCalled();
  });

  it('JoinInvitePage previews and accepts invite before redirecting', async () => {
    vi.spyOn(collaborationService, 'previewInvite').mockResolvedValue({
      resourceType: 'project',
      resourceId: 'proj-99',
      resourceTitle: 'Quantum Lab Notes',
      inviterName: 'Alice Owner',
      role: 'editor',
      targetEmail: null,
      expiresAt: null,
      alreadyMember: false,
    });
    const acceptSpy = vi.spyOn(collaborationService, 'acceptInvite').mockResolvedValue({
      resourceType: 'project',
      resourceId: 'proj-99',
      role: 'editor',
      redirectPath: '/projects/proj-99',
    });

    render(
      <ToastProvider>
        <MemoryRouter initialEntries={['/join/abc123']}>
          <Routes>
            <Route path="/join/:token" element={<JoinInvitePage />} />
            <Route path="/projects/:projectId" element={<div>Project Workspace Landed</div>} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>,
    );

    expect(await screen.findByText('Quantum Lab Notes')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Join project/i }));

    await waitFor(() => expect(acceptSpy).toHaveBeenCalledWith('abc123'));
    expect(await screen.findByText('Project Workspace Landed')).toBeInTheDocument();
  });

  it('enforces viewer read-only mode and appends live WebSocket followup.created turns on ResearchReportPage', async () => {
    const baseReport = {
      report: {
        id: 'rep-1',
        researchId: 'res-1',
        title: 'Realtime Collaboration Report',
        summary: 'Summary [S1].',
        dossierRef: 'REF #1',
        readingTimeMinutes: 3,
        sourceCount: 1,
        status: 'completed' as const,
        version: 1,
        myRole: 'viewer' as const,
        isShared: true,
        sections: [
          {
            id: 'sec-1',
            heading: 'Section',
            content: 'Grounded detail [S1].',
            quote: null,
            position: 0,
            citationIds: [1],
            citations: [{ id: 'cit-1', sourceId: 'src-1', number: 1, position: 0 }],
            createdAt: '2026-01-01T00:00:00Z',
            updatedAt: '2026-01-01T00:00:00Z',
          },
        ],
        createdAt: '2026-01-01T00:00:00Z',
        updatedAt: '2026-01-01T00:00:00Z',
      },
      sources: [
        {
          id: 'src-1',
          number: 1,
          title: 'Primary Study',
          publisher: 'ACM',
          authors: ['A. Author'],
          year: 2025,
          url: null,
          sourceType: 'peer-reviewed' as const,
          relevantExcerpt: 'Excerpt',
          citationCount: 1,
          doi: null,
          bibtex: null,
          documentId: null,
          chunkId: null,
          page: 1,
          section: null,
          rerankScore: 0.9,
          createdAt: '2026-01-01T00:00:00Z',
          updatedAt: '2026-01-01T00:00:00Z',
        },
      ],
      followups: [],
    };

    vi.spyOn(reportService, 'getResearchReport').mockResolvedValue(baseReport);

    render(
      <MemoryRouter initialEntries={['/research/res-1/report']}>
        <Routes>
          <Route path="/research/:id/report" element={<ResearchReportPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/You have view-only access to this research report/i),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText('Follow-up question')).not.toBeInTheDocument();

    await waitFor(() => expect(FakeWebSocket.instances.length).toBeGreaterThanOrEqual(1));
    const socket = FakeWebSocket.instances[0];
    act(() => {
      socket.emit({
        type: 'followup.created',
        room: 'research:res-1',
        timestamp: '2026-01-01T00:05:00Z',
        payload: {
          researchId: 'res-1',
          followup: {
            id: 'fu-live-1',
            reportId: 'rep-1',
            authorId: 'user-bob',
            authorName: 'Bob Editor',
            question: 'How fast does it sync?',
            answer: 'Sub-second via WebSockets [S1].',
            citationIds: [1],
            position: 0,
            provider: 'openrouter',
            model: 'model-a',
            insufficientEvidence: false,
            createdAt: '2026-01-01T00:05:00Z',
            updatedAt: '2026-01-01T00:05:00Z',
          },
          sources: baseReport.sources,
        },
      });
    });

    expect(await screen.findByText('How fast does it sync?')).toBeInTheDocument();
    expect(screen.getByText(/Asked by Bob Editor/i)).toBeInTheDocument();
  });
});
