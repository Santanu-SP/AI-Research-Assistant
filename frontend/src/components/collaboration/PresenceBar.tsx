import React from 'react';
import { Wifi, WifiOff } from 'lucide-react';
import { PresenceMember } from '../../types/collaboration';
import type { RealtimeConnectionState } from '../../hooks/useRealtimeRoom';

interface PresenceBarProps {
  presence: PresenceMember[];
  currentUserId?: string | null;
  connectionState: RealtimeConnectionState;
}

const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('') || '?';

const ACTIVITY_LABELS: Record<string, string> = {
  asking: 'asking AI…',
  typing: 'typing…',
  uploading: 'uploading…',
  editing: 'editing…',
};

export const PresenceBar: React.FC<PresenceBarProps> = ({
  presence,
  currentUserId,
  connectionState,
}) => {
  const activeCollaborators = presence.filter((member) => member.userId !== currentUserId);
  const workingNotice = activeCollaborators.find((member) => ACTIVITY_LABELS[member.activity]);

  if (connectionState === 'idle') return null;

  return (
    <div
      className="flex flex-wrap items-center gap-2 text-xs text-ink-muted"
      aria-live="polite"
    >
      <span
        className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-medium ${
          connectionState === 'connected'
            ? 'border-accent-line bg-accent-soft text-accent'
            : connectionState === 'reconnecting' || connectionState === 'connecting'
              ? 'border-line bg-subtle text-ink-soft'
              : 'border-line bg-subtle text-ink-muted'
        }`}
        title={
          connectionState === 'connected'
            ? 'Real-time sync active'
            : connectionState === 'reconnecting'
              ? 'Reconnecting real-time sync…'
              : 'Live sync paused'
        }
      >
        {connectionState === 'disconnected' ? (
          <WifiOff className="h-3 w-3" />
        ) : (
          <Wifi className="h-3 w-3" />
        )}
        <span>
          {connectionState === 'connected'
            ? presence.length > 1
              ? `Live · ${presence.length} online`
              : 'Live'
            : connectionState === 'reconnecting'
              ? 'Reconnecting…'
              : connectionState === 'connecting'
                ? 'Connecting…'
                : 'Offline'}
        </span>
      </span>

      {presence.length > 0 && (
        <div className="flex items-center -space-x-1.5" aria-label="Active collaborators">
          {presence.slice(0, 5).map((member) => (
            <span
              key={member.userId}
              title={`${member.name} (${member.role})${
                ACTIVITY_LABELS[member.activity] ? ` — ${ACTIVITY_LABELS[member.activity]}` : ''
              }`}
              className={`inline-flex h-6 w-6 items-center justify-center rounded-full border border-panel text-[10px] font-semibold shadow-2xs ${
                member.userId === currentUserId
                  ? 'bg-solid text-on-solid'
                  : 'bg-subtle text-ink'
              }`}
            >
              {initials(member.name)}
            </span>
          ))}
          {presence.length > 5 && (
            <span className="inline-flex h-6 w-6 items-center justify-center rounded-full border border-panel bg-subtle text-[10px] font-medium text-ink-soft">
              +{presence.length - 5}
            </span>
          )}
        </div>
      )}

      {workingNotice && (
        <span className="truncate text-[11px] font-medium text-accent">
          {workingNotice.name.split(/\s+/)[0]} is {ACTIVITY_LABELS[workingNotice.activity]}
        </span>
      )}
    </div>
  );
};
