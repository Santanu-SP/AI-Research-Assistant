import { API_BASE_URL, apiErrorMessage, apiRequest } from './api';
import {
  CollaboratorMember,
  CollaboratorsListResponse,
  EmailInviteResultResponse,
  InviteAcceptResponse,
  InvitePreviewResponse,
  InviteResourceType,
  InviteRole,
  LinkInviteCreateResponse,
} from '../types/collaboration';

const resourcePrefix = (type: InviteResourceType, id: string) =>
  `/${type === 'project' ? 'projects' : 'research'}/${encodeURIComponent(id)}`;

export const buildWebSocketUrl = (
  resourceType: InviteResourceType,
  resourceId: string,
): string => {
  const path = `${resourcePrefix(resourceType, resourceId)}`;
  if (/^https?:\/\//i.test(API_BASE_URL)) {
    return `${API_BASE_URL.replace(/^http/i, 'ws')}/ws${path}`;
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const base = API_BASE_URL.startsWith('/') ? API_BASE_URL : `/${API_BASE_URL}`;
  return `${protocol}//${window.location.host}${base.replace(/\/$/, '')}/ws${path}`;
};

export const collaborationService = {
  async listMembers(
    resourceType: InviteResourceType,
    resourceId: string,
  ): Promise<CollaboratorsListResponse> {
    return apiRequest<CollaboratorsListResponse>(
      `${resourcePrefix(resourceType, resourceId)}/members`,
    );
  },

  async inviteByEmail(
    resourceType: InviteResourceType,
    resourceId: string,
    email: string,
    role: InviteRole,
  ): Promise<EmailInviteResultResponse> {
    return apiRequest<EmailInviteResultResponse>(
      `${resourcePrefix(resourceType, resourceId)}/members`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, role }),
      },
    );
  },

  async updateMemberRole(
    resourceType: InviteResourceType,
    resourceId: string,
    memberUserId: string,
    role: InviteRole,
  ): Promise<CollaboratorMember> {
    return apiRequest<CollaboratorMember>(
      `${resourcePrefix(resourceType, resourceId)}/members/${encodeURIComponent(memberUserId)}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role }),
      },
    );
  },

  async removeMember(
    resourceType: InviteResourceType,
    resourceId: string,
    memberUserId: string,
  ): Promise<void> {
    await apiRequest<void>(
      `${resourcePrefix(resourceType, resourceId)}/members/${encodeURIComponent(memberUserId)}`,
      { method: 'DELETE' },
    );
  },

  async createInviteLink(
    resourceType: InviteResourceType,
    resourceId: string,
    role: InviteRole,
    options: { expiresInHours?: number | null; maxUses?: number | null } = {},
  ): Promise<LinkInviteCreateResponse> {
    return apiRequest<LinkInviteCreateResponse>(
      `${resourcePrefix(resourceType, resourceId)}/invites`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          role,
          expiresInHours: options.expiresInHours ?? 168,
          maxUses: options.maxUses ?? null,
        }),
      },
    );
  },

  async revokeInvite(
    resourceType: InviteResourceType,
    resourceId: string,
    inviteId: string,
  ): Promise<void> {
    await apiRequest<void>(
      `${resourcePrefix(resourceType, resourceId)}/invites/${encodeURIComponent(inviteId)}`,
      { method: 'DELETE' },
    );
  },

  async previewInvite(token: string): Promise<InvitePreviewResponse> {
    return apiRequest<InvitePreviewResponse>(
      `/collaboration/invites/${encodeURIComponent(token)}`,
    );
  },

  async acceptInvite(token: string): Promise<InviteAcceptResponse> {
    return apiRequest<InviteAcceptResponse>(
      `/collaboration/invites/${encodeURIComponent(token)}/accept`,
      { method: 'POST' },
    );
  },
};

export const collaborationErrorMessage = (error: unknown, fallback: string): string =>
  apiErrorMessage(error, fallback);
