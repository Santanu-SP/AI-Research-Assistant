"""Pydantic schemas for system health and status endpoints."""

from app.schemas.base import ApiSchema


class HealthResponse(ApiSchema):
    """Health check response payload."""

    status: str
    service: str
    environment: str