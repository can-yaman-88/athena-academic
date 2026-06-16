"""Strict Pydantic v2 domain schemas for Athena-Academic.

These models are the single source of truth for the shape and validity of every
record that flows through the system. All validation (bounds, required fields,
derived values) is enforced here so that downstream layers — persistence,
retrieval, and the future agent graph — can assume any model instance they
receive is already valid.

IDs are client-generated UUID4 strings. Generating the identifier at
construction time (rather than relying on the database) lets the persistence
layer deduplicate and enqueue records idempotently before they are ever
written.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field


def _new_id() -> str:
    """Return a fresh UUID4 string used as a primary key."""
    return str(uuid4())


class TaskStatus(str, Enum):
    """Lifecycle states for a :class:`Task`.

    Subclassing ``str`` keeps the enum JSON-/SQLite-friendly: ``status.value``
    is a plain string, and equality with raw strings still works.
    """

    PENDING = "pending"
    COMPLETED = "completed"


class TaskCategory(str, Enum):
    """Top-level split of tasks."""

    ACADEMIC = "academic"
    DAILY = "daily"


class WorkoutStatus(str, Enum):
    """Lifecycle of a workout. Only ``completed`` contributes to cognitive load."""

    PLANNED = "planned"
    COMPLETED = "completed"


class AcademicSubtype(str, Enum):
    """Sub-types for academic tasks (daily tasks stay subtype-less)."""

    PROJECT = "project"
    ASSIGNMENT = "assignment"
    STUDY_SESSION = "study_session"


class _StrictModel(BaseModel):
    """Base model applying project-wide validation policy.

    - ``validate_assignment``: re-validate on attribute mutation so an object
      can never drift into an invalid state after construction.
    - ``extra="forbid"``: reject unknown fields instead of silently dropping
      them, surfacing typos and schema mismatches early.
    - ``use_enum_values=False``: keep rich enum members in memory; the
      persistence layer is responsible for serialising ``.value``.
    """

    model_config = ConfigDict(
        validate_assignment=True,
        extra="forbid",
        use_enum_values=False,
    )


class Note(_StrictModel):
    """An editable free-text note attached to a task."""

    id: str = Field(default_factory=_new_id, description="UUID4 primary key.")
    text: str = Field(min_length=1, description="Note body.")
    created_at: datetime = Field(default_factory=datetime.now)


class Material(_StrictModel):
    """A reference attached to a task: an uploaded file or an external link."""

    id: str = Field(default_factory=_new_id, description="UUID4 primary key.")
    kind: str = Field(default="file", description="'file' or 'link'.")
    name: str = Field(min_length=1, description="Display name.")
    source: str = Field(min_length=1, description="File path or URL.")
    markdown_path: Optional[str] = Field(
        default=None, description="Path to the extracted Markdown, if any."
    )


class Task(_StrictModel):
    """A task the system schedules and tracks to completion.

    Tasks are split into ``academic`` (long-running projects/assignments/study
    sessions, with AI-generated subtasks, progress, notes and materials) and
    ``daily`` (lightweight, subtype-less). Subtasks are independent ``Task`` rows
    that reference their parent via ``parent_id``.
    """

    id: str = Field(default_factory=_new_id, description="UUID4 primary key.")
    title: str = Field(min_length=1, description="Human-readable task title.")
    deadline: datetime = Field(description="When the task is due.")
    discipline: str = Field(
        min_length=1, description="Subject/field the task belongs to."
    )
    status: TaskStatus = Field(
        default=TaskStatus.PENDING, description="Current lifecycle state."
    )
    estimated_hours: float = Field(
        gt=0, description="Estimated effort in hours; must be positive."
    )
    category: TaskCategory = Field(
        default=TaskCategory.DAILY, description="academic | daily."
    )
    subtype: Optional[AcademicSubtype] = Field(
        default=None, description="Academic sub-type; null for daily tasks."
    )
    parent_id: Optional[str] = Field(
        default=None, description="Parent task id when this is a subtask."
    )
    progress: int = Field(
        default=0, ge=0, le=100, description="Completion percentage (academic)."
    )
    materials: list[Material] = Field(
        default_factory=list, description="Attached files/links."
    )
    notes: list[Note] = Field(
        default_factory=list, description="Editable notes attached to the task."
    )


class StudySession(_StrictModel):
    """A completed study session and how well its content was retained."""

    id: str = Field(default_factory=_new_id, description="UUID4 primary key.")
    topic: str = Field(min_length=1, description="What was studied.")
    duration_minutes: int = Field(
        gt=0, description="Session length in minutes; must be positive."
    )
    retention_score: float = Field(
        ge=0,
        le=100,
        description="Estimated retention of the material, from 0 to 100.",
    )


class PhysicalLoad(_StrictModel):
    """A physical training session and its derived training load.

    ``calculated_load`` is a computed, read-only value (duration x RPE) — it is
    never accepted as input but is included in serialisation so it can be
    persisted and queried.
    """

    id: str = Field(default_factory=_new_id, description="UUID4 primary key.")
    date: date_type = Field(description="Calendar date of the session.")
    duration_minutes: int = Field(
        gt=0, description="Session length in minutes; must be positive."
    )
    rpe_score: int = Field(
        ge=1,
        le=10,
        description="Rating of Perceived Exertion on the 1-10 Borg CR10 scale.",
    )
    status: WorkoutStatus = Field(
        default=WorkoutStatus.COMPLETED,
        description="planned | completed. Only completed sessions count toward load.",
    )
    title: Optional[str] = Field(
        default=None, description="Optional label, e.g. 'tempo run'."
    )
    # TrainingPeaks-style optional metrics — shown only when provided.
    distance_km: Optional[float] = Field(default=None, ge=0)
    pace: Optional[str] = Field(
        default=None, description="Pace per km, e.g. '5:30'."
    )
    avg_speed_kmh: Optional[float] = Field(default=None, ge=0)
    avg_hr: Optional[int] = Field(default=None, ge=0, le=260)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def calculated_load(self) -> float:
        """Session training load, defined as ``duration_minutes * rpe_score``."""
        return float(self.duration_minutes * self.rpe_score)


class LoadAdjustment(_StrictModel):
    """A day-scoped cognitive-load addition derived from note analysis.

    Summed into a given day's cognitive load alongside the workout-derived load;
    because the dashboard only counts adjustments dated today, these reset daily.
    """

    id: str = Field(default_factory=_new_id, description="UUID4 primary key.")
    date: date_type = Field(default_factory=date_type.today)
    amount: float = Field(description="Cognitive-load points to add (may be 0+).")
    reason: str = Field(default="", description="Why this load was added.")
    task_id: Optional[str] = Field(default=None, description="Source task, if any.")


class PdfJobStatus(str, Enum):
    """Lifecycle states for a :class:`PdfJob`."""

    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PdfJob(_StrictModel):
    """A record of one PDF processed by the in-process PDF->LaTeX engine."""

    id: str = Field(default_factory=_new_id, description="UUID4 primary key.")
    filename: str = Field(min_length=1, description="Original uploaded file name.")
    status: PdfJobStatus = Field(
        default=PdfJobStatus.PROCESSING, description="Current lifecycle state."
    )
    created_at: datetime = Field(
        default_factory=datetime.now, description="When the job was queued."
    )
    completed_at: Optional[datetime] = Field(
        default=None, description="When the job finished (success or failure)."
    )
    artifacts: list[str] = Field(
        default_factory=list,
        description="Paths of produced artifacts (notes/exam/flashcards).",
    )
    cost_usd: float = Field(
        default=0.0, ge=0, description="Estimated OpenRouter spend for this job."
    )
    chunks_ingested: int = Field(
        default=0, ge=0, description="Number of chunks ingested into ChromaDB."
    )
    error: Optional[str] = Field(default=None, description="Failure detail, if any.")
    summary: str = Field(default="", description="Human-readable outcome summary.")


__all__ = [
    "AcademicSubtype",
    "LoadAdjustment",
    "Material",
    "Note",
    "PdfJob",
    "PdfJobStatus",
    "PhysicalLoad",
    "StudySession",
    "Task",
    "TaskCategory",
    "TaskStatus",
    "WorkoutStatus",
]
