"""Shared exception hierarchy for the Athena-Academic data layer.

Defined in their own module so that both the SQLite and Chroma managers can
import them without creating a circular dependency between the two manager
modules.
"""

from __future__ import annotations


class AthenaDBError(Exception):
    """Base class for all data-layer errors."""


class DatabaseError(AthenaDBError):
    """Raised for SQLite connection, locking, or SQL execution failures."""


class RecordNotFoundError(AthenaDBError):
    """Raised when a read/update/delete targets an id that does not exist."""


class ChromaError(AthenaDBError):
    """Raised for vector-store (ChromaDB) initialisation or query failures."""


__all__ = [
    "ChromaError",
    "DatabaseError",
    "AthenaDBError",
    "RecordNotFoundError",
]
