"""Schema + prompt for AI-generated subtasks of an academic task.

When an academic task (especially a project, possibly with an attached spec) is
created, the graph asks a strong model to break it into a handful of concrete,
independently-trackable subtasks. Each becomes its own ``Task`` row (``parent_id``
set), so they appear in the task list and can be completed on their own.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SubtaskItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, description="Concise, actionable subtask title.")
    estimated_hours: Optional[float] = Field(
        default=None, gt=0, description="Effort in hours; null → caller default."
    )
    deadline: Optional[str] = Field(
        default=None,
        description="ISO 8601 due date/time; resolve relative dates against 'now'. "
        "Should fall on/before the parent's deadline. Null → parent deadline.",
    )


class SubtaskPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtasks: list[SubtaskItem] = Field(default_factory=list)


SUBTASK_SYSTEM_PROMPT = """\
[Context]
Athena creates actionable project plans. The user has created an academic or daily project/task and expects it to be broken down into manageable subtasks. The current date and time is {now}.

[Role]
You are a highly logical project manager and decomposition engine. Your sole purpose is to break a parent task into a concrete, sequenced set of actionable subtasks.

[Intent/Instruction]
Break the parent task into subtasks that together complete it. Assign logical deadlines, estimate hours, and structure the data strictly according to the schema.

[Strictness/Style]
{limit_text}
- Use any attached material or spec to ground the breakdown in the real requirements.
- Spread deadlines sensibly between now and the parent's deadline (never after it). If no parent deadline is provided, schedule them logically.
- Estimate hours per subtask when you can; otherwise, leave it null.
- If there is too little information, return a minimal sensible breakdown rather than refusing.
- Do NOT generate extra chatter. Return ONLY the structured fields.

[Parameters/Output Format]
- title: Concise, actionable subtask title.
- estimated_hours: float or null.
- deadline: ISO 8601 string or null.

[Examples]
N/A
"""


__all__ = ["SUBTASK_SYSTEM_PROMPT", "SubtaskItem", "SubtaskPlan"]
