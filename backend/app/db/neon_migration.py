"""Repeatable, non-destructive migration and verification from Supabase to Neon PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any

from sqlalchemy import Engine, MetaData, func, inspect, select, text
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import create_db_engine
from app.models.document import Document, DocumentChunk
import app.models  # noqa: F401 - ensure all models are registered on Base.metadata

logger = logging.getLogger(__name__)

# Topological foreign-key order for safe copying.
ORDERED_TABLES: tuple[str, ...] = (
    "users",
    "auth_sessions",
    "oauth_states",
    "user_api_keys",
    "research_projects",
    "documents",
    "document_chunks",
    "research",
    "research_reports",
    "report_sections",
    "sources",
    "citations",
    "background_jobs",
    "telemetry_events",
)


@dataclass
class TableVerification:
    table_name: str
    source_count: int
    target_count: int
    matches: bool


@dataclass
class MigrationReport:
    dry_run: bool
    source_dialect: str
    target_dialect: str
    pgvector_enabled: bool
    fts_trigger_present: bool
    tables: list[TableVerification] = field(default_factory=list)
    rows_copied: dict[str, int] = field(default_factory=dict)
    document_ids_verified: bool = False
    chunk_ids_verified: bool = False
    vector_dimensions_verified: bool = False
    similarity_query_verified: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (
            not self.errors
            and all(item.matches for item in self.tables)
            and self.document_ids_verified
            and self.chunk_ids_verified
            and self.vector_dimensions_verified
        )


def ensure_neon_extensions_and_fts(target_engine: Engine) -> tuple[bool, bool]:
    """Enable pgvector and FTS trigger on PostgreSQL/Neon targets."""
    if target_engine.dialect.name != "postgresql":
        return False, False

    with target_engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(
            text(
                """
                CREATE OR REPLACE FUNCTION document_chunks_search_vector_update()
                RETURNS trigger AS $$
                BEGIN
                    NEW.search_vector := to_tsvector('english', coalesce(NEW.text, ''));
                    RETURN NEW;
                END
                $$ LANGUAGE plpgsql
                """
            )
        )
        has_trigger = conn.execute(
            text(
                "SELECT 1 FROM pg_trigger WHERE tgname = 'trg_document_chunks_search_vector'"
            )
        ).scalar()
        if not has_trigger:
            conn.execute(
                text(
                    """
                    CREATE TRIGGER trg_document_chunks_search_vector
                    BEFORE INSERT OR UPDATE OF text ON document_chunks
                    FOR EACH ROW EXECUTE FUNCTION document_chunks_search_vector_update()
                    """
                )
            )
        has_vector = bool(
            conn.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            ).scalar()
        )
        has_trigger_after = bool(
            conn.execute(
                text(
                    "SELECT 1 FROM pg_trigger WHERE tgname = 'trg_document_chunks_search_vector'"
                )
            ).scalar()
        )
    return has_vector, has_trigger_after


def _table_row_count(engine: Engine, table_name: str) -> int:
    inspector = inspect(engine)
    if not inspector.has_table(table_name):
        return 0
    table = Base.metadata.tables[table_name]
    pk_cols = list(table.primary_key.columns)
    count_expr = func.count(pk_cols[0]) if pk_cols else func.count()
    with engine.connect() as conn:
        return int(conn.execute(select(count_expr).select_from(table)).scalar() or 0)


def migrate_database(
    source_engine: Engine,
    target_engine: Engine,
    *,
    dry_run: bool = True,
    create_schema_if_missing: bool = True,
    allow_non_empty_target: bool = False,
    expected_vector_dim: int = 1024,
    batch_size: int = 250,
) -> MigrationReport:
    """Copy data from source (Supabase/SQLite) to target (Neon) and verify integrity."""
    report = MigrationReport(
        dry_run=dry_run,
        source_dialect=source_engine.dialect.name,
        target_dialect=target_engine.dialect.name,
        pgvector_enabled=False,
        fts_trigger_present=False,
    )

    source_inspector = inspect(source_engine)
    target_inspector = inspect(target_engine)

    if not dry_run and create_schema_if_missing:
        if target_engine.dialect.name == "postgresql":
            with target_engine.begin() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.create_all(target_engine)
        pgvector_ok, fts_ok = ensure_neon_extensions_and_fts(target_engine)
        report.pgvector_enabled = pgvector_ok
        report.fts_trigger_present = fts_ok
        target_inspector = inspect(target_engine)
    elif target_engine.dialect.name == "postgresql":
        with target_engine.connect() as conn:
            report.pgvector_enabled = bool(
                conn.execute(
                    text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                ).scalar()
            )
            report.fts_trigger_present = bool(
                conn.execute(
                    text(
                        "SELECT 1 FROM pg_trigger WHERE tgname = 'trg_document_chunks_search_vector'"
                    )
                ).scalar()
            )

    for table_name in ORDERED_TABLES:
        if table_name not in Base.metadata.tables:
            continue
        if not source_inspector.has_table(table_name):
            report.warnings.append(f"Source table '{table_name}' does not exist; skipping.")
            continue

        table = Base.metadata.tables[table_name]
        source_columns = {col["name"] for col in source_inspector.get_columns(table_name)}
        target_exists = target_inspector.has_table(table_name)
        target_columns = (
            {col["name"] for col in target_inspector.get_columns(table_name)}
            if target_exists
            else {col.name for col in table.columns}
        )
        shared_column_names = [
            col.name
            for col in table.columns
            if col.name in source_columns
            and col.name in target_columns
            and not (
                table_name == "document_chunks"
                and col.name == "search_vector"
                and target_engine.dialect.name == "postgresql"
            )
        ]
        selectable_cols = [table.c[name] for name in shared_column_names]
        with source_engine.connect() as s_conn:
            source_rows = [dict(row._mapping) for row in s_conn.execute(select(*selectable_cols))]

        existing_target_count = _table_row_count(target_engine, table_name) if target_exists else 0

        if dry_run:
            report.rows_copied[table_name] = 0
            report.tables.append(
                TableVerification(
                    table_name=table_name,
                    source_count=len(source_rows),
                    target_count=existing_target_count,
                    matches=len(source_rows) == existing_target_count,
                )
            )
            continue

        if existing_target_count > 0 and not allow_non_empty_target:
            report.errors.append(
                f"Target table '{table_name}' already contains {existing_target_count} rows. "
                "Pass allow_non_empty_target=True to merge idempotently."
            )
            return report

        pk_columns = [col.name for col in table.primary_key.columns]
        copied = 0
        if source_rows:
            with target_engine.begin() as t_conn:
                existing_pks: set[tuple[Any, ...]] = set()
                if existing_target_count > 0 and pk_columns:
                    pk_select = select(*[table.c[col] for col in pk_columns])
                    existing_pks = {tuple(r) for r in t_conn.execute(pk_select).fetchall()}

                to_insert = [
                    row
                    for row in source_rows
                    if not existing_pks or tuple(row[col] for col in pk_columns) not in existing_pks
                ]
                for idx in range(0, len(to_insert), batch_size):
                    batch = to_insert[idx : idx + batch_size]
                    t_conn.execute(table.insert(), batch)
                    copied += len(batch)

        report.rows_copied[table_name] = copied
        final_target_count = _table_row_count(target_engine, table_name)
        report.tables.append(
            TableVerification(
                table_name=table_name,
                source_count=len(source_rows),
                target_count=final_target_count,
                matches=len(source_rows) == final_target_count,
            )
        )

    verify_migration(
        source_engine,
        target_engine,
        report=report,
        expected_vector_dim=expected_vector_dim,
    )
    return report


def verify_migration(
    source_engine: Engine,
    target_engine: Engine,
    *,
    report: MigrationReport | None = None,
    expected_vector_dim: int = 1024,
) -> MigrationReport:
    """Verify row counts, document/chunk IDs, vector dimensions, and similarity search."""
    active_report = report or MigrationReport(
        dry_run=True,
        source_dialect=source_engine.dialect.name,
        target_dialect=target_engine.dialect.name,
        pgvector_enabled=False,
        fts_trigger_present=False,
    )
    if not active_report.tables:
        for table_name in ORDERED_TABLES:
            if table_name not in Base.metadata.tables:
                continue
            sc = _table_row_count(source_engine, table_name)
            tc = _table_row_count(target_engine, table_name)
            active_report.tables.append(
                TableVerification(
                    table_name=table_name,
                    source_count=sc,
                    target_count=tc,
                    matches=sc == tc,
                )
            )

    source_inspector = inspect(source_engine)
    target_inspector = inspect(target_engine)
    if not source_inspector.has_table("documents") or not target_inspector.has_table("documents"):
        return active_report

    doc_table = Base.metadata.tables["documents"]
    chunk_table = Base.metadata.tables["document_chunks"]
    with Session(source_engine) as s_session, Session(target_engine) as t_session:
        doc_cols = (
            doc_table.c.id,
            doc_table.c.checksum,
            doc_table.c.stored_name,
            doc_table.c.user_id,
        )
        source_docs = {
            row.id: (row.checksum, row.stored_name, row.user_id)
            for row in s_session.execute(select(*doc_cols)).all()
        }
        target_docs = {
            row.id: (row.checksum, row.stored_name, row.user_id)
            for row in t_session.execute(select(*doc_cols)).all()
        }
        active_report.document_ids_verified = source_docs == target_docs
        if not active_report.document_ids_verified and not active_report.dry_run:
            active_report.errors.append("Document IDs or metadata do not match between source and target.")

        chunk_cols = (
            chunk_table.c.id,
            chunk_table.c.document_id,
            chunk_table.c.node_id,
            chunk_table.c.chunk_index,
        )
        source_chunks = {
            row.id: (row.document_id, row.node_id, row.chunk_index)
            for row in s_session.execute(select(*chunk_cols)).all()
        }
        target_chunk_rows = list(
            t_session.execute(select(*chunk_cols, chunk_table.c.embedding)).all()
        )
        target_chunks = {
            row.id: (row.document_id, row.node_id, row.chunk_index)
            for row in target_chunk_rows
        }
        active_report.chunk_ids_verified = source_chunks == target_chunks
        if not active_report.chunk_ids_verified and not active_report.dry_run:
            active_report.errors.append("DocumentChunk IDs or ordering do not match between source and target.")

        dim_ok = True
        sample_vector: list[float] | None = None
        for row in target_chunk_rows:
            if row.embedding is not None:
                vec = list(row.embedding)
                if len(vec) != expected_vector_dim:
                    dim_ok = False
                    active_report.errors.append(
                        f"Chunk {row.id} has embedding dimension {len(vec)} != {expected_vector_dim}"
                    )
                    break
                if sample_vector is None:
                    sample_vector = vec
        active_report.vector_dimensions_verified = dim_ok

        if target_engine.dialect.name == "postgresql":
            probe = sample_vector or ([0.01] * expected_vector_dim)
            try:
                distance = DocumentChunk.embedding.cosine_distance(probe)
                t_session.execute(
                    select(DocumentChunk.id, distance).limit(1)
                ).all()
                active_report.similarity_query_verified = True
            except Exception as exc:
                active_report.similarity_query_verified = False
                active_report.errors.append(f"pgvector similarity query failed: {exc}")
        else:
            active_report.similarity_query_verified = True

    return active_report


def generate_rollback_plan() -> str:
    """Return step-by-step non-destructive rollback instructions to Supabase."""
    return (
        "ROLLBACK PROCEDURE (Neon -> Supabase):\n"
        "1. Supabase database is never modified or deleted during migration.\n"
        "2. To revert traffic immediately, unset NEON_DATABASE_URL / NEON_DIRECT_DATABASE_URL "
        "in .env (or restore DATABASE_URL to your Supabase connection string).\n"
        "3. Restart the FastAPI API and background worker processes.\n"
        "4. Verify readiness via GET /api/v1/health/ready."
    )

