"""On-demand note analysis: mine task notes for progress with a strong model.

The user attaches free-text notes to tasks. When they ask to analyze them, all
notes are sent to a high-capacity model (Opus by default) which returns:

- **task_progress_updates** — when a note reports progress that belongs to a
  (possibly different) task, the new progress percentage for that task.

The model is constrained by :class:`NoteAnalysis` via ``with_structured_output``;
it may only reference task ids it was given. The LLM is injectable so the logic is
testable offline.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from config import settings

logger = logging.getLogger("athena.notes")


class TaskProgressUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(description="Existing task id this progress applies to.")
    progress: int = Field(ge=0, le=100, description="New completion percentage.")
    reason: str = Field(description="Short justification drawn from the note.")


class NoteAnalysis(BaseModel):
    """Structured output the analyzer model must produce."""

    model_config = ConfigDict(extra="forbid")

    task_progress_updates: list[TaskProgressUpdate] = Field(default_factory=list)


NOTE_ANALYSIS_SYSTEM_PROMPT = """\
You analyze a student's task notes and extract task progress. You are given a JSON
list of tasks, each with: id, title, category, subtype, progress, and notes.

Rules:
- PROGRESS: If a note reports concrete progress on a task or SUBTASK — possibly a
  DIFFERENT task than the one the note is attached to — emit a "task_progress_updates"
  entry with that task's id and the new overall progress percentage (0-100).
  If a note says a task or subtask is "done" or "completed", set its progress to 100.
  Only reference task ids present in the input.

Be conservative: if a note is purely descriptive with no progress signal, produce
nothing for it. Never invent task ids. Return only the structured fields.\
"""


def _default_llm(callbacks: Optional[list] = None) -> Any:
    from core.graph import _make_llm

    llm = _make_llm(
        settings.notes_model, settings.notes_model_max_tokens, callbacks=callbacks
    )
    return llm.with_structured_output(NoteAnalysis, method="function_calling")


async def analyze_notes(
    tasks_payload: list[dict],
    *,
    llm: Any = None,
    callbacks: Optional[list] = None,
) -> NoteAnalysis:
    """Run note analysis over a list of task dicts (id/title/notes/...)."""
    import json

    if llm is None:
        llm = _default_llm(callbacks)
    result: Optional[NoteAnalysis] = await llm.ainvoke(
        [
            SystemMessage(content=NOTE_ANALYSIS_SYSTEM_PROMPT),
            HumanMessage(content=json.dumps(tasks_payload, ensure_ascii=False)),
        ]
    )
    return result or NoteAnalysis()


__all__ = [
    "NoteAnalysis",
    "NOTE_ANALYSIS_SYSTEM_PROMPT",
    "TaskProgressUpdate",
    "analyze_notes",
    "_default_llm",
]
