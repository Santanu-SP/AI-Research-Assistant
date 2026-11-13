#!/usr/bin/env python3
"""CLI utility to migrate and verify data from Supabase/SQLite to Neon PostgreSQL."""

from __future__ import annotations

import argparse
import json
import os
import sys

from sqlalchemy import URL

from app.core.config import Settings
from app.db.neon_migration import (
    generate_rollback_plan,
    migrate_database,
    verify_migration,
)
from app.db.session import create_db_engine


def _default_source_url(settings: Settings) -> str | None:
    explicit = os.environ.get("SOURCE_DATABASE_URL")
    if explicit:
        return explicit
    supa_vals = (
        settings.supabase_db_user,
        settings.supabase_db_password,
        settings.supabase_db_host,
        settings.supabase_db_port,
        settings.supabase_db_name,
    )
    if all(v is not None for v in supa_vals):
        return URL.create(
            "postgresql+psycopg",
            username=settings.supabase_db_user,
            password=settings.supabase_db_password,
            host=settings.supabase_db_host,
            port=settings.supabase_db_port,
            database=settings.supabase_db_name,
            query={"sslmode": "require"},
        ).render_as_string(hide_password=False)
    return None


def main(argv: list[str] | None = None) -> int:
    settings = Settings()
    parser = argparse.ArgumentParser(
        description="Migrate and verify database from Supabase to Neon PostgreSQL."
    )
    parser.add_argument(
        "--source-url",
        default=_default_source_url(settings),
        help="Source database URL (e.g. Supabase PostgreSQL URL).",
    )
    parser.add_argument(
        "--target-url",
        default=(
            os.environ.get("NEON_DIRECT_DATABASE_URL")
            or os.environ.get("DATABASE_URL_UNPOOLED")
            or os.environ.get("NEON_DATABASE_URL")
            or os.environ.get("DATABASE_URL")
            or settings.migration_database_url
        ),
        help="Target Neon PostgreSQL database URL.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute data copy (defaults to safe --dry-run if not passed).",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify row counts, IDs, vector dimensions, and similarity queries.",
    )
    parser.add_argument(
        "--allow-non-empty-target",
        action="store_true",
        help="Allow idempotent insertion into a non-empty target database.",
    )
    parser.add_argument(
        "--show-rollback",
        action="store_true",
        help="Print the rollback procedure and exit.",
    )
    args = parser.parse_args(argv)

    if args.show_rollback:
        print(generate_rollback_plan())
        return 0

    if not args.source_url or not args.target_url:
        print(
            "Error: Both --source-url and --target-url must be provided.",
            file=sys.stderr,
        )
        return 2

    source_engine = create_db_engine(args.source_url)
    target_engine = create_db_engine(args.target_url)
    try:
        if args.verify_only:
            report = verify_migration(source_engine, target_engine)
        else:
            report = migrate_database(
                source_engine,
                target_engine,
                dry_run=not args.execute,
                allow_non_empty_target=args.allow_non_empty_target,
            )
        summary = {
            "dry_run": report.dry_run,
            "ok": report.ok,
            "source_dialect": report.source_dialect,
            "target_dialect": report.target_dialect,
            "pgvector_enabled": report.pgvector_enabled,
            "fts_trigger_present": report.fts_trigger_present,
            "document_ids_verified": report.document_ids_verified,
            "chunk_ids_verified": report.chunk_ids_verified,
            "vector_dimensions_verified": report.vector_dimensions_verified,
            "similarity_query_verified": report.similarity_query_verified,
            "rows_copied": report.rows_copied,
            "tables": [
                {
                    "table": t.table_name,
                    "source_count": t.source_count,
                    "target_count": t.target_count,
                    "matches": t.matches,
                }
                for t in report.tables
            ],
            "warnings": report.warnings,
            "errors": report.errors,
        }
        print(json.dumps(summary, indent=2))
        return 0 if (report.ok or report.dry_run) else 1
    finally:
        source_engine.dispose()
        target_engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())

