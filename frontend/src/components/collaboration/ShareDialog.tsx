import React, { useCallback, useEffect, useState } from 'react';
import {
  Check,
  Copy,
  Link2,
  Mail,
  Shield,
  Trash2,
  UserPlus,
  Users,
  X,
} from 'lucide-react';
import {
  CollaborationInvite,
  CollaboratorMember,
  CollaboratorRole,
  InviteResourceType,
  InviteRole,
} from '../../types/collaboration';
import {
  collaborationErrorMessage,
  collaborationService,
} from '../../services/collaboration.service';
import { useAuth } from '../../app/AuthContext';
import { useOptionalToast } from '../../app/ToastContext';
import { PrimaryButton } from '../common/PrimaryButton';

interface ShareDialogProps {
  isOpen: boolean;
  resourceType: InviteResourceType;
  resourceId: string;
  resourceTitle: string;
  onClose: () => void;
  onChanged?: () => void;
}

const ROLE_LABELS: Record<CollaboratorRole, string> = {
  owner: 'Owner',
  editor: 'Can edit',
  viewer: 'View only',
};

export const ShareDialog: React.FC<ShareDialogProps> = ({
  isOpen,
  resourceType,
  resourceId,
  resourceTitle,
  onClose,
  onChanged,
}) => {
  const { user } = useAuth();
  const toast = useOptionalToast();
  const addToast = useCallback(
    (payload: Parameters<NonNullable<typeof toast>['addToast']>[0]) => {
      toast?.addToast(payload);
    },
    [toast]
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [myRole, setMyRole] = useState<CollaboratorRole>('viewer');
  const [members, setMembers] = useState<CollaboratorMember[]>([]);
  const [invites, setInvites] = useState<CollaborationInvite[]>([]);

  const [email, setEmail] = useState('');
  const [emailRole, setEmailRole] = useState<InviteRole>('editor');
  const [invitingEmail, setInvitingEmail] = useState(false);

  const [linkRole, setLinkRole] = useState<InviteRole>('editor');
  const [creatingLink, setCreatingLink] = useState(false);
  const [latestLink, setLatestLink] = useState<string | null>(null);
  const [copiedLink, setCopiedLink] = useState(false);
  const [busyUserId, setBusyUserId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await collaborationService.listMembers(resourceType, resourceId);
      setMyRole(data.myRole);
      setMembers(data.members);
      setInvites(data.invites);
    } catch (err) {
      setError(collaborationErrorMessage(err, 'Could not load collaborators.'));
    } finally {
      setLoading(false);
    }
  }, [resourceType, resourceId]);

  useEffect(() => {
    if (!isOpen) return;
    setLatestLink(null);
    setCopiedLink(false);
    void load();
  }, [isOpen, load]);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const isOwner = myRole === 'owner';
  const kindLabel = resourceType === 'project' ? 'project' : 'research chat';

  const toAbsoluteInviteUrl = (invitePath: string) =>
    `${window.location.origin}${invitePath}`;

  const handleCopyUrl = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url);
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2000);
    } catch {
      setCopiedLink(false);
    }
  };

  const handleInviteEmail = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleaned = email.trim();
    if (!cleaned || invitingEmail) return;
    setInvitingEmail(true);
    setError(null);
    try {
      const res = await collaborationService.inviteByEmail(
        resourceType,
        resourceId,
        cleaned,
        emailRole,
      );
      const absolute = toAbsoluteInviteUrl(res.invitePath);
      setEmail('');
      if (res.memberAdded && res.member) {
        addToast({
          type: 'success',
          title: 'Collaborator added',
          description: `${res.member.name} now has ${ROLE_LABELS[res.member.role].toLowerCase()} access.`,
        });
      } else {
        setLatestLink(absolute);
        addToast({
          type: 'success',
          title: 'Invite created',
          description: `Share the link with ${cleaned} so they can join after signing up.`,
        });
      }
      await load();
      onChanged?.();
    } catch (err) {
      setError(collaborationErrorMessage(err, 'Could not send invite.'));
    } finally {
      setInvitingEmail(false);
    }
  };

  const handleCreateLink = async () => {
    if (creatingLink) return;
    setCreatingLink(true);
    setError(null);
    try {
      const res = await collaborationService.createInviteLink(
        resourceType,
        resourceId,
        linkRole,
      );
      const absolute = toAbsoluteInviteUrl(res.invitePath);
      setLatestLink(absolute);
      await handleCopyUrl(absolute);
      await load();
    } catch (err) {
      setError(collaborationErrorMessage(err, 'Could not create invite link.'));
    } finally {
      setCreatingLink(false);
    }
  };

  const handleRevokeInvite = async (inviteId: string) => {
    setError(null);
    try {
      await collaborationService.revokeInvite(resourceType, resourceId, inviteId);
      setInvites((prev) => prev.filter((item) => item.id !== inviteId));
    } catch (err) {
      setError(collaborationErrorMessage(err, 'Could not revoke invite.'));
    }
  };

  const handleRoleChange = async (memberUserId: string, nextRole: InviteRole) => {
    setBusyUserId(memberUserId);
    setError(null);
    try {
      const updated = await collaborationService.updateMemberRole(
        resourceType,
        resourceId,
        memberUserId,
        nextRole,
      );
      setMembers((prev) =>
        prev.map((m) => (m.userId === memberUserId ? updated : m)),
      );
      onChanged?.();
    } catch (err) {
      setError(collaborationErrorMessage(err, 'Could not update role.'));
    } finally {
      setBusyUserId(null);
    }
  };

  const handleRemoveMember = async (memberUserId: string) => {
    setBusyUserId(memberUserId);
    setError(null);
    try {
      await collaborationService.removeMember(resourceType, resourceId, memberUserId);
      setMembers((prev) => prev.filter((m) => m.userId !== memberUserId));
      onChanged?.();
      if (memberUserId === user?.id) {
        onClose();
      }
    } catch (err) {
      setError(collaborationErrorMessage(err, 'Could not remove collaborator.'));
    } finally {
      setBusyUserId(null);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4 overlay-enter"
      onMouseDown={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="share-dialog-title"
        className="w-full max-w-lg overflow-hidden rounded-xl border border-line bg-panel shadow-xl dialog-enter"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <div className="min-w-0">
            <h3 id="share-dialog-title" className="flex items-center gap-2 text-base font-semibold text-ink">
              <Users className="h-4 w-4 text-accent" />
              <span className="truncate">Share {kindLabel}</span>
            </h3>
            <p className="mt-0.5 truncate text-xs text-ink-muted">{resourceTitle}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close share dialog"
            className="rounded-md p-1.5 text-ink-muted transition-colors hover:bg-subtle hover:text-ink"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="max-h-[75vh] space-y-5 overflow-y-auto p-5">
          {error && (
            <p role="alert" className="rounded-md border border-danger-line bg-danger-soft px-3 py-2 text-xs text-danger">
              {error}
            </p>
          )}

          {isOwner && (
            <>
              <form onSubmit={(e) => void handleInviteEmail(e)} className="space-y-2">
                <label htmlFor="invite-email-input" className="field-label flex items-center gap-1.5">
                  <Mail className="h-3.5 w-3.5 text-ink-muted" />
                  Invite by email
                </label>
                <div className="flex flex-wrap gap-2">
                  <input
                    id="invite-email-input"
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="teammate@example.com"
                    className="field h-9 min-w-[180px] flex-1 text-[13px]"
                  />
                  <select
                    aria-label="Invite email role"
                    value={emailRole}
                    onChange={(e) => setEmailRole(e.target.value as InviteRole)}
                    className="field h-9 w-28 text-[13px]"
                  >
                    <option value="editor">Can edit</option>
                    <option value="viewer">View only</option>
                  </select>
                  <PrimaryButton type="submit" size="sm" isLoading={invitingEmail}>
                    <UserPlus className="h-3.5 w-3.5" />
                    Invite
                  </PrimaryButton>
                </div>
                <p className="text-[11px] text-ink-muted">
                  Existing users get access right away. Collaborators use their own AI credits.
                </p>
              </form>

              <div className="space-y-2 border-t border-line pt-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="field-label flex items-center gap-1.5 mb-0">
                    <Link2 className="h-3.5 w-3.5 text-ink-muted" />
                    Shareable invite link
                  </span>
                  <div className="flex items-center gap-2">
                    <select
                      aria-label="Invite link role"
                      value={linkRole}
                      onChange={(e) => setLinkRole(e.target.value as InviteRole)}
                      className="field h-8 w-28 text-xs"
                    >
                      <option value="editor">Can edit</option>
                      <option value="viewer">View only</option>
                    </select>
                    <PrimaryButton
                      type="button"
                      variant="outline"
                      size="sm"
                      isLoading={creatingLink}
                      onClick={() => void handleCreateLink()}
                    >
                      Create link
                    </PrimaryButton>
                  </div>
                </div>

                {latestLink && (
                  <div className="flex items-center gap-2 rounded-lg border border-accent-line bg-accent-soft/40 p-2">
                    <input
                      type="text"
                      readOnly
                      aria-label="Generated invite link"
                      value={latestLink}
                      className="min-w-0 flex-1 bg-transparent px-1.5 font-mono text-xs text-ink outline-none"
                    />
                    <button
                      type="button"
                      onClick={() => void handleCopyUrl(latestLink)}
                      className="inline-flex h-7 items-center gap-1 rounded bg-panel px-2 text-xs font-medium text-ink shadow-2xs hover:bg-subtle"
                    >
                      {copiedLink ? <Check className="h-3.5 w-3.5 text-accent" /> : <Copy className="h-3.5 w-3.5" />}
                      {copiedLink ? 'Copied' : 'Copy'}
                    </button>
                  </div>
                )}

                {invites.length > 0 && (
                  <div className="space-y-1.5 pt-1">
                    <p className="text-[11px] font-medium text-ink-muted">
                      Active invite links ({invites.length})
                    </p>
                    {invites.map((inv) => (
                      <div
                        key={inv.id}
                        className="flex items-center justify-between gap-2 rounded-md border border-line bg-subtle/40 px-2.5 py-1.5 text-xs"
                      >
                        <span className="truncate text-ink-soft">
                          {inv.targetEmail ? `Email: ${inv.targetEmail}` : 'Share link'} ·{' '}
                          <span className="font-medium text-ink">{ROLE_LABELS[inv.role]}</span> ·{' '}
                          {inv.useCount} used
                        </span>
                        <button
                          type="button"
                          onClick={() => void handleRevokeInvite(inv.id)}
                          className="text-[11px] font-medium text-danger hover:underline"
                        >
                          Revoke
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}

          <div className={isOwner ? 'border-t border-line pt-4' : ''}>
            <h4 className="mb-2.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
              <Shield className="h-3.5 w-3.5" />
              People with access ({members.length})
            </h4>

            {loading ? (
              <p className="py-2 text-xs text-ink-muted">Loading collaborators…</p>
            ) : (
              <div className="divide-y divide-line rounded-lg border border-line bg-subtle/20">
                {members.map((member) => {
                  const isSelf = member.userId === user?.id;
                  return (
                    <div
                      key={member.userId}
                      className="flex items-center justify-between gap-3 px-3 py-2.5"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-[13px] font-medium text-ink">
                          {member.name}
                          {isSelf ? ' (You)' : ''}
                        </p>
                        <p className="truncate text-xs text-ink-muted">{member.email}</p>
                      </div>

                      <div className="flex shrink-0 items-center gap-2">
                        {member.isOwner ? (
                          <span className="rounded-full bg-subtle px-2.5 py-0.5 text-[11px] font-medium text-ink-soft">
                            Owner
                          </span>
                        ) : isOwner ? (
                          <>
                            <select
                              aria-label={`Role for ${member.name}`}
                              disabled={busyUserId === member.userId}
                              value={member.role}
                              onChange={(e) =>
                                void handleRoleChange(member.userId, e.target.value as InviteRole)
                              }
                              className="field h-7 px-2 text-xs"
                            >
                              <option value="editor">Can edit</option>
                              <option value="viewer">View only</option>
                            </select>
                            <button
                              type="button"
                              aria-label={`Remove ${member.name}`}
                              disabled={busyUserId === member.userId}
                              onClick={() => void handleRemoveMember(member.userId)}
                              className="rounded p-1 text-ink-muted transition-colors hover:bg-danger-soft hover:text-danger"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </>
                        ) : (
                          <>
                            <span className="rounded-full bg-subtle px-2 py-0.5 text-[11px] font-medium text-ink-soft">
                              {ROLE_LABELS[member.role]}
                            </span>
                            {isSelf && (
                              <button
                                type="button"
                                disabled={busyUserId === member.userId}
                                onClick={() => void handleRemoveMember(member.userId)}
                                className="text-xs font-medium text-danger hover:underline"
                              >
                                Leave
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
