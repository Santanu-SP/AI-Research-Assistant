import { useCallback, useEffect, useRef, useState } from 'react';
import {
  InviteResourceType,
  PresenceActivity,
  PresenceMember,
  RealtimeEventEnvelope,
} from '../types/collaboration';
import { buildWebSocketUrl } from '../services/collaboration.service';

export type RealtimeConnectionState =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'disconnected';

interface UseRealtimeRoomOptions {
  resourceType: InviteResourceType;
  resourceId: string | null | undefined;
  enabled?: boolean;
  onEvent?: (event: RealtimeEventEnvelope) => void;
}

const RECONNECT_DELAYS_MS = [1000, 2000, 4000, 8000, 12000] as const;
const HEARTBEAT_INTERVAL_MS = 25_000;
const TERMINAL_CLOSE_CODES = new Set([4401, 4403, 4404]);

export function useRealtimeRoom({
  resourceType,
  resourceId,
  enabled = true,
  onEvent,
}: UseRealtimeRoomOptions) {
  const [connectionState, setConnectionState] = useState<RealtimeConnectionState>('idle');
  const [presence, setPresence] = useState<PresenceMember[]>([]);
  const socketRef = useRef<WebSocket | null>(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const sendActivity = useCallback((activity: PresenceActivity) => {
    const ws = socketRef.current;
    if (!ws || ws.readyState !== 1) return;
    try {
      ws.send(JSON.stringify({ type: 'activity', activity }));
    } catch {
      // Ignore transient send failures while socket reconnects.
    }
  }, []);

  useEffect(() => {
    const hasWindow = typeof window !== 'undefined' && typeof window.WebSocket === 'function';
    const isUnmockedTestSocket =
      hasWindow &&
      import.meta.env.MODE === 'test' &&
      Function.prototype.toString.call(window.WebSocket).includes('[native code]');
    if (!enabled || !resourceId || !hasWindow || isUnmockedTestSocket) {
      setConnectionState('idle');
      setPresence([]);
      return;
    }

    let disposed = false;
    let attempt = 0;
    let reconnectTimer: number | undefined;
    let heartbeatTimer: number | undefined;

    const clearTimers = () => {
      if (reconnectTimer !== undefined) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = undefined;
      }
      if (heartbeatTimer !== undefined) {
        window.clearInterval(heartbeatTimer);
        heartbeatTimer = undefined;
      }
    };

    const connect = () => {
      if (disposed) return;
      setConnectionState(attempt === 0 ? 'connecting' : 'reconnecting');

      let ws: WebSocket;
      try {
        ws = new window.WebSocket(buildWebSocketUrl(resourceType, resourceId));
      } catch {
        setConnectionState('disconnected');
        return;
      }
      socketRef.current = ws;

      ws.onopen = () => {
        if (disposed) {
          ws.close();
          return;
        }
        attempt = 0;
        setConnectionState('connected');
        heartbeatTimer = window.setInterval(() => {
          if (ws.readyState === 1) {
            try {
              ws.send(JSON.stringify({ type: 'ping' }));
            } catch {
              // Handled on close.
            }
          }
        }, HEARTBEAT_INTERVAL_MS);
      };

      ws.onmessage = (event) => {
        if (disposed || typeof event.data !== 'string') return;
        let parsed: RealtimeEventEnvelope;
        try {
          parsed = JSON.parse(event.data) as RealtimeEventEnvelope;
        } catch {
          return;
        }
        if (!parsed || typeof parsed.type !== 'string') return;
        if (parsed.type === 'pong') return;
        if (parsed.type === 'presence.sync') {
          const members = (parsed.payload as { members?: PresenceMember[] })?.members;
          if (Array.isArray(members)) {
            setPresence(members);
          }
          return;
        }
        onEventRef.current?.(parsed);
      };

      ws.onerror = () => {
        // Close handler handles cleanup and backoff reconnect cleanly.
      };

      ws.onclose = (event) => {
        clearTimers();
        if (socketRef.current === ws) {
          socketRef.current = null;
        }
        if (disposed) return;
        if (event && TERMINAL_CLOSE_CODES.has(event.code)) {
          setConnectionState('disconnected');
          setPresence([]);
          return;
        }
        const delay =
          RECONNECT_DELAYS_MS[Math.min(attempt, RECONNECT_DELAYS_MS.length - 1)];
        attempt += 1;
        setConnectionState('reconnecting');
        reconnectTimer = window.setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      disposed = true;
      clearTimers();
      const ws = socketRef.current;
      socketRef.current = null;
      if (ws && (ws.readyState === 0 || ws.readyState === 1)) {
        try {
          ws.close(1000, 'route_leave');
        } catch {
          // Ignore close failures during unmount.
        }
      }
    };
  }, [resourceType, resourceId, enabled]);

  return {
    connectionState,
    presence,
    sendActivity,
  };
}
