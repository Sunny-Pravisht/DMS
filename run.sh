#!/usr/bin/env bash
# Start HARMAN DMS on Ubuntu.
#
# Tesseract and Poppler are installed in a user prefix (~/.local/opt/dms-tools)
# rather than system-wide, because installing them with apt needs root. The
# wrapper scripts there set their own LD_LIBRARY_PATH, so nothing extra is
# needed here - the paths are already recorded in .env and the settings table.
#
# If you later install them properly with
#     sudo apt-get install -y tesseract-ocr poppler-utils
# then point TESSERACT_PATH at /usr/bin/tesseract and POPPLER_PATH at /usr/bin
# in .env, update the same two rows in the settings table, and delete the prefix.
set -euo pipefail

cd "$(dirname "$0")"

HOST="${DOCUMENT_MANAGER_HOST:-127.0.0.1}"
PORT="${DOCUMENT_MANAGER_PORT:-8000}"

if [ ! -x .venv/bin/python ]; then
    echo "No virtual environment found. Create one with:" >&2
    echo "    uv venv --python 3.12 .venv && uv pip install -r requirements.txt" >&2
    exit 1
fi

echo "HARMAN DMS -> http://${HOST}:${PORT}"
exec .venv/bin/python -m uvicorn app.main:app --host "$HOST" --port "$PORT" "$@"
