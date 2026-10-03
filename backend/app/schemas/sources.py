"""Project source ingestion request contracts."""

from pydantic import ConfigDict, Field

from app.schemas.base import ApiSchema


class UrlSourceCreate(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=8, max_length=2048)


class DoiSourceCreate(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    doi: str = Field(min_length=6, max_length=512)


class OpenAlexSourceCreate(ApiSchema):
    model_config = ConfigDict(extra="forbid")

    identifier: str = Field(min_length=2, max_length=512)
