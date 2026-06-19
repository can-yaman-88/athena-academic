"""Prompt templates and the structured routing schema for Athena-Academic.

The router's decision is constrained by :class:`RouteDecision`, a strict Pydantic
model bound to the LLM with ``.with_structured_output(...)``. Because the model
must return one of a fixed set of ``next_node`` values, the router can never emit
an out-of-band or malformed destination — eliminating an entire class of routing
failures.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from core.state import RouteTarget


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
    parent_hint: Optional[str] = Field(
        default=None,
        description=(
            "For 'create' only: if the user explicitly wants this task to be a "
            "subtask of another, a short phrase identifying the parent task. "
            "Null otherwise."
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
    tags: list[str] = Field(
        default_factory=list,
        description=(
            "List of tags associated with the task (e.g. ['İş', 'Okuma']). "
            "Extract these if the user mentions them using a '#' symbol or explicitly."
        )
    )
    notes: Optional[str] = Field(
        default="",
        description="Any additional comments, details, or instructions provided by the user that don't fit into the title."
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
[Context]
Athena is an advanced, strictly organized assistant that manages daily chores, academic tasks, and study sessions. Users input free-form natural language requests that often lack strict formatting or explicit dates. The current date and time is {now}.

[Role]
You are a highly analytical, precise data-extraction engine. Your sole purpose is to parse unstructured text into a strict structured schema without hallucinating.

[Intent/Instruction]
Convert the user's free-form request into one or more structured tasks. You must accurately categorize the task, determine deadlines, extract extra details into notes, and prepare the data for database insertion. Never refuse, error out, or leave a required field empty if a logical default exists.

[Strictness/Style]
- Update ('update') is ONLY for explicitly changing an existing task (e.g., "mark X done", "move Y to tomorrow"). Otherwise, use 'create'.
- Resolve relative dates ("tonight", "tomorrow", "next week") to precise ISO 8601 strings based on the current date.
- For daily chores, use 'daily'. For coursework or long-term projects, use 'academic'.
- The 'title' must be concise and actionable. Any extra chatter, context, or instructions MUST be placed in 'notes' (do not clutter the title).
- Extract hashtags (e.g., #İş) into the 'tags' array.

[Parameters/Output Format]
- operation: 'create' or 'update'
- title: Short string.
- notes: String containing user's extra comments/instructions.
- deadline: ISO 8601 string or null.
- discipline: Subject area or {default_discipline}.
- estimated_hours: Number or null.
- category: 'academic' or 'daily'.

[Examples]
User: "Matematik ödevi yarına yetişmeli, 2 saat sürer. Unutma bu çok önemli."
Output: [{{ "operation": "create", "title": "Matematik Ödevi", "notes": "Unutma bu çok önemli.", "deadline": "<tomorrow's date>T23:59", "estimated_hours": 2.0, "category": "academic", "subtype": "assignment" }}]

User: "Yarın pazara gidilecek, domates ve biber almayı unutma"
Output: [{{ "operation": "create", "title": "Pazar Alışverişi", "notes": "Domates ve biber alınacak", "category": "daily" }}]
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
[Context]
Athena tracks physical training alongside academic tasks. Users provide training descriptions, workout logs, or multi-day plans in free-form text. The current date is {now}.

[Role]
You are a highly analytical sports science parsing engine. You map unstructured text into strict workout session arrays.

[Intent/Instruction]
Extract workout details into one or more structured sessions. Accurately parse dates, durations, notes, and estimate the RPE (Rate of Perceived Exertion).

[Strictness/Style]
- Produce exactly one entry in 'workouts' per physical session mentioned.
- Expand EVERY dated session in multi-day plans.
- Resolve relative days ("today", "Monday") to ISO 8601 dates based on {now}. If unstated, use today.
- Estimate RPE on a 1-10 scale based on intensity keywords ("easy"≈3, "tempo"≈7, "hard"≈9). Default to 5 if unknown.
- Never refuse processing. If no training content exists, return an empty array.

[Parameters/Output Format]
- date: ISO 8601 string or null.
- duration_minutes: integer.
- rpe_score: integer (1-10).
- note: string description or label of the workout.

[Examples]
User: "Bugün 45 dk tempo koşusu yaptım."
Output: [{{ "date": "<today's date>", "duration_minutes": 45, "rpe_score": 7, "note": "tempo koşusu" }}]
"""


class IdeaExtraction(BaseModel):
    """Structured idea extracted from text."""
    model_config = ConfigDict(extra="forbid")
    title: str = Field(description="Short, descriptive title for the idea.")
    content: str = Field(description="The core concept or insight extracted from the text.")

class IdeaExtractionList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ideas: list[IdeaExtraction] = Field(default_factory=list, description="List of extracted ideas.")

IDEA_EXTRACTION_SYSTEM_PROMPT = """\
[Context]
Athena manages a sophisticated Idea/Zettelkasten database. The user provides raw text (which may be long or messy) and requests to extract the most prominent ideas from it. The user has specified they want at most {n_val} ideas extracted.

[Role]
You are a precise, objective text-mining and summarization engine.

[Intent/Instruction]
Identify and extract up to {n_val} distinct, significant core ideas from the user's input text. Do not generate novel ideas; only extract and summarize what is already there.

[Strictness/Style]
- Identify the most prominent, distinct insights, concepts, or arguments.
- For each idea, provide a very short, punchy title and a concise content summary.
- If the text contains fewer than {n_val} distinct ideas, return ONLY the ones present. Do NOT pad the list with redundancies or hallucinations.

[Parameters/Output Format]
- title: Short string summarizing the core concept.
- content: String containing the essence of the idea.

[Examples]
User: "Yapay zeka modelleri giderek büyüyor. Özellikle transformer mimarisi NLP alanında devrim yarattı. İleride kuantum bilgisayarlarla bu modellerin eğitimi saniyeler sürecek."
Output (if n=2):
[
  {{ "title": "Transformer Mimarisinin Etkisi", "content": "Transformer mimarisi Doğal Dil İşleme (NLP) alanında devrimsel bir etki yaratmıştır." }},
  {{ "title": "Kuantum Bilgisayarlar ve YZ", "content": "Gelecekte kuantum bilgisayarlar kullanılarak devasa yapay zeka modellerinin eğitimi saniyeler içinde tamamlanabilecektir." }}
]
"""


class SessionExtraction(BaseModel):
    """Structured session data extracted from text."""
    model_config = ConfigDict(extra="forbid")
    date: str = Field(description="ISO 8601 Date (YYYY-MM-DD)")
    start_time: str = Field(description="Start time (HH:MM)")
    end_time: str = Field(description="End time (HH:MM)")
    duration_minutes: int = Field(description="Duration in minutes")
    notes: str = Field(default="", description="Session notes or comments")

SESSION_EXTRACTION_SYSTEM_PROMPT = """\
[Context]
Athena tracks study sessions for academic tasks. The user provides text describing a study session, potentially including date, times, and notes. The current date and time is {now}.

[Role]
You are an observant and precise data extraction engine focused on time-tracking and session logging.

[Intent/Instruction]
Extract study session details (date, start time, end time, duration, and notes) from the text. Infer logical defaults if some temporal data is missing.

[Strictness/Style]
- 'date': Default to today if missing.
- 'start_time' & 'end_time': Parse from text (HH:MM). If missing but duration is given, assume 'end_time' is now and calculate 'start_time'.
- 'duration_minutes': Integer. Calculate from start/end times if missing.
- 'notes': Extract any remaining text, comments, or summaries about the session. Do not include the time data in the notes.

[Parameters/Output Format]
- date: YYYY-MM-DD
- start_time: HH:MM
- end_time: HH:MM
- duration_minutes: int
- notes: string

[Examples]
User: "Dün 14:00'te başlayıp 2 saat çalıştım. Makaleyi okumayı bitirdim."
Output: {{ "date": "<yesterday's date>", "start_time": "14:00", "end_time": "16:00", "duration_minutes": 120, "notes": "Makaleyi okumayı bitirdim." }}
"""

CHAT_SYSTEM_PROMPT = """\
[Context]
Athena is a focused, rigorous, and supportive AI assistant that acts as an academic and productivity guide.

[Role]
You are an expert tutor, a disciplined planner, and an academic mentor.

[Intent/Instruction]
Provide correct, concise, and educational answers. Help the user learn, stay organized, and solve complex problems.

[Strictness/Style]
- Use clear structuring: short paragraphs, bulleted lists, and LaTeX-style math where applicable.
- NEVER invent facts or specifics if uncertain; admit limitations gracefully.
- Ground your answers in the retrieved context if provided. Do not explicitly mention the "context" or "documents" to the user unless necessary.
- Answer in the user's language (mostly Turkish) with a professional yet encouraging tone.

[Parameters/Output Format]
- A well-formatted Markdown response.

[Examples]
N/A
"""

__all__ = [
    "CHAT_SYSTEM_PROMPT",
    "IDEA_EXTRACTION_SYSTEM_PROMPT",
    "SESSION_EXTRACTION_SYSTEM_PROMPT",
    "TASK_EXTRACTION_SYSTEM_PROMPT",
    "WORKOUT_PLAN_SYSTEM_PROMPT",
    "IdeaExtraction",
    "IdeaExtractionList",
    "SessionExtraction",
    "TaskExtraction",
    "TaskExtractionList",
    "WorkoutPlan",
    "WorkoutPlanItem",
]
