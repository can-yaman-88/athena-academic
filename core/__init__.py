"""Core domain layer for Athena-Academic.

Exposes the strict Pydantic schemas used throughout the system.
"""

from core.schemas import (
    StudySession,
    Task,
    TaskStatus,
)

__all__ = [
    "StudySession",
    "Task",
    "TaskStatus",
]
