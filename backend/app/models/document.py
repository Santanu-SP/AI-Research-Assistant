from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Enum, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.domain.documents import DocumentStatus, DocumentType


def _enum_values(enum_class: type[DocumentStatus] | type[DocumentType]) -> list[str]:
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


class Document(TimestampMixin, Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
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
    status: Mapped[DocumentStatus] = mapped_column(
        document_status_enum,
        default=DocumentStatus.READY,
        server_default=DocumentStatus.READY.value,
        nullable=False,
        index=True,
    )
