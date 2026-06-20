"""Shared pytest fixtures.

Every test runs against an isolated, writable SQLite file in a temp directory,
so the suite never touches the real ``data/athena.db`` (which is owned by the
Docker container in deployment).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Point the global settings singleton at a writable temp store BEFORE `config`
# is imported anywhere, so the full-app HTTP test never touches the real
# (Docker-owned, read-only) data/athena.db.
_TMP = Path(tempfile.mkdtemp(prefix="athena_pytest_"))
os.environ.setdefault("ATHENA_SQLITE_PATH", str(_TMP / "app.db"))
os.environ.setdefault("ATHENA_CHROMA_DIR", str(_TMP / "chroma"))

import pytest
import pytest_asyncio

from db.sqlite_manager import SQLiteManager


@pytest_asyncio.fixture
async def db(tmp_path):
    """A freshly initialized SQLiteManager backed by a temp file."""
    manager = SQLiteManager(db_path=tmp_path / "test.db")
    await manager.initialize()
    try:
        yield manager
    finally:
        await manager.close()
