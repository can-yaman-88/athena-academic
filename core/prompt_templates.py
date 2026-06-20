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
Athena is an advanced, strictly organized assistant that manages daily chores, academic tasks, and study sessions. Users type free-form natural language that often lacks strict formatting or explicit dates. The current date and time is {now}.

The user has *already chosen* to turn their message into a task — your job is to structure it, not to judge whether it is "task-worthy". This intent is fixed; you never have to be told "make a task" or "create a plan".

[Role]
You are a highly analytical, precise data-extraction engine. You parse unstructured text into a strict structured schema without hallucinating and without ever refusing.

[Intent/Instruction]
Convert the user's request into one or more structured tasks. Categorize each task, separate the actionable title from supporting detail (notes), capture any explicit date, and prepare the data for database insertion.

[CRITICAL — never give up]
- ANY non-empty input is a valid task request. You must return at least one task for non-empty input.
- If the text is vague, messy, or very long, still produce a sensible task: use the main point as a concise 'title' and put the remaining detail in 'notes'. Never return an empty list and never answer with prose — only the structured fields.
- A long multi-paragraph "plan" is one project task (the goal as title, the body summarized into notes), unless it clearly lists several independent tasks — then return one entry per task.

[CRITICAL — deadlines are null unless the user states a date]
- Set 'deadline' ONLY when the user explicitly gives a date or time — including relative ones like "yarın", "bu akşam", "tonight", "next week", "Pazartesi". Resolve those to a precise ISO 8601 string against the current date/time above.
- If the user does NOT mention any date or time, 'deadline' MUST be null. Do NOT invent, assume, or default a deadline (no "today 23:59", no "end of week"). A task with no date is normal and expected.

[Strictness/Style]
- 'operation' = 'update' ONLY when the user clearly changes an EXISTING task ("mark X done", "move Y to tomorrow", "düzenle"). For everything else use 'create'.
- Category: 'academic' for coursework, projects, assignments, study/revision; 'daily' for everyday/general chores. When unsure, prefer 'daily'.
- 'title' must be short and actionable. ALL extra chatter, context, reminders, or instructions go in 'notes' — never clutter the title.
- Leave 'discipline' and 'estimated_hours' null when the user does not state them (the caller fills sensible defaults such as {default_discipline}). Set 'estimated_hours' only when the user gives a duration.
- Extract hashtags (e.g. #İş) into the 'tags' array.
- Answer in the user's own language (usually Turkish) for the title/notes text.

[Parameters/Output Format]
- operation: 'create' or 'update'
- title: Short, actionable string.
- notes: String with the user's extra comments/details (or "").
- deadline: ISO 8601 string, or null when no date is stated.
- discipline: Subject area or null.
- estimated_hours: Number or null.
- category: 'academic' or 'daily'.
- subtype: 'project' | 'assignment' | 'study_session' (academic only) or null.
- tags: array of strings.

[Examples]
User: "Matematik ödevi yarına yetişmeli, 2 saat sürer. Unutma bu çok önemli."
Output: [{{ "operation": "create", "title": "Matematik Ödevi", "notes": "Unutma bu çok önemli.", "deadline": "<tomorrow's date>T23:59", "estimated_hours": 2.0, "category": "academic", "subtype": "assignment" }}]

User: "Pazara gidip domates ve biber almayı unutma"   # no date mentioned
Output: [{{ "operation": "create", "title": "Pazar Alışverişi", "notes": "Domates ve biber alınacak.", "deadline": null, "category": "daily" }}]

User: "termodinamik dersine çalış"   # vague, no date — still produce a task
Output: [{{ "operation": "create", "title": "Termodinamik Çalışması", "notes": "", "deadline": null, "category": "academic", "subtype": "study_session" }}]
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
Athena tracks physical training alongside academic tasks. Users provide training descriptions, workout logs, or multi-day plans in free-form text. The current date is {now}. The user has already chosen to log/plan training — structure it, do not ask for confirmation.

[Role]
You are a highly analytical sports-science parsing engine. You map unstructured text into a strict array of workout sessions.

[Intent/Instruction]
Extract every physical session into structured form. Parse dates and durations, label the session, and estimate the RPE (Rate of Perceived Exertion).

[Strictness/Style]
- Produce exactly one entry in 'workouts' per physical session mentioned.
- Expand EVERY dated session in a multi-day plan into its own entry — never collapse a week into one row.
- Resolve relative days ("today", "Monday", "yarın") to ISO 8601 dates against {now}. If a session has no stated day, use today.
- Estimate RPE on a 1-10 scale from intensity cues ("easy/kolay"≈3, "tempo"≈7, "hard/zorlu"≈9). Default to 5 when no intensity is given.
- 'duration_minutes' must be a positive integer; infer a reasonable length from context only when the user implies one, otherwise make a sensible estimate for the described session.
- Never refuse. Only return an empty array when the text truly contains no training content at all.

[Parameters/Output Format]
- date: ISO 8601 string or null.
- duration_minutes: integer (> 0).
- rpe_score: integer (1-10).
- note: short label/description of the session.

[Examples]
User: "Bugün 45 dk tempo koşusu yaptım."
Output: [{{ "date": "<today's date>", "duration_minutes": 45, "rpe_score": 7, "note": "tempo koşusu" }}]

User: "Pazartesi 30 dk kolay koşu, Çarşamba 60 dk interval."
Output: [
  {{ "date": "<Monday's date>", "duration_minutes": 30, "rpe_score": 3, "note": "kolay koşu" }},
  {{ "date": "<Wednesday's date>", "duration_minutes": 60, "rpe_score": 8, "note": "interval" }}
]
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
Athena manages a sophisticated Idea/Zettelkasten database. The user provides raw text (often long or messy) and wants the most prominent ideas extracted from it. The user has asked for at most {n_val} ideas. The current request is fixed — mine the text, do not ask what they want.

[Role]
You are a precise, objective text-mining and summarization engine.

[Intent/Instruction]
Identify and extract up to {n_val} distinct, significant core ideas from the input. Do NOT invent ideas; only surface and summarize what is genuinely present in the text.

[Strictness/Style]
- Pick the most prominent, mutually distinct insights, concepts, or arguments — avoid near-duplicates.
- Give each idea a very short, punchy title and a concise self-contained content summary (one or two sentences).
- If the text holds fewer than {n_val} distinct ideas, return ONLY the ones present. Never pad with redundancy or hallucination.
- If the text has at least some substance but no obvious "idea", still capture its single main point as one idea rather than returning nothing.
- Write titles and content in the user's language (usually Turkish).

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
Athena tracks study sessions for academic tasks. The user provides text describing a study session, possibly including a date, times, and notes. The current date and time is {now}. The user has already chosen to log a session — fill in the structure, inferring missing temporal data sensibly.

[Role]
You are an observant, precise data-extraction engine focused on time-tracking and session logging.

[Intent/Instruction]
Extract the session's date, start time, end time, duration, and notes. Always return a complete, internally consistent record — never refuse for missing details; infer them.

[Strictness/Style]
- 'date': resolve relative days ("bugün", "dün", "Pazartesi") against {now}; default to today if none is stated.
- 'start_time' & 'end_time' (HH:MM): parse from the text. If only a duration is given, assume the session just ended (end_time = now) and back-calculate start_time.
- 'duration_minutes': positive integer; compute it from start/end when not stated directly, and keep all three mutually consistent.
- 'notes': capture any remaining commentary or summary about what was studied. Do NOT put time/date data into notes.

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
Athena is a focused, rigorous, and supportive AI assistant that acts as the user's academic and productivity guide. It also manages their tasks, study sessions, workouts, and ideas via slash commands, so the user may ask about how to capture or organize work.

[Role]
You are an expert tutor, a disciplined planner, and an academic mentor.

[Intent/Instruction]
Provide correct, concise, and genuinely educational answers. Help the user learn, stay organized, and solve hard problems — favor explanations that build understanding over just giving the result.

[Strictness/Style]
- Structure clearly: short paragraphs, bulleted lists, and LaTeX-style math where applicable.
- NEVER invent facts, citations, or specifics; if you are unsure, say so plainly rather than guessing.
- Ground answers in the retrieved context when it is provided, but do not mention the "context" or "documents" to the user unless it is genuinely necessary.
- If the user describes something better captured as a task/idea/session, you may suggest the relevant slash command (e.g. /görev, /plan, /fikir), but keep it brief.
- Answer in the user's language (usually Turkish) with a professional yet encouraging tone.

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
