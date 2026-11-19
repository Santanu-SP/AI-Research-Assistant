"""Authenticated WebSocket endpoints for live project and research room sync."""

from __future__ import annotations

import json
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool

from app.core.errors import AppError
from app.core.realtime_bus import project_room, research_room
from app.domain.collaboration import CollaboratorRole
from app.services.auth.sessions import SESSION_COOKIE, current_user
from app.services.collaboration.access import require_project_access, require_research_access
from app.services.realtime.hub import RealtimeHub

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["realtime"])


def _authenticate_room_sync(
    websocket: WebSocket,
    *,
    kind: str,
    target_id: UUID,
) -> tuple[UUID, str, str, CollaboratorRole]:
    settings = websocket.app.state.settings
    origin = websocket.headers.get("origin")
    if origin is not None and not settings.is_allowed_origin(origin):
        raise AppError("Origin is not allowed", status_code=403, code="origin_not_allowed")
    if settings.app_environment == "production" and settings.require_origin_header and origin is None:
        raise AppError("Origin header is required", status_code=403, code="origin_required")

    token = websocket.cookies.get(SESSION_COOKIE)
    session_factory = websocket.app.state.db_session_factory
    # Close the DB session immediately after verifying access so idle sockets
    # never consume Postgres connection pool slots.
    with session_factory() as session:
        user = current_user(
            session,
            token,
            session_days=settings.auth_session_days,
            inactivity_days=settings.auth_inactivity_days,
        )
        if kind == "project":
            _, role = require_project_access(
                session, target_id, user.id, min_role=CollaboratorRole.VIEWER
            )
        else:
            _, role = require_research_access(
                session, target_id, user.id, min_role=CollaboratorRole.VIEWER
            )
        return user.id, user.name, user.email, role


async def _serve_room_socket(
    websocket: WebSocket,
    *,
    kind: str,
    target_id: UUID,
    room: str,
) -> None:
    try:
        user_id, name, email, role = await run_in_threadpool(
            _authenticate_room_sync,
            websocket,
            kind=kind,
            target_id=target_id,
        )
    except AppError as exc:
        code = 4401 if exc.status_code == 401 else (4403 if exc.status_code == 403 else 4404)
        await websocket.close(code=code, reason=exc.code)
        return
    except Exception:
        logger.debug("WebSocket authentication error", exc_info=True)
        await websocket.close(code=4401, reason="authentication_failed")
        return

    hub: RealtimeHub = websocket.app.state.realtime_hub
    await websocket.accept()
    await hub.connect(room, websocket, user_id=user_id, name=name, email=email, role=role)
    try:
        while True:
            raw = await websocket.receive_text()
            if len(raw) > 4096:
                continue
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            msg_type = str(message.get("type") or "").strip().lower()
            if msg_type == "ping":
                await websocket.send_json({"type": "pong", "room": room})
            elif msg_type == "activity":
                await hub.set_activity(room, websocket, str(message.get("activity") or ""))
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("WebSocket room loop closed unexpectedly", exc_info=True)
    finally:
        await hub.disconnect(room, websocket)


@router.websocket("/projects/{project_id}")
async def project_realtime_socket(websocket: WebSocket, project_id: UUID) -> None:
    await _serve_room_socket(
        websocket,
        kind="project",
        target_id=project_id,
        room=project_room(project_id),
    )


@router.websocket("/research/{research_id}")
async def research_realtime_socket(websocket: WebSocket, research_id: UUID) -> None:
    await _serve_room_socket(
        websocket,
        kind="research",
        target_id=research_id,
        room=research_room(research_id),
    )
