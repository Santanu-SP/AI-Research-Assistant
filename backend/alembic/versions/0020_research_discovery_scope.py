"""Let a research run find its own sources in the background.

Adds ``research.discovery_scope``. When it is set, the background job
searches the trusted providers, imports what it finds and attaches it to the
run before answering, instead of the request doing all of that up front.

Revision ID: 0020_research_discovery_scope
Revises: 0019_document_progress
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0020_research_discovery_scope"
down_revision: str | None = "0019_document_progress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("research") as batch_op:
        batch_op.add_column(sa.Column("discovery_scope", sa.String(length=16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("research") as batch_op:
        batch_op.drop_column("discovery_scope")
