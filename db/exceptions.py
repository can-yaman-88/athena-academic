"""Shared exception hierarchy for the Jarvis-Academic data layer.

Defined in their own module so that both the SQLite and Chroma managers can
import them without creating a circular dependency between the two manager
modules.
"""

from __future__ import annotations


class JarvisDBError(Exception):
    """Base class for all data-layer errors."""


class DatabaseError(JarvisDBError):
    """Raised for SQLite connection, locking, or SQL execution failures."""


class RecordNotFoundError(JarvisDBError):
    """Raised when a read/update/delete targets an id that does not exist."""


class ChromaError(JarvisDBError):
    """Raised for vector-store (ChromaDB) initialisation or query failures."""


__all__ = [
    "ChromaError",
    "DatabaseError",
    "JarvisDBError",
    "RecordNotFoundError",
]
