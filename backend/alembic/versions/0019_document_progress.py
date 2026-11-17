"""Show which step a file is on while it is being prepared.

Adds ``documents.processing_stage`` (reading, ocr, embedding, saving) and
``documents.processing_progress`` (0-100 within the embedding step), so the
library can say more than "Preparing…". Both are cleared once the file is
ready or has failed.

Revision ID: 0019_document_progress
Revises: 0018_research_model_failure
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0019_document_progress"
down_revision: str | None = "0018_research_model_failure"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(sa.Column("processing_stage", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("processing_progress", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_column("processing_progress")
        batch_op.drop_column("processing_stage")
