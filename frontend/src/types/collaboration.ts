export type CollaboratorRole = 'owner' | 'editor' | 'viewer';
export type InviteRole = 'editor' | 'viewer';
export type InviteResourceType = 'project' | 'research';
export type PresenceActivity =
  | 'viewing'
  | 'idle'
  | 'asking'
  | 'typing'
  | 'uploading'
  | 'editing';

export interface PresenceMember {
  userId: string;
  name: string;
  email: string;
  role: CollaboratorRole;
  activity: PresenceActivity;
  connections: number;
}

export interface RealtimeActor {
  userId: string;
  name?: string;
  email?: string;
}

export interface RealtimeEventEnvelope<T = Record<string, unknown>> {
  type: string;
  room: string;
  timestamp: string;
  actor?: RealtimeActor;
  payload: T;
}

export interface CollaboratorMember {
  userId: string;
  name: string;
  email: string;
  role: CollaboratorRole;
  isOwner: boolean;
  joinedAt: string;
}

export interface CollaborationInvite {
  id: string;
  resourceType: InviteResourceType;
  projectId: string | null;
  researchId: string | null;
  role: InviteRole;
  targetEmail: string | null;
  maxUses: number | null;
  useCount: number;
  expiresAt: string | null;
  revokedAt: string | null;
  acceptedAt: string | null;
  createdAt: string;
}

export interface CollaboratorsListResponse {
  resourceType: InviteResourceType;
  resourceId: string;
  myRole: CollaboratorRole;
  version: number;
  members: CollaboratorMember[];
  invites: CollaborationInvite[];
}

export interface EmailInviteResultResponse {
  memberAdded: boolean;
  member: CollaboratorMember | null;
  invite: CollaborationInvite;
  invitePath: string;
  token: string;
}

export interface LinkInviteCreateResponse {
  invite: CollaborationInvite;
  invitePath: string;
  token: string;
}

export interface InvitePreviewResponse {
  resourceType: InviteResourceType;
  resourceId: string;
  resourceTitle: string;
  inviterName: string | null;
  role: InviteRole;
  targetEmail: string | null;
  expiresAt: string | null;
  alreadyMember: boolean;
}

export interface InviteAcceptResponse {
  resourceType: InviteResourceType;
  resourceId: string;
  role: CollaboratorRole;
  redirectPath: string;
}
