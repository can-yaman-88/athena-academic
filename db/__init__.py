"""Persistence layer for Jarvis-Academic.

Bundles the async SQLite manager, the ChromaDB vector-store manager, and the
shared exception hierarchy.
"""

from db.chroma_manager import ChromaManager
from db.exceptions import (
    ChromaError,
    DatabaseError,
    JarvisDBError,
    RecordNotFoundError,
)
from db.sqlite_manager import SQLiteManager

__all__ = [
    "ChromaError",
    "ChromaManager",
    "DatabaseError",
    "JarvisDBError",
    "RecordNotFoundError",
    "SQLiteManager",
]
