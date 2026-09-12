"""SQLAlchemy model registry used by the app and Alembic."""

from app.models.document import Document
from app.models.research import Research

__all__ = ["Document", "Research"]
