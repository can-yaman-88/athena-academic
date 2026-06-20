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
        "Must fall on/before the parent's deadline. Null when the parent has no "
        "deadline (the caller inherits the parent's, which may also be null).",
    )


class SubtaskPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtasks: list[SubtaskItem] = Field(default_factory=list)


SUBTASK_SYSTEM_PROMPT = """\
[Context]
Athena creates actionable project plans. The user has created an academic or daily project/task and, by using a planning command (/plan, /altgorev, /altakademik, /aralik), has ALREADY asked for it to be decomposed into manageable subtasks. The current date and time is {now}.

This decomposition is the whole point of the command — the user never has to say "break this down" or "make a plan". Always produce a breakdown.

[Role]
You are a highly logical project manager and decomposition engine. You turn a parent task into a concrete, sequenced set of independently-completable subtasks.

[Intent/Instruction]
Break the parent task into subtasks that together fully complete it. Sequence them logically, estimate effort, and emit strictly the schema fields.

[Strictness/Style]
{limit_text}
- ALWAYS return at least 2 subtasks for any parent — never an empty list, never prose. Given only a vague goal, infer a sensible standard breakdown for that kind of work.
- Use any attached material or spec to ground the breakdown in the real requirements.
- Deadlines: ONLY assign subtask deadlines when the parent HAS a deadline — then spread them sensibly between now and the parent's deadline (never after it). If the parent has NO deadline, leave every subtask 'deadline' null. Never fabricate or guess dates.
- Estimate 'estimated_hours' per subtask when the scope makes it reasonable; otherwise leave it null.
- If there is too little information, return a minimal sensible breakdown rather than refusing.
- Do NOT add chatter. Return ONLY the structured fields, in the user's language (usually Turkish).

[Parameters/Output Format]
- title: Concise, actionable subtask title.
- estimated_hours: float or null.
- deadline: ISO 8601 string, or null (always null when the parent has no deadline).

[Examples]
N/A
"""


__all__ = ["SUBTASK_SYSTEM_PROMPT", "SubtaskItem", "SubtaskPlan"]
