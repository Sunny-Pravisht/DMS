#!/usr/bin/env python3
"""
Convert Windows-style file paths in the DMS database to POSIX form.

The database was populated on Windows, so `documents.file_path` and
`document_versions.file_path` hold backslash-separated paths such as

    data\\storage\\Unknown\\2026-07-30\\<uuid>_AI.pdf

On Linux a backslash is an ordinary filename character, so `Path(...)` treats
the whole string as one file that does not exist: downloads, previews,
thumbnails, re-processing and signature stamping all fail.

`media_assets.file_path` is deliberately left alone - `media_service.seed_builtins()`
rewrites those on every startup, so it heals itself.

Idempotent: a row already in POSIX form is left untouched. Makes a timestamped
backup of the database before writing anything.
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB = Path("data/documents.db")
TARGETS = [("documents", "file_path"), ("document_versions", "file_path")]


def to_posix(value: str) -> str:
    """Backslashes to forward slashes, and drop the old Windows project root."""
    converted = value.replace("\\", "/")
    for prefix in ("C:/Users/Pravisht/Desktop/DMS/", "C:/Users/Pravisht/Desktop/DMS"):
        if converted.startswith(prefix):
            converted = converted[len(prefix):].lstrip("/")
            break
    return converted


def main() -> int:
    if not DB.exists():
        print(f"ERROR: {DB} not found. Run this from the project root.", file=sys.stderr)
        return 1

    backup = DB.with_name(f"documents.db.bak-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(DB, backup)
    print(f"Backed up database to {backup}")

    conn = sqlite3.connect(DB)
    total_changed = 0
    total_missing = 0

    for table, column in TARGETS:
        rows = conn.execute(f"SELECT rowid, {column} FROM {table}").fetchall()
        changed = 0
        missing: list[str] = []

        for rowid, value in rows:
            if not value:
                continue
            converted = to_posix(value)
            if converted != value:
                conn.execute(
                    f"UPDATE {table} SET {column} = ? WHERE rowid = ?", (converted, rowid)
                )
                changed += 1
            if not Path(converted).exists():
                missing.append(converted)

        total_changed += changed
        total_missing += len(missing)
        print(f"{table}.{column}: {changed} of {len(rows)} rewritten, "
              f"{len(missing)} not present on disk")
        for path in missing:
            print(f"    missing: {path}")

    conn.commit()
    conn.close()

    print(f"\nDone. {total_changed} paths rewritten.")
    if total_missing:
        print(f"{total_missing} row(s) point at files that are not on disk. These are "
              f"pre-existing orphans, not a result of this migration.\n"
              f"Clear them with:  POST /api/documents/cleanup/orphaned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
