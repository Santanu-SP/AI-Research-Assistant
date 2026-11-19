import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { CheckCircle2, Users } from 'lucide-react';
import { CenteredLoadingState } from '../components/common/LoadingState';
import { ErrorState } from '../components/common/ErrorState';
import { PrimaryButton } from '../components/common/PrimaryButton';
import {
  collaborationErrorMessage,
  collaborationService,
} from '../services/collaboration.service';
import { InvitePreviewResponse } from '../types/collaboration';
import { useToast } from '../app/ToastContext';

export const JoinInvitePage: React.FC = () => {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const { addToast } = useToast();
  const [preview, setPreview] = useState<InvitePreviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [joining, setJoining] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setError('Invite link is missing.');
      setLoading(false);
      return;
    }
    let active = true;
    setLoading(true);
    setError(null);
    collaborationService
      .previewInvite(token)
      .then((res) => {
        if (active) setPreview(res);
      })
      .catch((err) => {
        if (active) {
          setError(collaborationErrorMessage(err, 'This invite link could not be loaded.'));
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [token]);

  const handleJoin = async () => {
    if (!token || joining) return;
    setJoining(true);
    setError(null);
    try {
      const accepted = await collaborationService.acceptInvite(token);
      window.dispatchEvent(new Event('research-history:refresh'));
      addToast({
        type: 'success',
        title: 'Joined workspace',
        description: `You now have ${accepted.role} access.`,
      });
      navigate(accepted.redirectPath, { replace: true });
    } catch (err) {
      setError(collaborationErrorMessage(err, 'Could not accept this invite.'));
    } finally {
      setJoining(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <CenteredLoadingState label="Checking invite link…" />
      </div>
    );
  }

  if (error || !preview) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <div className="w-full max-w-md">
          <ErrorState
            title="Invite unavailable"
            message={error ?? 'This invite link is no longer valid.'}
            onRetry={() => navigate('/projects', { replace: true })}
          />
        </div>
      </div>
    );
  }

  const kindLabel = preview.resourceType === 'project' ? 'project' : 'research chat';
  const roleLabel = preview.role === 'editor' ? 'Editor (can upload, edit & ask AI)' : 'Viewer (read-only)';

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-md rounded-xl border border-line bg-panel p-6 shadow-md">
        <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-accent-soft text-accent">
          <Users className="h-5 w-5" />
        </div>
        <h1 className="text-lg font-semibold text-ink">
          Join shared {kindLabel}
        </h1>
        <p className="mt-1.5 text-sm text-ink-soft">
          {preview.inviterName ? `${preview.inviterName} invited you to collaborate on ` : 'You were invited to collaborate on '}
          <span className="font-medium text-ink">{preview.resourceTitle}</span>.
        </p>

        <div className="mt-4 rounded-lg border border-line bg-subtle/40 px-3.5 py-2.5 text-xs text-ink-soft">
          Access level: <span className="font-medium text-ink">{roleLabel}</span>
        </div>

        <div className="mt-6 flex items-center justify-end gap-2.5">
          <PrimaryButton
            type="button"
            variant="outline"
            onClick={() => navigate('/projects')}
          >
            Cancel
          </PrimaryButton>
          <PrimaryButton
            type="button"
            isLoading={joining}
            onClick={() => void handleJoin()}
          >
            <CheckCircle2 className="h-4 w-4" />
            {preview.alreadyMember ? `Open ${kindLabel}` : `Join ${kindLabel}`}
          </PrimaryButton>
        </div>
      </div>
    </div>
  );
};
