"""Thread-safe realtime event bus abstraction shared by API routes and background workers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import logging
from threading import RLock
from typing import Any, Protocol
from uuid import UUID

logger = logging.getLogger(__name__)


def project_room(project_id: UUID | str) -> str:
    return f"project:{project_id}"


def research_room(research_id: UUID | str) -> str:
    return f"research:{research_id}"


class RealtimePublisher(Protocol):
    def publish_sync(
        self,
        rooms: Iterable[str],
        event_type: str,
        payload: Mapping[str, Any] | None = None,
        *,
        actor: Mapping[str, Any] | None = None,
    ) -> None: ...


_lock = RLock()
_active_publisher: RealtimePublisher | None = None


def set_active_publisher(publisher: RealtimePublisher | None) -> None:
    """Register the active application's RealtimeHub during ASGI lifespan."""
    global _active_publisher
    with _lock:
        _active_publisher = publisher


def clear_active_publisher(expected: RealtimePublisher | None = None) -> None:
    """Unregister the publisher on shutdown without clobbering a newer app."""
    global _active_publisher
    with _lock:
        if expected is None or _active_publisher is expected:
            _active_publisher = None


def actor_summary(
    user_id: UUID | str | None,
    name: str | None = None,
    email: str | None = None,
) -> dict[str, str] | None:
    if user_id is None:
        return None
    data = {"userId": str(user_id)}
    if name:
        data["name"] = name
    if email:
        data["email"] = email
    return data


def publish_realtime_event(
    rooms: Iterable[str],
    event_type: str,
    payload: Mapping[str, Any] | None = None,
    *,
    actor: Mapping[str, Any] | None = None,
) -> None:
    """Emit a realtime event to one or more rooms (safe no-op when no hub is active)."""
    with _lock:
        publisher = _active_publisher
    if publisher is None:
        return
    try:
        publisher.publish_sync(rooms, event_type, payload, actor=actor)
    except Exception:  # pragma: no cover - never fail business logic on realtime push
        logger.debug("Realtime broadcast failed for %s", event_type, exc_info=True)
