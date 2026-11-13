"""BYOK (Bring Your Own Key) API routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import Field
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.db.session import get_db
from app.schemas.base import ApiSchema
from app.services.auth import api_keys as api_key_service

router = APIRouter(prefix="/auth/api-keys", tags=["byok"])
DatabaseSession = Annotated[Session, Depends(get_db)]


class APIKeyUpsertRequest(ApiSchema):
    api_key: str = Field(min_length=8, max_length=512)


class APIKeyMetadataResponse(ApiSchema):
    id: UUID
    provider: str
    key_hint: str
    is_active: bool
    usage_requests: int
    usage_tokens: int
    last_used_at: datetime | None = None
    created_at: datetime


class APIKeyListResponse(ApiSchema):
    items: list[APIKeyMetadataResponse]


@router.get("", response_model=APIKeyListResponse)
def list_api_keys(
    session: DatabaseSession,
    user: CurrentUser,
) -> APIKeyListResponse:
    items = api_key_service.list_user_api_keys(session, user.id)
    return APIKeyListResponse(items=items)


@router.put("/{provider}", response_model=APIKeyMetadataResponse)
def save_api_key(
    provider: str,
    payload: APIKeyUpsertRequest,
    session: DatabaseSession,
    request: Request,
    user: CurrentUser,
) -> APIKeyMetadataResponse:
    return api_key_service.save_user_api_key(
        session,
        user.id,
        provider,
        payload.api_key,
        request.app.state.settings,
    )


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
def delete_api_key(
    provider: str,
    session: DatabaseSession,
    user: CurrentUser,
) -> Response:
    api_key_service.revoke_user_api_key(session, user.id, provider)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
