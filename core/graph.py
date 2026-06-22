"""LangGraph workflow for Athena-Academic.

The graph is intentionally small and explicit:

    START -> router_node -> (conditional) -> {chat_node | pdf_tool_node | task_tool_node} -> END

``router_node`` uses a lightweight LLM constrained by
:class:`~core.prompt_templates.RouteDecision` to choose the destination, and the
conditional edge dispatches strictly on that choice. The two tool nodes execute
the bound (mocked) Python tools from :mod:`core.tools`. Every node returns a
*partial* state mapping — state is never mutated in place.

All LLMs are reached through OpenRouter (OpenAI-compatible) via
``langchain-openai``'s ``ChatOpenAI``. They are injectable so the routing logic
can be verified offline with fakes; the defaults are built lazily so importing
this module never requires the package or an API key.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import date as date_type
from datetime import datetime
from functools import partial
from typing import Any, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from config import settings
from core.commands import COMMANDS, help_text, parse_command
from core.prompt_templates import (
    CHAT_SYSTEM_PROMPT,
    IDEA_EXTRACTION_SYSTEM_PROMPT,
    SESSION_EXTRACTION_SYSTEM_PROMPT,
    TASK_EXTRACTION_SYSTEM_PROMPT,
    IdeaExtractionList,
    RouteDecision,
    SessionExtraction,
    TaskExtraction,
    TaskExtractionList,
)
from core.schemas import (
    AcademicSession,
    AcademicSubtype,
    Material,
    Note,
    Task,
    TaskCategory,
    TaskStatus,
)
from core.state import AthenaState, RouteTarget
from core.tools import add_task, process_pdf

logger = logging.getLogger("athena.graph")

# Maps a routing target to the tool name a node will surface in active_tool.
_TOOL_FOR_ROUTE: dict[RouteTarget, Optional[str]] = {
    "chat_node": None,
    "pdf_tool_node": "process_pdf",
    "task_tool_node": "add_task",
    "session_node": "add_session",
    "idea_extractor_node": "extract_ideas",
    "research_node": "deep_research",
}

_PDF_PATH_RE = re.compile(r"\S+\.pdf\b", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# LLM factories (lazy import so module import needs no package / key)
# --------------------------------------------------------------------------- #
def _make_llm(
    model: str,
    max_tokens: int,
    temperature: Optional[float] = None,
    *,
    callbacks: Optional[list] = None,
) -> Any:
    """Construct a ChatOpenAI client pointed at OpenRouter."""
    from langchain_openai import ChatOpenAI

    api_key = os.environ.get(settings.openrouter_api_key_env)
    if not api_key:
        raise RuntimeError(
            f"Environment variable {settings.openrouter_api_key_env} is not set; "
            "it is required to call models through OpenRouter."
        )

    kwargs: dict[str, Any] = dict(
        model=model,
        base_url=settings.openrouter_base_url,
        api_key=api_key,
        max_tokens=max_tokens,
        # Optional attribution headers recommended by OpenRouter.
        default_headers={"X-Title": "Athena-Academic"},
    )
    if temperature is not None:
        kwargs["temperature"] = temperature
    if callbacks:
        kwargs["callbacks"] = callbacks
    return ChatOpenAI(**kwargs)


def _make_structured_llm(llm: Any, schema: type) -> Any:
    """Bind a Pydantic schema as a tool with tool_choice='auto'.

    LangChain's with_structured_output(method="function_calling") forces
    tool_choice to the schema name (object form), which Qwen/Alibaba thinking
    models reject with a 400. Using tool_choice='auto' avoids the restriction
    while still directing the model toward the schema tool.
    """
    from langchain_core.output_parsers.openai_tools import PydanticToolsParser

    bound = llm.bind_tools([schema], tool_choice="auto")
    return bound | PydanticToolsParser(tools=[schema], first_tool_only=True)


def _default_router_llm(callbacks: Optional[list] = None) -> Any:
    """Lightweight, deterministic router bound to the RouteDecision schema."""
    llm = _make_llm(
        settings.router_model, settings.router_max_tokens, temperature=0,
        callbacks=callbacks,
    )
    return _make_structured_llm(llm, RouteDecision)


def _default_chat_llm(callbacks: Optional[list] = None) -> Any:
    """Conversational model for chat_node (no temperature: Opus rejects it)."""
    return _make_llm(
        settings.chat_model, settings.chat_max_tokens, callbacks=callbacks
    )


def _default_task_extractor_llm(callbacks: Optional[list] = None) -> Any:
    """Lightweight, deterministic extractor bound to the TaskExtraction schema."""
    llm = _make_llm(
        settings.router_model, settings.router_max_tokens, temperature=0,
        callbacks=callbacks,
    )
    return _make_structured_llm(llm, TaskExtractionList)


def _default_session_extractor_llm(callbacks: Optional[list] = None) -> Any:
    llm = _make_llm(settings.router_model, settings.router_max_tokens, temperature=0, callbacks=callbacks)
    return _make_structured_llm(llm, SessionExtraction)


def _default_idea_extractor_llm(callbacks: Optional[list] = None) -> Any:
    llm = _make_llm(settings.router_model, settings.router_max_tokens, temperature=0, callbacks=callbacks)
    return _make_structured_llm(llm, IdeaExtractionList)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _last_human_message(messages: list[Any]) -> str:
    """Return the text of the most recent human message, or '' if none."""
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            content = message.content
            return content if isinstance(content, str) else str(content)
    return ""


def _resolve_deadline(value: Optional[str], now: datetime) -> Optional[datetime]:
    """Turn the extractor's optional ISO deadline into a concrete datetime.
    Returns None if missing or unparseable.
    """
    if value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            logger.warning("unparseable deadline %r; returning None", value)
    return None


def _attachments_text(state: AthenaState) -> str:
    """Concatenate the markdown of any chat-attached materials in the state."""
    parts: list[str] = []
    for att in state.get("attachments") or []:
        md = (att or {}).get("markdown") if isinstance(att, dict) else None
        if md:
            name = att.get("name", "attachment")
            parts.append(f"--- {name} ---\n{md}")
    return "\n\n".join(parts)


def _resolve_target_task(
    tasks: list[Task], target_hint: Optional[str], target_date, now: datetime
) -> Optional[Task]:
    """Pick the task to edit, per the rule: same-day → else nearest future.

    ``target_date`` (a date or None): when given, restrict to tasks due that day;
    when None, prefer tasks due *today*, else the nearest future task. ``target_hint``
    (a phrase) breaks ties by case-insensitive title match.
    """
    def _match(cands: list[Task]) -> Optional[Task]:
        if not cands:
            return None
        if target_hint:
            hint = target_hint.lower()
            hits = [t for t in cands if hint in t.title.lower()]
            if hits:
                return sorted(hits, key=lambda t: t.deadline or datetime.max)[0]
        return sorted(cands, key=lambda t: t.deadline or datetime.max)[0]

    # Search among all tasks (including subtasks) if explicitly hinted, otherwise just top-level
    cands_pool = tasks if target_hint else [t for t in tasks if t.parent_id is None]

    if target_date is not None:
        return _match([t for t in cands_pool if t.deadline and t.deadline.date() == target_date])

    today = now.date()
    todays = [t for t in cands_pool if t.deadline and t.deadline.date() == today]
    hit = _match(todays)
    if hit:
        return hit
    future = [t for t in cands_pool if not t.deadline or t.deadline >= now]
    return _match(future)


_DATE_RE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{2,4})\b"
)


def _extract_date_token(text: str, now: datetime):
    """Pull a date (ISO/dd.mm.yyyy or bugün/yarın/today/tomorrow) from text.

    Returns (date|None, remaining_text_without_token).
    """
    lowered = text.lower()
    for word, delta in (("bugün", 0), ("today", 0), ("yarın", 1), ("tomorrow", 1)):
        if word in lowered:
            from datetime import timedelta

            d = (now + timedelta(days=delta)).date()
            return d, re.sub(word, "", text, flags=re.IGNORECASE).strip()
    m = _DATE_RE.search(text)
    if m:
        token = m.group(1)
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d.%m.%y", "%d/%m/%y"):
            try:
                d = datetime.strptime(token, fmt).date()
                return d, (text[: m.start()] + text[m.end():]).strip()
            except ValueError:
                continue
    return None, text


def _resolve_task_by_name(
    tasks: list[Task], name: str, target_date, *, include_completed: bool = False
) -> Optional[Task]:
    """Find a task by name (exact substring else fuzzy) optionally on a date."""
    import difflib

    cands = tasks  # include subtasks in direct name lookups
    if not include_completed:
        cands = [t for t in cands if t.status != TaskStatus.COMPLETED]
    if target_date is not None:
        cands = [t for t in cands if t.deadline and t.deadline.date() == target_date]
    if not cands:
        return None
    name = (name or "").strip().lower()
    if not name:
        return sorted(cands, key=lambda t: t.deadline or datetime.max)[0]
    exact = [t for t in cands if name == t.title.lower() or name in t.title.lower()]
    if exact:
        return sorted(exact, key=lambda t: t.deadline or datetime.max)[0]
    titles = {t.title.lower(): t for t in cands}
    close = difflib.get_close_matches(name, list(titles), n=1, cutoff=0.3)
    return titles[close[0]] if close else None


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #
def router_node(state: AthenaState, *, router_llm: Any) -> dict[str, Any]:
    """Classify the latest message and record the routing decision.

    A leading slash command bypasses the LLM router entirely (deterministic).
    """
    user_text = _last_human_message(state["messages"])

    command, _remainder, n_val = parse_command(user_text)
    if command is not None:
        return {
            "route": command.route,
            "active_tool": _TOOL_FOR_ROUTE.get(command.route),
            "command": command.name,
            "n_val": n_val,
        }

    return {
        "route": "chat_node",
        "active_tool": _TOOL_FOR_ROUTE["chat_node"],
        "command": None,
    }


async def chat_node(
    state: AthenaState,
    *,
    chat_llm: Any = None,
    chroma: Any = None,
    brain: Any = None,
    callbacks: Any = None,
) -> dict[str, Any]:
    """Answer conversationally, grounded in retrieved document context + memory."""
    # /yardim is deterministic — list commands without an LLM call.
    if state.get("command") == "yardim":
        return {"messages": [AIMessage(content=help_text())], "active_tool": None}

    query = _last_human_message(state["messages"])

    context = ""
    if chroma is not None and query:
        try:
            results = chroma.query_documents(query, n_results=3)
            context = "\n\n".join(r["text"] for r in results if r.get("text"))
        except Exception:
            # Retrieval is best-effort; never let it break the chat turn.
            context = ""

    # Long-term memory (Brain): inject relevant remembered facts about the user.
    memory = ""
    if brain is not None and query:
        try:
            facts = await brain.query_relevant(query, n=settings.brain_recall_k)
            memory = "\n".join(f"- {f['text']}" for f in facts if f.get("text"))
        except Exception:
            memory = ""

    attach = _attachments_text(state)
    if attach:
        context = (context + "\n\n" if context else "") + "[Attached by user]\n" + attach[:6000]

    system = CHAT_SYSTEM_PROMPT.format(
        context=context or "(no relevant context found)",
        memory=memory or "(no stored facts yet)",
    )
    
    llm_to_use = chat_llm
    override = state.get("model_override")
    if override:
        try:
            from core.graph import _make_llm
            # Attempt to use the overridden model
            llm_to_use = _make_llm(override, settings.chat_max_tokens, callbacks=callbacks)
        except Exception as e:
            logger.warning("Could not override model with %s: %s", override, e)

    response = await llm_to_use.ainvoke([SystemMessage(content=system), *state["messages"]])
    return {
        "messages": [response],
        "retrieved_context": context or None,
        "active_tool": None,
    }


def pdf_tool_node(state: AthenaState) -> dict[str, Any]:
    """Execute the (mocked) PDF processing tool."""
    user_text = _last_human_message(state["messages"])
    match = _PDF_PATH_RE.search(user_text)
    file_path = match.group(0) if match else "<unspecified>.pdf"
    result = process_pdf.invoke({"file_path": file_path})
    return {
        "messages": [AIMessage(content=result)],
        "active_tool": "process_pdf",
    }


def _materials_from_attachments(state: AthenaState) -> list[Material]:
    mats: list[Material] = []
    for att in state.get("attachments") or []:
        if not isinstance(att, dict):
            continue
        mats.append(
            Material(
                kind="file",
                name=att.get("name", "attachment"),
                source=att.get("path") or att.get("name", "attachment"),
                markdown_path=att.get("markdown_path"),
            )
        )
    return mats


async def _generate_subtasks(
    parent: Task, context_text: str, subtask_llm: Any, now: datetime, max_subtasks: Optional[int] = None
) -> list[Task]:
    """Break an academic task into independent subtask rows via the LLM."""
    from core.subtasks import SUBTASK_SYSTEM_PROMPT, SubtaskPlan  # local import

    payload = (
        f"Parent task: {parent.title}\nDiscipline: {parent.discipline}\n"
        f"Subtype: {parent.subtype.value if parent.subtype else 'n/a'}\n"
        f"Deadline: {parent.deadline.isoformat() if parent.deadline else 'none (parent has no deadline → leave subtask deadlines null)'}\n\n"
        f"Material/spec (may be empty):\n{context_text or '(none)'}"
    )
    limit_text = (
        f"- Produce up to {max_subtasks} subtasks; each must be a single actionable unit with a clear title."
        if max_subtasks
        else "- Produce 3–8 subtasks; each must be a single actionable unit with a clear title."
    )
    plan: Optional[SubtaskPlan] = await subtask_llm.ainvoke(
        [
            SystemMessage(content=SUBTASK_SYSTEM_PROMPT.format(now=now.isoformat(timespec="minutes"), limit_text=limit_text)),
            HumanMessage(content=payload),
        ]
    )
    subs: list[Task] = []
    for item in (plan.subtasks if plan else []):
        deadline = _resolve_deadline(item.deadline, now)
        if deadline and parent.deadline:
            deadline = min(deadline, parent.deadline)
        elif not deadline and parent.deadline:
            deadline = parent.deadline
        subs.append(
            Task(
                title=item.title,
                deadline=deadline,
                discipline=parent.discipline,
                estimated_hours=item.estimated_hours or settings.default_estimated_hours,
                category=TaskCategory.ACADEMIC,
                subtype=parent.subtype,
                parent_id=parent.id,
            )
        )
    return subs


async def task_tool_node(
    state: AthenaState,
    *,
    task_extractor_llm: Any = None,
    sqlite_manager: Any = None,
    subtask_llm: Any = None,
    callbacks: Any = None,
) -> dict[str, Any]:
    """Create/update tasks (and notes) from chat, honoring slash-command hints."""
    user_text = _last_human_message(state["messages"])
    command, remainder, n_val = parse_command(user_text)
    hints = COMMANDS[command.name].hints if command else {}
    working_text = remainder if command else user_text

    override = state.get("model_override")
    if override:
        from core.graph import _make_llm, _make_structured_llm
        from core.prompt_templates import TaskExtractionList
        from core.subtasks import SubtaskPlan
        try:
            base_llm = _make_llm(override, settings.chat_max_tokens, callbacks=callbacks)
            task_extractor_llm = _make_structured_llm(base_llm, TaskExtractionList)
            subtask_llm = _make_structured_llm(base_llm, SubtaskPlan)
        except Exception as e:
            logger.warning("Could not override task models with %s: %s", override, e)

    if sqlite_manager is None or task_extractor_llm is None:
        result = add_task.invoke(
            {"title": working_text or "Untitled task", "deadline": "TBD",
             "discipline": "General", "estimated_hours": 1.0}
        )
        return {"messages": [AIMessage(content=result)], "active_tool": "add_task"}

    now = datetime.now()
    tasks = await sqlite_manager.list_tasks()

    # --- extract task ops ------------------------------------------------- #
    # Cap very long input so a huge /plan paste can't blow the model's context
    # window (the source of the occasional "memory error" on long plans). The
    # head goes to the extractor; the tail is preserved into the task's notes
    # by the deterministic fallback so nothing the user typed is lost.
    _MAX_EXTRACT_CHARS = 8000
    capped_text = working_text[:_MAX_EXTRACT_CHARS]
    overflow_text = working_text[_MAX_EXTRACT_CHARS:].strip()
    attach_text = _attachments_text(state)
    extractor_input = capped_text
    if attach_text:
        extractor_input += f"\n\n[Attached material]\n{attach_text[:6000]}"

    def _fallback_ops() -> list[TaskExtraction]:
        """Guarantee a command never gives up.

        When the extractor returns nothing (empty result or an exception),
        synthesize a single task straight from the raw text: the first line
        becomes the title and everything else is kept in notes. This is what
        makes /gorev and /plan self-sufficient — any non-empty input yields a
        task, with a null deadline (no date is invented).
        """
        snippet = capped_text.strip()
        lines = snippet.splitlines()
        first_line = lines[0].strip() if lines else ""
        title = first_line[:120].strip() or "Yeni görev"
        note_parts = [p for p in (
            first_line[120:].strip(),
            "\n".join(lines[1:]).strip(),
            overflow_text,
        ) if p]
        return [TaskExtraction(
            operation="create",
            title=title,
            notes="\n".join(note_parts),
            category=hints.get("category"),
        )]

    try:
        extraction: Optional[TaskExtractionList] = await task_extractor_llm.ainvoke(
            [
                SystemMessage(content=TASK_EXTRACTION_SYSTEM_PROMPT.format(
                    now=now.isoformat(timespec="minutes"),
                    default_discipline=settings.default_discipline,
                    default_estimated_hours=settings.default_estimated_hours,
                )),
                HumanMessage(content=extractor_input),
            ]
        )
        ops = extraction.tasks if extraction is not None else []
    except Exception:
        logger.exception("task extraction failed; using deterministic fallback")
        ops = []

    # A command must never end with "couldn't extract". For the create/plan
    # family, fall back to a single task built from the raw text. (Management
    # operations — note/complete/delete/reschedule — already returned above.)
    if not ops:
        if not working_text.strip():
            return {"messages": [AIMessage(content=(
                "Boş bir görev gönderdin. Örn: '/görev yarın 9'da 1 saat kalkülüs tekrarı'."))],
                "active_tool": "add_task"}
        ops = _fallback_ops()

    forced_op = hints.get("operation")  # create | update | None
    forced_category = hints.get("category")
    forced_subtype = hints.get("subtype")
    materials = _materials_from_attachments(state)

    created: list[Task] = []
    updated: list[Task] = []
    for op in ops:
        operation = forced_op or op.operation

        if operation == "update":
            target_date = None
            if op.deadline:
                try:
                    target_date = datetime.fromisoformat(op.deadline).date()
                except ValueError:
                    target_date = None
            target = _resolve_target_task(
                tasks, op.target_hint or op.title, target_date, now
            )
            if target is None:
                return {"messages": [AIMessage(content=(
                    "Düzenlenecek görevi bulamadım (bugün ya da en yakın gelecekte)."))],
                    "active_tool": "add_task"}
            if op.deadline:
                target.deadline = _resolve_deadline(op.deadline, now)
            if op.estimated_hours:
                target.estimated_hours = op.estimated_hours
            if op.discipline:
                target.discipline = op.discipline
            cat = forced_category or op.category
            if cat:
                target.category = TaskCategory(cat)
            sub = forced_subtype or op.subtype
            if sub and target.category == TaskCategory.ACADEMIC:
                target.subtype = AcademicSubtype(sub)
            if op.tags:
                # Merge new tags or just replace? The prompt says "Extract these". We should append or replace.
                # Since LLM might not know old tags, let's just append unique tags.
                target.tags = list(set(target.tags + op.tags))
            await sqlite_manager.update_task(target)
            updated.append(target)
            continue

        # create
        cat_value = forced_category or op.category or "daily"
        category = TaskCategory(cat_value)
        subtype = None
        if category == TaskCategory.ACADEMIC:
            sub_value = forced_subtype or op.subtype
            subtype = AcademicSubtype(sub_value) if sub_value else None
        
        parent_id = None
        if op.parent_hint:
            parent_target = _resolve_target_task(tasks, op.parent_hint, None, now)
            if parent_target:
                parent_id = parent_target.id
                # Inherit deadline from parent if it's earlier
                op_deadline = _resolve_deadline(op.deadline, now)
                if op_deadline and parent_target.deadline:
                    deadline = min(op_deadline, parent_target.deadline)
                elif not op_deadline and parent_target.deadline:
                    deadline = parent_target.deadline
                else:
                    deadline = op_deadline
            else:
                deadline = _resolve_deadline(op.deadline, now)
        else:
            deadline = _resolve_deadline(op.deadline, now)

        task = Task(
            title=op.title or (working_text or "Untitled task"),
            deadline=deadline,
            discipline=op.discipline or settings.default_discipline,
            estimated_hours=op.estimated_hours or settings.default_estimated_hours,
            category=category,
            subtype=subtype,
            materials=materials if category == TaskCategory.ACADEMIC else [],
            parent_id=parent_id,
            tags=op.tags,
            notes=[Note(text=op.notes)] if getattr(op, "notes", None) else [],
            is_spaced_repetition=hints.get("is_spaced_repetition", False),
        )
        await sqlite_manager.create_task(task)
        created.append(task)
        logger.info("created task id=%s title=%s cat=%s", task.id, task.title, category.value)

        if hints.get("generate_subtasks") and subtask_llm is not None:
            try:
                subs = await _generate_subtasks(task, extractor_input, subtask_llm, now, max_subtasks=n_val)
                for s in subs:
                    await sqlite_manager.create_task(s)
                    created.append(s)
            except Exception as e:
                logger.warning("Subtask generation failed: %s", e)

    msgs: list[str] = []
    if created:
        msgs.append(
            ("1 görev oluşturuldu:" if len(created) == 1 else f"{len(created)} görev oluşturuldu:")
            + "\n" + "\n".join(
                f"- '{t.title}' ({t.category.value}"
                + (f"/{t.subtype.value}" if t.subtype else "")
                + f"), {t.deadline.strftime('%Y-%m-%d %H:%M') if t.deadline else 'Tarihsiz'}, {t.estimated_hours:g}h"
                for t in created
            )
        )
    if updated:
        msgs.append(
            ("1 görev güncellendi:" if len(updated) == 1 else f"{len(updated)} görev güncellendi:")
            + "\n" + "\n".join(
                f"- '{t.title}', {t.deadline.strftime('%Y-%m-%d %H:%M') if t.deadline else 'Tarihsiz'}, {t.estimated_hours:g}h"
                for t in updated
            )
        )
    focus = (created + updated)[-1]
    return {
        "messages": [AIMessage(content="\n\n".join(msgs))],
        "active_tool": "add_task",
        "current_task": focus,
    }


async def session_node(
    state: AthenaState,
    *,
    session_extractor_llm: Any = None,
    sqlite_manager: Any = None,
    callbacks: Any = None,
) -> dict[str, Any]:
    """Extract a study session and attach it to an academic task."""
    user_text = _last_human_message(state["messages"])
    command, remainder, n_val = parse_command(user_text)
    working_text = remainder if command else user_text

    override = state.get("model_override")
    if override:
        from core.graph import _make_llm, _make_structured_llm
        from core.prompt_templates import SessionExtraction
        try:
            base_llm = _make_llm(override, settings.chat_max_tokens, callbacks=callbacks)
            session_extractor_llm = _make_structured_llm(base_llm, SessionExtraction)
        except Exception as e:
            logger.warning("Could not override session model with %s: %s", override, e)

    if sqlite_manager is None or session_extractor_llm is None:
        return {"messages": [AIMessage(content="[mock] session tool not wired.")],
                "active_tool": "add_session"}

    now = datetime.now()
    try:
        extraction: Optional[SessionExtraction] = await session_extractor_llm.ainvoke(
            [
                SystemMessage(content=SESSION_EXTRACTION_SYSTEM_PROMPT.format(
                    now=now.isoformat(timespec="minutes"))),
                HumanMessage(content=working_text),
            ]
        )
    except Exception as exc:
        logger.exception("session extraction failed")
        return {"messages": [AIMessage(content=f"Seans verisi çıkarılamadı: {exc}")],
                "active_tool": "add_session"}

    if not extraction:
        return {"messages": [AIMessage(content="Seans çıkarılamadı.")],
                "active_tool": "add_session"}
                
    tasks = await sqlite_manager.list_tasks()
    academic_tasks = [t for t in tasks if t.category == TaskCategory.ACADEMIC]
    target = _resolve_task_by_name(academic_tasks, working_text, None)
    
    if not target:
        return {"messages": [AIMessage(content="Eşleşen akademik görev bulunamadı. Lütfen mesajın içine hedeflenen görev adını yazın.")],
                "active_tool": "add_session"}
                
    try:
        session_date = datetime.fromisoformat(extraction.date).date()
    except ValueError:
        session_date = now.date()

    session = AcademicSession(
        task_id=target.id,
        date=session_date,
        start_time=extraction.start_time,
        end_time=extraction.end_time,
        duration_minutes=extraction.duration_minutes,
        notes=extraction.notes
    )
    await sqlite_manager.create_academic_session(session)
    
    if extraction.notes:
        target.notes = [*target.notes, Note(text=f"[Seans Notu] {extraction.notes}")]
        await sqlite_manager.update_task(target)
    
    return {
        "messages": [AIMessage(content=f"'{target.title}' görevi için {session.duration_minutes} dakikalık seans eklendi.")],
        "active_tool": "add_session",
        "current_task": target
    }


async def idea_extractor_node(
    state: AthenaState,
    *,
    idea_extractor_llm: Any = None,
    sqlite_manager: Any = None,
    callbacks: Any = None,
) -> dict[str, Any]:
    """Extract ideas from text using the provided N value."""
    user_text = _last_human_message(state["messages"])
    command, remainder, n_val = parse_command(user_text)
    working_text = remainder if command else user_text
    n = n_val or 1

    override = state.get("model_override")
    if override:
        from core.graph import _make_llm, _make_structured_llm
        from core.prompt_templates import IdeaExtractionList
        try:
            base_llm = _make_llm(override, settings.chat_max_tokens, callbacks=callbacks)
            idea_extractor_llm = _make_structured_llm(base_llm, IdeaExtractionList)
        except Exception as e:
            logger.warning("Could not override idea model with %s: %s", override, e)

    if idea_extractor_llm is None or sqlite_manager is None:
        return {"messages": [AIMessage(content="[mock] idea tool not wired.")],
                "active_tool": "extract_ideas"}

    try:
        extraction: Optional[IdeaExtractionList] = await idea_extractor_llm.ainvoke(
            [
                SystemMessage(content=IDEA_EXTRACTION_SYSTEM_PROMPT.format(n_val=n)),
                HumanMessage(content=working_text),
            ]
        )
    except Exception as exc:
        logger.exception("idea extraction failed")
        return {"messages": [AIMessage(content=f"Fikir çıkarılamadı: {exc}")],
                "active_tool": "extract_ideas"}

    if not extraction or not extraction.ideas:
        return {"messages": [AIMessage(content="Herhangi bir fikir çıkarılamadı.")],
                "active_tool": "extract_ideas"}

    msgs = [f"{len(extraction.ideas)} Fikir yakalandı ve Zettelkasten'e kaydedildi:"]
    
    from core.schemas import Idea
    for i, item in enumerate(extraction.ideas, 1):
        idea = Idea(title=item.title, content=item.content)
        await sqlite_manager.upsert_idea(idea)
        msgs.append(f"{i}. **{idea.title}**\n   {idea.content}")

    return {
        "messages": [AIMessage(content="\n".join(msgs))],
        "active_tool": "extract_ideas",
    }



async def research_node(
    state: AthenaState,
    *,
    research_llm: Any = None,
    sqlite_manager: Any = None,
    callbacks: Any = None,
) -> dict[str, Any]:
    """Run multi-round Deep Research and stream live progress to the client.

    The final report is returned as an ``AIMessage`` (rendered in chat) and also
    saved as an Idea so it persists in the Fikir Defteri.
    """
    user_text = _last_human_message(state["messages"])
    command, remainder, _ = parse_command(user_text)
    question = (remainder if command else user_text).strip()

    if not question:
        return {
            "messages": [AIMessage(content="Araştırılacak bir konu belirtmedin.")],
            "active_tool": "deep_research",
        }
    if research_llm is None:
        return {
            "messages": [AIMessage(content="[mock] Deep Research not wired (no API key).")],
            "active_tool": "deep_research",
        }

    # Bridge live progress to the SSE stream via LangGraph's custom stream writer.
    writer = None
    try:
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
    except Exception:  # pragma: no cover - older langgraph / no streaming context
        writer = None

    def _emit(data: dict[str, Any]) -> None:
        if writer is not None:
            try:
                writer({"type": "research_progress", **data})
            except Exception:
                pass

    from tools.agentic_tools.deep_research import DeepResearchEngine

    engine = DeepResearchEngine(llm=research_llm, progress=_emit)
    try:
        report, sources = await engine.research(question)
    except Exception as exc:
        logger.exception("deep research failed")
        return {
            "messages": [AIMessage(content=f"Araştırma başarısız oldu: {exc}")],
            "active_tool": "deep_research",
        }

    sources_md = ""
    if sources:
        lines = "\n".join(
            f"{i}. [{s.get('title') or s.get('url')}]({s.get('url')})"
            for i, s in enumerate(sources, 1)
        )
        sources_md = f"\n\n---\n\n**Kaynaklar**\n\n{lines}"

    full = (report or "Araştırma sonuç üretemedi.") + sources_md

    # Persist the report as an Idea so it lives in the Fikir Defteri.
    if sqlite_manager is not None and report:
        try:
            from core.schemas import Idea

            title = question if len(question) <= 120 else question[:117] + "…"
            await sqlite_manager.upsert_idea(Idea(title=title, content=full))
        except Exception:
            logger.exception("failed to save research report as idea")

    return {"messages": [AIMessage(content=full)], "active_tool": "deep_research"}


def route_selector(state: AthenaState) -> RouteTarget:
    """Conditional-edge function: send the run to the router's chosen node."""
    return state.get("route") or "chat_node"


# --------------------------------------------------------------------------- #
# Graph assembly
# --------------------------------------------------------------------------- #
def build_athena_graph(
    *,
    router_llm: Any = None,
    chat_llm: Any = None,
    chroma_manager: Any = None,
    brain_manager: Any = None,
    sqlite_manager: Any = None,
    task_extractor_llm: Any = None,
    subtask_llm: Any = None,
    session_extractor_llm: Any = None,
    idea_extractor_llm: Any = None,
    research_llm: Any = None,
    usage_callback: Any = None,
) -> Any:
    """Build and compile the Athena-Academic routing graph.

    Args:
        router_llm: A runnable whose ``.invoke()`` returns a ``RouteDecision``.
            Defaults to a ChatOpenAI/OpenRouter router bound to the schema.
        chat_llm: A chat model runnable for ``chat_node``. Defaults to the
            configured OpenRouter chat model.
        chroma_manager: Optional ``ChromaManager`` for retrieval in ``chat_node``.
        sqlite_manager: Optional ``SQLiteManager``. When provided, ``task_tool_node``
            persists real tasks; when omitted, it falls back to the Phase 2 mock.
        task_extractor_llm: A runnable whose ``.ainvoke()`` returns a
            ``TaskExtraction``. Defaults to a schema-bound OpenRouter model, but
            only built when ``sqlite_manager`` is supplied (real persistence path).
        usage_callback: Optional LangChain callback handler attached to the default
            LLMs so agent-side token/cost usage is recorded (the "agent" meter).

    Returns:
        A compiled LangGraph ready for ``.invoke(state)`` / ``.stream(state)``.
    """
    callbacks = [usage_callback] if usage_callback is not None else None
    router_llm = router_llm or _default_router_llm(callbacks)
    chat_llm = chat_llm or _default_chat_llm(callbacks)
    # Only stand up the extractors when persistence is available; without a
    # sqlite_manager the tool nodes stay in mock mode and need no LLM/API key.
    if sqlite_manager is not None:
        if task_extractor_llm is None:
            task_extractor_llm = _default_task_extractor_llm(callbacks)
        if research_llm is None:
            try:
                research_llm = _make_llm(
                    settings.research_model, settings.research_model_max_tokens,
                    callbacks=callbacks,
                )
            except Exception:  # pragma: no cover - missing key/package
                research_llm = None
        if session_extractor_llm is None:
            session_extractor_llm = _default_session_extractor_llm(callbacks)
        if idea_extractor_llm is None:
            idea_extractor_llm = _default_idea_extractor_llm(callbacks)
        if subtask_llm is None:
            try:
                sub_base = _make_llm(
                    settings.notes_model, settings.notes_model_max_tokens,
                    callbacks=callbacks,
                )
                from core.subtasks import SubtaskPlan

                subtask_llm = _make_structured_llm(sub_base, SubtaskPlan)
            except Exception:  # pragma: no cover - missing key/package
                subtask_llm = None

    builder = StateGraph(AthenaState)
    builder.add_node("router_node", partial(router_node, router_llm=router_llm))
    builder.add_node(
        "chat_node",
        partial(
            chat_node,
            chat_llm=chat_llm,
            chroma=chroma_manager,
            brain=brain_manager,
            callbacks=callbacks,
        ),
    )
    builder.add_node("pdf_tool_node", pdf_tool_node)
    builder.add_node(
        "task_tool_node",
        partial(
            task_tool_node,
            task_extractor_llm=task_extractor_llm,
            sqlite_manager=sqlite_manager,
            subtask_llm=subtask_llm,
            callbacks=callbacks,
        ),
    )
    builder.add_node(
        "research_node",
        partial(
            research_node,
            research_llm=research_llm,
            sqlite_manager=sqlite_manager,
            callbacks=callbacks,
        ),
    )
    builder.add_node(
        "session_node",
        partial(
            session_node,
            session_extractor_llm=session_extractor_llm,
            sqlite_manager=sqlite_manager,
            callbacks=callbacks,
        ),
    )
    builder.add_node(
        "idea_extractor_node",
        partial(
            idea_extractor_node,
            idea_extractor_llm=idea_extractor_llm,
            sqlite_manager=sqlite_manager,
            callbacks=callbacks,
        ),
    )

    builder.add_edge(START, "router_node")
    builder.add_conditional_edges(
        "router_node",
        route_selector,
        {
            "chat_node": "chat_node",
            "pdf_tool_node": "pdf_tool_node",
            "task_tool_node": "task_tool_node",
            "research_node": "research_node",
            "session_node": "session_node",
            "idea_extractor_node": "idea_extractor_node",
        },
    )
    builder.add_edge("chat_node", END)
    builder.add_edge("pdf_tool_node", END)
    builder.add_edge("task_tool_node", END)
    builder.add_edge("research_node", END)
    builder.add_edge("session_node", END)
    builder.add_edge("idea_extractor_node", END)

    return builder.compile()


__all__ = [
    "build_athena_graph",
    "chat_node",
    "pdf_tool_node",
    "route_selector",
    "router_node",
    "task_tool_node",
    "research_node",
    "session_node",
    "idea_extractor_node",
]
