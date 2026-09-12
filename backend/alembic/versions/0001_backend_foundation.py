"""Establish migration infrastructure without domain tables.

Revision ID: 0001_backend_foundation
Revises:
Create Date: 2026-09-12
"""

from collections.abc import Sequence

revision: str = "0001_backend_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
