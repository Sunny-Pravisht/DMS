"""
Additive schema migrations for databases that already hold documents.

`Base.metadata.create_all` happily creates new *tables*, but it will never add
a *column* to a table that already exists. A deployment that has been running
since before the Studio shipped would therefore start and then fail on the
first query touching `documents.origin`.

Everything here is additive and idempotent: add a column if it is missing, do
nothing otherwise. No column is ever dropped or retyped, so running an older
build against a migrated database still works.
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# table -> {column: SQL type and default}
ADDITIONS: dict[str, dict[str, str]] = {
    "documents": {
        "origin": "VARCHAR DEFAULT 'uploaded'",
        "template_id": "VARCHAR",
        "source_html": "TEXT",
        "version": "VARCHAR DEFAULT '1.0'",
        "revision_of": "VARCHAR",
        "created_by": "VARCHAR",
        "folder_id": "VARCHAR",
    },
    "signatures": {
        "designation": "VARCHAR",
        # Placement as a fraction of the page. NULL means "let the automatic
        # layout decide", which is what every existing signature wants.
        "page_number": "INTEGER",
        "x_pct": "FLOAT",
        "y_pct": "FLOAT",
        "width_pct": "FLOAT",
        "placed_by": "VARCHAR",
        "placed_at": "DATETIME",
    },
    "users": {
        "department": "VARCHAR",
        "job_title": "VARCHAR",
        "account_type": "VARCHAR DEFAULT 'employee'",
        # Existing users keep the ability to approve and, deliberately, do NOT
        # gain the ability to sign. Signature authority is granted, never
        # inherited by a migration.
        "can_approve": "BOOLEAN DEFAULT 1",
        "can_sign": "BOOLEAN DEFAULT 0",
    },
    "approval_steps": {
        # A step now says whether one of its named people decides for it or
        # whether all of them must. Existing steps - including approvals part
        # way through - default to "any", which is how they behaved when the
        # people on them were asked to approve. A migration must never change
        # what somebody already agreed to.
        "approval_mode": "VARCHAR DEFAULT 'any'",
    },
}


def apply_migrations(engine: Engine) -> list[str]:
    """Add any missing columns and remove stale unique constraints that block My Folder uploads."""
    applied: list[str] = []
    inspector = inspect(engine)

    try:
        existing_tables = set(inspector.get_table_names())
    except Exception as exc:
        logger.warning(f"Could not inspect the database, skipping migrations: {exc}")
        return applied

    for table, columns in ADDITIONS.items():
        if table not in existing_tables:
            continue  # create_all will build it complete

        have = {c["name"] for c in inspector.get_columns(table)}

        for column, ddl in columns.items():
            if column in have:
                continue
            statement = f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"
            try:
                with engine.begin() as conn:
                    conn.execute(text(statement))
                applied.append(f"{table}.{column}")
                logger.info(f"Schema migration: added {table}.{column}")
            except Exception as exc:
                # A parallel worker may have won the race. Anything else is
                # worth seeing in the log but is not worth refusing to start.
                logger.warning(f"Schema migration skipped for {table}.{column}: {exc}")

    if "documents" in existing_tables:
        try:
            indexes = inspector.get_indexes("documents")
            for index in indexes:
                columns = index.get("column_names") or []
                name = index.get("name")
                if columns == ["file_hash"] and index.get("unique"):
                    with engine.begin() as conn:
                        conn.execute(text(f"DROP INDEX IF EXISTS {name}"))
                    applied.append(f"documents.file_hash_unique_index_removed")
                    logger.info(f"Schema migration: dropped unique index {name} on documents.file_hash")
        except Exception as exc:
            logger.warning(f"Could not reconcile file_hash index on documents: {exc}")

    return applied
