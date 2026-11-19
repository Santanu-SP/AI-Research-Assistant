"""In-process WebSocket room manager, presence tracker, and thread-safe dispatcher.

Architecture note:
Every WebSocket authenticates during handshake with a short-lived DB session
that closes immediately before the socket loop starts, so idle sockets never
hold Neon PostgreSQL pool connections open. All mutations emit events through
``RealtimeHub`` (ready to swap/extend with Redis Pub/Sub for multi-node scale).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import threading
from typing import Any
from uuid import UUID

from fastapi import WebSocket

from app.domain.collaboration import CollaboratorRole, role_satisfies

logger = logging.getLogger(__name__)

VALID_ACTIVITIES = frozenset({"viewing", "idle", "asking", "typing", "uploading", "editing"})
_SEND_TIMEOUT_SECONDS = 1.5


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ConnectedMember:
    websocket: WebSocket
    user_id: str
    name: str
    email: str
    role: CollaboratorRole
    activity: str = "viewing"
    connected_at: str = field(default_factory=_now_iso)


class RealtimeHub:
    """Manages active WebSocket rooms, user presence, and event fan-out."""

    def __init__(self) -> None:
        self._rooms: dict[str, dict[int, ConnectedMember]] = {}
        self._lock = threading.RLock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop | None) -> None:
        self._loop = loop

    @staticmethod
    def _serialize_presence(members: Iterable[ConnectedMember]) -> list[dict[str, Any]]:
        # Collapse multiple tabs opened by the same user, keeping the highest
        # activity priority (non-viewing activity beats passive viewing).
        by_user: dict[str, dict[str, Any]] = {}
        for item in members:
            existing = by_user.get(item.user_id)
            if existing is None:
                by_user[item.user_id] = {
                    "userId": item.user_id,
                    "name": item.name,
                    "email": item.email,
                    "role": item.role.value,
                    "activity": item.activity,
                    "connections": 1,
                }
            else:
                existing["connections"] = int(existing["connections"]) + 1
                if item.activity not in {"viewing", "idle"}:
                    existing["activity"] = item.activity
        return sorted(by_user.values(), key=lambda entry: (entry["name"].lower(), entry["userId"]))

    async def connect(
        self,
        room: str,
        websocket: WebSocket,
        *,
        user_id: UUID | str,
        name: str,
        email: str,
        role: CollaboratorRole,
    ) -> None:
        member = ConnectedMember(
            websocket=websocket,
            user_id=str(user_id),
            name=name,
            email=email,
            role=role,
            activity="viewing",
        )
        running_loop = asyncio.get_running_loop()
        if self._loop is None or self._loop.is_closed():
            self._loop = running_loop
        with self._lock:
            room_members = self._rooms.setdefault(room, {})
            room_members[id(websocket)] = member
        await self.broadcast_presence(room)

    async def disconnect(self, room: str, websocket: WebSocket) -> None:
        removed = False
        remaining = False
        with self._lock:
            room_members = self._rooms.get(room)
            if room_members is not None:
                removed = room_members.pop(id(websocket), None) is not None
                if not room_members:
                    self._rooms.pop(room, None)
                else:
                    remaining = True
        if removed and remaining:
            await self.broadcast_presence(room)

    async def set_activity(
        self,
        room: str,
        websocket: WebSocket,
        activity: str,
    ) -> None:
        cleaned = activity.strip().lower()
        if cleaned not in VALID_ACTIVITIES:
            return
        changed = False
        with self._lock:
            room_members = self._rooms.get(room)
            member = room_members.get(id(websocket)) if room_members else None
            if member is None:
                return
            if cleaned not in {"viewing", "idle"} and not role_satisfies(
                member.role, CollaboratorRole.EDITOR
            ):
                return
            if member.activity != cleaned:
                member.activity = cleaned
                changed = True
        if changed:
            await self.broadcast_presence(room)

    async def broadcast_presence(self, room: str) -> None:
        with self._lock:
            room_members = list((self._rooms.get(room) or {}).values())
        if not room_members:
            return
        presence = self._serialize_presence(room_members)
        await self.publish([room], "presence.sync", {"members": presence})

    async def snapshot_presence(self, room: str) -> list[dict[str, Any]]:
        with self._lock:
            room_members = list((self._rooms.get(room) or {}).values())
        return self._serialize_presence(room_members)

    async def publish(
        self,
        rooms: Iterable[str],
        event_type: str,
        payload: Mapping[str, Any] | None = None,
        *,
        actor: Mapping[str, Any] | None = None,
    ) -> None:
        unique_rooms = [room for room in dict.fromkeys(rooms) if room]
        if not unique_rooms:
            return

        targets: list[tuple[str, ConnectedMember]] = []
        with self._lock:
            for room in unique_rooms:
                for member in (self._rooms.get(room) or {}).values():
                    targets.append((room, member))

        if not targets:
            return

        body_base = dict(payload or {})
        actor_dict = dict(actor) if actor is not None else None
        timestamp = _now_iso()
        stale: list[tuple[str, WebSocket]] = []

        async def _send_one(room: str, member: ConnectedMember) -> None:
            envelope = {
                "type": event_type,
                "room": room,
                "timestamp": timestamp,
                "payload": body_base,
            }
            if actor_dict is not None:
                envelope["actor"] = actor_dict
            try:
                await asyncio.wait_for(
                    member.websocket.send_json(envelope),
                    timeout=_SEND_TIMEOUT_SECONDS,
                )
            except Exception:
                stale.append((room, member.websocket))

        await asyncio.gather(*(_send_one(room, member) for room, member in targets))

        if stale:
            affected_rooms: set[str] = set()
            with self._lock:
                for room, ws in stale:
                    room_members = self._rooms.get(room)
                    if room_members is not None and room_members.pop(id(ws), None) is not None:
                        affected_rooms.add(room)
                        if not room_members:
                            self._rooms.pop(room, None)
            for room in affected_rooms:
                await self.broadcast_presence(room)

    def publish_sync(
        self,
        rooms: Iterable[str],
        event_type: str,
        payload: Mapping[str, Any] | None = None,
        *,
        actor: Mapping[str, Any] | None = None,
    ) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        coro = self.publish(rooms, event_type, payload, actor=actor)
        if running_loop is loop:
            loop.create_task(coro)
            return

        future = asyncio.run_coroutine_threadsafe(coro, loop)
        try:
            future.result(timeout=2.0)
        except Exception:
            logger.debug("Realtime sync dispatch did not complete", exc_info=True)
