"""Persistence layer for Athena-Academic.

Bundles the async SQLite manager, the ChromaDB vector-store manager, and the
shared exception hierarchy.
"""

from db.chroma_manager import ChromaManager
from db.exceptions import (
    ChromaError,
    DatabaseError,
    AthenaDBError,
    RecordNotFoundError,
)
from db.sqlite_manager import SQLiteManager

__all__ = [
    "ChromaError",
    "ChromaManager",
    "DatabaseError",
    "AthenaDBError",
    "RecordNotFoundError",
    "SQLiteManager",
]
