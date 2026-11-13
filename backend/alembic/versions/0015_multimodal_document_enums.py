"""Expand document file_type, source_type, and content_level enums for multimodal sources.

Revision ID: 0015_multimodal_document_enums
Revises: 0014_neon_multimodal_router_byok
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0015_multimodal_document_enums"
down_revision: str | None = "0014_neon_multimodal_router_byok"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


old_file_type = sa.Enum(
    "pdf",
    "docx",
    "txt",
    name="document_type",
    native_enum=False,
    create_constraint=True,
)
new_file_type = sa.Enum(
    "pdf",
    "docx",
    "txt",
    "pptx",
    "xlsx",
    "html",
    "audio",
    "video",
    "image",
    "youtube",
    "web",
    name="document_type",
    native_enum=False,
    create_constraint=True,
)

old_source_type = sa.Enum(
    "uploaded_file",
    "web_page",
    "doi",
    "openalex",
    "crossref",
    name="source_type",
    native_enum=False,
    create_constraint=True,
)
new_source_type = sa.Enum(
    "uploaded_file",
    "web_page",
    "youtube_video",
    "audio_file",
    "video_file",
    "image_file",
    "doi",
    "openalex",
    "crossref",
    name="source_type",
    native_enum=False,
    create_constraint=True,
)

old_content_level = sa.Enum(
    "full_text",
    "abstract",
    "metadata_only",
    "web_page",
    "user_document",
    name="content_level",
    native_enum=False,
    create_constraint=True,
)
new_content_level = sa.Enum(
    "full_text",
    "abstract",
    "metadata_only",
    "web_page",
    "user_document",
    "transcript",
    "visual_analysis",
    name="content_level",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.alter_column(
            "file_type",
            existing_type=old_file_type,
            type_=new_file_type,
            existing_nullable=False,
        )
        batch_op.alter_column(
            "source_type",
            existing_type=old_source_type,
            type_=new_source_type,
            existing_nullable=False,
            existing_server_default="uploaded_file",
            server_default="uploaded_file",
        )
        batch_op.alter_column(
            "content_level",
            existing_type=old_content_level,
            type_=new_content_level,
            existing_nullable=False,
            existing_server_default="user_document",
            server_default="user_document",
        )


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.alter_column(
            "content_level",
            existing_type=new_content_level,
            type_=old_content_level,
            existing_nullable=False,
            existing_server_default="user_document",
            server_default="user_document",
        )
        batch_op.alter_column(
            "source_type",
            existing_type=new_source_type,
            type_=old_source_type,
            existing_nullable=False,
            existing_server_default="uploaded_file",
            server_default="uploaded_file",
        )
        batch_op.alter_column(
            "file_type",
            existing_type=new_file_type,
            type_=old_file_type,
            existing_nullable=False,
        )
