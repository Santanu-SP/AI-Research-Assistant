"""Remember why the model failed on a research run.

Adds ``research.failure_provider``, ``failure_model`` and ``failure_type`` so
a failed run can explain itself, e.g. "Gemini 2.5 Pro hit its free limit".
Only the provider, the model name and a short error type are stored, never
keys or raw provider messages.

Revision ID: 0018_research_model_failure
Revises: 0017_research_documents
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0018_research_model_failure"
down_revision: str | None = "0017_research_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("research") as batch_op:
        batch_op.add_column(sa.Column("failure_provider", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("failure_model", sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column("failure_type", sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("research") as batch_op:
        batch_op.drop_column("failure_type")
        batch_op.drop_column("failure_model")
        batch_op.drop_column("failure_provider")
