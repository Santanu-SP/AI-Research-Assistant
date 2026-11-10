from datetime import datetime
from uuid import UUID
import re

from pydantic import BaseModel, Field, field_validator

from app.schemas.base import ApiSchema

# A short deny-list of the passwords attackers try first. It is not a full
# breached-password check, but it stops the most common choices outright.
COMMON_PASSWORDS = frozenset(
    {
        "password", "password1", "password12", "password123", "password1234",
        "12345678", "123456789", "1234567890", "qwertyui", "qwerty123",
        "11111111", "iloveyou", "abc12345", "letmein1", "welcome1",
        "admin123", "passw0rd", "sunshine", "football", "baseball",
    }
)


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=1024)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name is required")
        return value

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("password")
    @classmethod
    def reject_weak_password(cls, value: str) -> str:
        if len(set(value)) < 4:
            raise ValueError("Password is too simple; use a mix of characters")
        if value.strip().lower() in COMMON_PASSWORDS:
            raise ValueError("This password is too common; choose another one")
        return value


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class UserResponse(ApiSchema):
    id: UUID
    name: str
    email: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
