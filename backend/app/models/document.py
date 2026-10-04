from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from pgvector.sqlalchemy import Vector

from app.core.time import utc_now
from app.db.base import Base, TimestampMixin
from app.db.types import UTCDateTime
from app.domain.documents import ContentLevel, DocumentStatus, DocumentType, SourceType


def _enum_values(
    enum_class: type[ContentLevel]
    | type[DocumentStatus]
    | type[DocumentType]
    | type[SourceType],
) -> list[str]:
    return [member.value for member in enum_class]


document_type_enum = Enum(
    DocumentType,
    name="document_type",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    values_callable=_enum_values,
)

document_status_enum = Enum(
    DocumentStatus,
    name="document_status",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    values_callable=_enum_values,
)

source_type_enum = Enum(
    SourceType,
    name="source_type",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    values_callable=_enum_values,
)

content_level_enum = Enum(
    ContentLevel,
    name="content_level",
    native_enum=False,
    create_constraint=True,
    validate_strings=True,
    values_callable=_enum_values,
)

json_document_type = JSON().with_variant(JSONB(), "postgresql")


class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_user_project", "user_id", "project_id"),
        Index(
            "ix_documents_user_project_checksum",
            "user_id",
            "project_id",
            "checksum",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    file_type: Mapped[DocumentType] = mapped_column(
        document_type_enum,
        nullable=False,
        index=True,
    )
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        source_type_enum,
        default=SourceType.UPLOADED_FILE,
        server_default=SourceType.UPLOADED_FILE.value,
        nullable=False,
        index=True,
    )
    source_uri: Mapped[str | None] = mapped_column(String(2048))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    checksum: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[DocumentStatus] = mapped_column(
        document_status_enum,
        default=DocumentStatus.UPLOADED,
        server_default=DocumentStatus.UPLOADED.value,
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(1000))
    authors: Mapped[list[str] | None] = mapped_column(JSON)
    abstract: Mapped[str | None] = mapped_column(Text)
    doi: Mapped[str | None] = mapped_column(String(255), index=True)
    openalex_id: Mapped[str | None] = mapped_column(String(255), index=True)
    crossref_id: Mapped[str | None] = mapped_column(String(255), index=True)
    publication_year: Mapped[int | None] = mapped_column(Integer)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    content_level: Mapped[ContentLevel] = mapped_column(
        content_level_enum,
        default=ContentLevel.USER_DOCUMENT,
        server_default=ContentLevel.USER_DOCUMENT.value,
        nullable=False,
        index=True,
    )
    canonical_metadata: Mapped[dict[str, object] | None] = mapped_column(
        "metadata",
        json_document_type,
    )
    metadata_provenance: Mapped[dict[str, str] | None] = mapped_column(
        json_document_type
    )
    parser_name: Mapped[str | None] = mapped_column(String(100))
    parser_version: Mapped[str | None] = mapped_column(String(100))
    ingestion_version: Mapped[str | None] = mapped_column(String(100), index=True)
    page_count: Mapped[int | None] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, server_default=func.now(), nullable=False
    )
    processing_error: Mapped[str | None] = mapped_column(Text)

    project: Mapped["ResearchProject | None"] = relationship(
        back_populates="documents"
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DocumentChunk.chunk_index",
    )

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    @property
    def ingestion_status(self) -> DocumentStatus:
        """Expose the existing truthful lifecycle under canonical terminology."""

        return self.status


class DocumentChunk(TimestampMixin, Base):
    """Page-aware text ready for embedding during the next pipeline phase."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        CheckConstraint(
            "page IS NULL OR page >= 1",
            name="ck_document_chunks_page_positive",
        ),
        CheckConstraint(
            "page_end IS NULL OR page_end >= 1",
            name="ck_document_chunks_page_end_positive",
        ),
        CheckConstraint(
            "page IS NULL OR page_end IS NULL OR page_end >= page",
            name="ck_document_chunks_page_range",
        ),
        CheckConstraint(
            "chunk_index >= 0", name="ck_document_chunks_index_nonnegative"
        ),
        CheckConstraint(
            "token_count IS NULL OR token_count >= 0",
            name="ck_document_chunks_token_count_nonnegative",
        ),
        UniqueConstraint(
            "document_id", "chunk_index", name="uq_document_chunks_document_index"
        ),
        UniqueConstraint("node_id", name="uq_document_chunks_node_id"),
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index(
            "ix_document_chunks_search_vector_gin",
            "search_vector",
            postgresql_using="gin",
        ).ddl_if(dialect="postgresql"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(500))
    section_path: Mapped[list[str] | None] = mapped_column(JSON)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer)
    node_metadata: Mapped[dict[str, object] | None] = mapped_column(
        "metadata",
        json_document_type,
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR().with_variant(Text(), "sqlite"),
        nullable=True,
    )

    document: Mapped[Document] = relationship(back_populates="chunks")
