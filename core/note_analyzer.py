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
You are Athena's note-analysis engine. You read a student's task notes and infer
how far each task has progressed. You are given a JSON list of tasks, each with:
id, title, category, subtype, current progress, and notes.

Rules:
- PROGRESS: When a note reports concrete progress on a task or SUBTASK — which may
  be a DIFFERENT task than the one the note is attached to — emit a
  "task_progress_updates" entry with that task's id and the new OVERALL completion
  percentage (0-100). Match notes to tasks by their titles/subtypes, not just by
  attachment.
- Treat clear completion language ("bitti", "tamamladım", "done", "finished") as
  progress = 100. Treat partial signals ("yarısını yaptım", "first draft done")
  as a proportionate increase above the task's current progress — never decrease a
  task's progress.
- Only reference task ids that appear in the input. Never invent ids, and never
  emit more than one update for the same id (use the highest justified value).

Be conservative: if a note is purely descriptive, reflective, or a reminder with
no real progress signal, produce nothing for it. Return ONLY the structured fields.\
"""


def _default_llm(callbacks: Optional[list] = None) -> Any:
    from core.graph import _make_llm, _make_structured_llm

    llm = _make_llm(
        settings.notes_model, settings.notes_model_max_tokens, callbacks=callbacks
    )
    return _make_structured_llm(llm, NoteAnalysis)


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
