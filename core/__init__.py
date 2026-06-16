"""Core domain layer for Jarvis-Academic.

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
