"""Prompt templates and the structured routing schema for Jarvis-Academic.

The router's decision is constrained by :class:`RouteDecision`, a strict Pydantic
model bound to the LLM with ``.with_structured_output(...)``. Because the model
must return one of a fixed set of ``next_node`` values, the router can never emit
an out-of-band or malformed destination — eliminating an entire class of routing
failures.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from core.state import CognitiveLoadStatus, RouteTarget


class RouteDecision(BaseModel):
    """Structured output the router LLM must produce for every turn.

    ``extra="forbid"`` rejects any field the model hallucinates, and the
    ``Literal`` type on :data:`~core.state.RouteTarget` guarantees ``next_node``
    is always a real graph node.
    """

    model_config = ConfigDict(extra="forbid")

    next_node: RouteTarget = Field(
        description=(
            "Which node should handle this message next. Exactly one of "
            "'chat_node', 'pdf_tool_node', or 'task_tool_node'."
        )
    )
    cognitive_load_status: CognitiveLoadStatus = Field(
        default="normal",
        description=(
            "Your estimate of the user's current cognitive load based on their "
            "message: 'low', 'normal', 'high', or 'overloaded'."
        ),
    )
    reasoning: str = Field(
        description="One short sentence explaining why this route was chosen."
    )


class TaskExtraction(BaseModel):
    """Structured task fields the extractor LLM pulls from a free-form request.

    Bound to the extraction LLM with ``.with_structured_output(...)`` so the
    model returns clean, typed fields that map directly onto
    :class:`core.schemas.Task`. ``deadline`` is an optional ISO string here (the
    node resolves it to a real ``datetime``), keeping the LLM contract simple.
    """

    model_config = ConfigDict(extra="forbid")

    operation: Literal["create", "update"] = Field(
        default="create",
        description=(
            "'create' for a new task; 'update' when the user wants to change an "
            "EXISTING task (e.g. 'move my run to 6pm', 'mark X done', 'düzenle')."
        ),
    )
    target_hint: Optional[str] = Field(
        default=None,
        description=(
            "For 'update' only: a short phrase identifying which existing task to "
            "change (e.g. 'jog', 'thermo project'). Null if unclear."
        ),
    )
    title: str = Field(
        description="A concise, human-readable title for the task."
    )
    deadline: Optional[str] = Field(
        default=None,
        description=(
            "The task's due date/time as an ISO 8601 string "
            "(e.g. '2026-07-01T09:00'). Resolve relative dates such as 'today' "
            "or 'tomorrow' against the current date provided in the system "
            "prompt. Use null if the user gives no deadline."
        ),
    )
    discipline: Optional[str] = Field(
        default=None,
        description=(
            "Subject or field (e.g. 'Math', 'Fitness'). Null if the user did not "
            "indicate one (the caller fills a default on create)."
        ),
    )
    estimated_hours: Optional[float] = Field(
        default=None,
        gt=0,
        description=(
            "Estimated effort in hours. Null if unstated (caller fills a default on "
            "create; on update only set it when the user changes it)."
        ),
    )
    category: Optional[Literal["academic", "daily"]] = Field(
        default=None,
        description=(
            "'academic' for projects/assignments/study-sessions and anything tied "
            "to coursework; 'daily' for everyday/general to-dos. Null = let the "
            "caller decide (defaults to daily)."
        ),
    )
    subtype: Optional[Literal["project", "assignment", "study_session"]] = Field(
        default=None,
        description="Academic sub-type when category is 'academic'; else null.",
    )


class TaskExtractionList(BaseModel):
    """A batch of tasks extracted from one request.

    A single user message can describe several tasks ("add A and B"), so the
    extractor returns a list. Bound to the LLM with ``.with_structured_output``;
    an empty list means no actionable task was found.
    """

    model_config = ConfigDict(extra="forbid")

    tasks: list[TaskExtraction] = Field(
        default_factory=list,
        description="One entry per distinct task described in the request.",
    )


TASK_EXTRACTION_SYSTEM_PROMPT = """\
You convert a user's free-form request into one or more structured tasks for an
academic planner. The current date and time is {now}.

CORE PRINCIPLE — FILL THE GAPS, NEVER REFUSE:
The user will usually be terse and leave details out. That is expected and fine.
Your job is to produce complete, usable tasks anyway by applying sensible
defaults. NEVER return an error, ask a clarifying question, or leave a required
field blank because information is missing. The ONLY time "tasks" is empty is
when the message contains nothing that could be interpreted as a task at all.

DEFAULTS (use these whenever the user did not state the value; OVERRIDE them with
the user's value whenever they did):
- title: infer a short, specific title from the request — never copy the whole
  sentence verbatim, and never leave it blank.
- deadline: resolve relative expressions ("today", "tonight", "tomorrow", "this
  weekend", "next Monday", "in 2 hours") against the current date/time above and
  return an ISO 8601 string. Map vague day-parts to times: "morning"->09:00,
  "afternoon"->14:00, "evening"/"tonight"->19:00, "end of day"->{default_deadline_time}.
  If NO time-frame is given at all, use today at {default_deadline_time}.
- discipline: the subject/field (e.g. "Math", "Physics", "Fitness", "Writing").
  If you cannot tell, use "{default_discipline}".
- estimated_hours: parse durations like "1 saat"/"1 hour"/"30 dk"/"half an hour".
  If unstated, use {default_estimated_hours}.

CREATE vs UPDATE:
- Default operation is "create". Use "update" when the user clearly wants to change
  an EXISTING task (e.g. "move my run to 6pm", "mark the essay done", "make it 2h",
  or an explicit edit request). For "update", set "target_hint" to a short phrase
  identifying the task; only fill the fields that change.

CATEGORY & SUBTYPE:
- Set category to "academic" for coursework — long projects, assignments, exam prep,
  or self-assigned study sessions — and choose a subtype (project / assignment /
  study_session). Set category to "daily" for everyday/general to-dos (leave subtype
  null). If genuinely unsure, leave category null.

MULTIPLE TASKS:
A single message may describe several tasks (e.g. "add A and also B"). Return one
entry in "tasks" for EACH distinct task, each independently completed with the
rules above.

Respond ONLY with the structured fields required by the schema.\
"""


class WorkoutPlanItem(BaseModel):
    """One training session within a (possibly multi-day) plan."""

    model_config = ConfigDict(extra="forbid")

    date: Optional[str] = Field(
        default=None,
        description=(
            "ISO date (YYYY-MM-DD). Resolve relative days against the current date "
            "in the system prompt. Null → today."
        ),
    )
    duration_minutes: int = Field(gt=0, description="Session length in minutes.")
    rpe_score: int = Field(
        ge=1, le=10, description="Perceived exertion 1-10; estimate from intensity."
    )
    note: Optional[str] = Field(default=None, description="Optional label (e.g. 'tempo run').")


class WorkoutPlan(BaseModel):
    """A batch of training sessions parsed from text or an attached plan file."""

    model_config = ConfigDict(extra="forbid")

    workouts: list[WorkoutPlanItem] = Field(default_factory=list)


WORKOUT_PLAN_SYSTEM_PROMPT = """\
You convert a user's training description or attached training plan into structured
workout sessions. The current date is {now}.

- Produce one entry in "workouts" per session. For multi-day plans (e.g. a month of
  training in Markdown/JSON), expand EVERY dated session into its own entry.
- Resolve relative days ("today", "Mon", "week 1 day 3") to ISO dates against the
  current date; if a session has no date, use today.
- duration_minutes: parse the stated duration. rpe_score: estimate 1-10 from the
  intensity language ("easy"≈3, "tempo"≈7, "hard intervals"≈9); default 5 if unclear.
- Never refuse or error on missing detail — fill sensible values. If there is no
  training content at all, return an empty list.

Return ONLY the structured fields.\
"""


ROUTER_SYSTEM_PROMPT = """\
You are the router for Jarvis-Academic, an autonomous academic assistant. Read the
user's most recent message and route it to exactly ONE handler. When a message
could fit more than one, prefer the most specific actionable handler
(pdf_tool_node or task_tool_node) over chat_node.

Choose exactly one next_node:
- pdf_tool_node: the user wants to process, parse, OCR, ingest, convert, summarize,
  or turn a PDF / document / lecture notes / scan into notes, an exam, or
  flashcards. Cues: "process this PDF", "convert my notes", "make flashcards",
  mentions of an uploaded file.
- task_tool_node: the user wants to add, create, schedule, EDIT, or track a task,
  assignment, project, deadline, study block, or to-do. Cues: imperative verbs like
  "add", "schedule", "create", "edit", "ekle", "düzenle".
- workout_tool_node: the user wants to log a workout/training session, or import a
  (possibly multi-day) training plan. Cues: "run", "training", "RPE", "antrenman",
  "plan", durations + intensities.
- chat_node: everything else — questions, explanations, tutoring, brainstorming,
  status checks, or general conversation, AND any request to retrieve/ask ABOUT
  already-ingested material (rather than process a new file).

Also estimate the user's cognitive load (low / normal / high / overloaded) from the
tone, urgency, and density of the message.

Return ONLY the structured fields; pick exactly one valid next_node.\
"""


CHAT_SYSTEM_PROMPT = """\
You are Jarvis-Academic, a focused, rigorous, and supportive academic assistant.
Your goals, in order: (1) be correct, (2) help the user genuinely learn and stay
organized, (3) be concise. Prefer clear structure (short paragraphs, lists, and
LaTeX-style math when helpful). When a question is ambiguous, state the most
reasonable interpretation and answer it rather than stalling on clarification.

Ground your answer in the retrieved context below WHEN it is relevant — cite the
ideas naturally and build on them. If the context is irrelevant or empty, rely on
your own knowledge and do not force the context in or mention that it was empty.
If you are uncertain or the material does not support a claim, say so plainly
instead of inventing specifics.

Retrieved context:
{context}\
"""


__all__ = [
    "CHAT_SYSTEM_PROMPT",
    "ROUTER_SYSTEM_PROMPT",
    "TASK_EXTRACTION_SYSTEM_PROMPT",
    "WORKOUT_PLAN_SYSTEM_PROMPT",
    "RouteDecision",
    "TaskExtraction",
    "TaskExtractionList",
    "WorkoutPlan",
    "WorkoutPlanItem",
]
