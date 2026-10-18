"""Base Pydantic schema with automatic snake_case to camelCase JSON aliasing."""

from pydantic import BaseModel, ConfigDict


def to_camel(value: str) -> str:
    """Convert a ``snake_case`` identifier into ``camelCase`` for JSON serialization."""
    first, *rest = value.split("_")
    return first + "".join(word.capitalize() for word in rest)


class ApiSchema(BaseModel):
    """Base schema using snake_case in Python and camelCase in JSON."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
    )