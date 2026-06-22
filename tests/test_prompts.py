"""Guard the deepened prompts: every template must still `.format(...)` cleanly.

A stray single brace or a renamed placeholder would raise at runtime inside a
graph node; this catches it at test time instead.
"""

from __future__ import annotations

from datetime import datetime

from config import settings
from core.journal_analyzer import JOURNAL_ANALYSIS_SYSTEM_PROMPT
from core.note_analyzer import NOTE_ANALYSIS_SYSTEM_PROMPT
from core.prompt_templates import (
    CHAT_SYSTEM_PROMPT,
    IDEA_EXTRACTION_SYSTEM_PROMPT,
    RESEARCH_PLAN_PROMPT,
    SESSION_EXTRACTION_SYSTEM_PROMPT,
    TASK_EXTRACTION_SYSTEM_PROMPT,
)
from core.spaced_repetition import ACADEMIC_MEMORY_EVALUATOR_PROMPT
from core.subtasks import SUBTASK_SYSTEM_PROMPT

_NOW = datetime(2026, 6, 20, 12, 0).isoformat(timespec="minutes")


def test_task_prompt_formats_and_enforces_null_deadline():
    out = TASK_EXTRACTION_SYSTEM_PROMPT.format(
        now=_NOW,
        default_discipline=settings.default_discipline,
        default_estimated_hours=settings.default_estimated_hours,
    )
    assert _NOW in out
    # The null-by-default deadline rule must be present.
    assert "null" in out and "deadline" in out.lower()


def test_subtask_prompt_formats():
    out = SUBTASK_SYSTEM_PROMPT.format(now=_NOW, limit_text="- Produce 3-8 subtasks.")
    assert "null when the parent has no deadline" in out


def test_other_prompts_format():
    assert RESEARCH_PLAN_PROMPT.format(now=_NOW, question="quantum computing")
    assert SESSION_EXTRACTION_SYSTEM_PROMPT.format(now=_NOW)
    assert IDEA_EXTRACTION_SYSTEM_PROMPT.format(n_val=3)
    # The chat prompt has context/memory slots that the chat node fills.
    assert CHAT_SYSTEM_PROMPT.format(context="ctx", memory="mem")
    assert NOTE_ANALYSIS_SYSTEM_PROMPT.format()
    assert JOURNAL_ANALYSIS_SYSTEM_PROMPT.format()
    assert ACADEMIC_MEMORY_EVALUATOR_PROMPT.format()
