"""Pydantic request and response schemas for user authentication."""

from datetime import datetime
import re
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.base import ApiSchema

EMAIL_REGEX_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class RegisterRequest(BaseModel):
    """Payload for registering a new user account with email and password."""

    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=1024)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Name is required")
        return cleaned

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not EMAIL_REGEX_PATTERN.fullmatch(cleaned):
            raise ValueError("Enter a valid email address")
        return cleaned


class LoginRequest(BaseModel):
    """Payload for authenticating an existing user with email and password."""

    email: str
    password: str


class UserResponse(ApiSchema):
    """Public profile representation of an authenticated user."""

    id: UUID
    name: str
    email: str
    is_active: bool
    created_at: datetime
    updated_at: datetime