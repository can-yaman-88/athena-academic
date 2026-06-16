"""Core domain layer for Athena-Academic.

Exposes the strict Pydantic schemas used throughout the system.
"""

from core.schemas import (
    PhysicalLoad,
    StudySession,
    Task,
    TaskStatus,
)

__all__ = [
    "PhysicalLoad",
    "StudySession",
    "Task",
    "TaskStatus",
]
