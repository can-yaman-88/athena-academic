"""LangGraph workflow for Jarvis-Academic.

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
    ROUTER_SYSTEM_PROMPT,
    TASK_EXTRACTION_SYSTEM_PROMPT,
    WORKOUT_PLAN_SYSTEM_PROMPT,
    RouteDecision,
    TaskExtractionList,
    WorkoutPlan,
)
from core.schemas import (
    AcademicSubtype,
    Material,
    Note,
    PhysicalLoad,
    Task,
    TaskCategory,
    TaskStatus,
)
from core.state import JarvisState, RouteTarget
from core.tools import add_task, process_pdf

logger = logging.getLogger("jarvis.graph")

# Maps a routing target to the tool name a node will surface in active_tool.
_TOOL_FOR_ROUTE: dict[RouteTarget, Optional[str]] = {
    "chat_node": None,
    "pdf_tool_node": "process_pdf",
    "task_tool_node": "add_task",
    "workout_tool_node": "log_workout",
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
        default_headers={"X-Title": "Jarvis-Academic"},
    )
    if temperature is not None:
        kwargs["temperature"] = temperature
    if callbacks:
        kwargs["callbacks"] = callbacks
    return ChatOpenAI(**kwargs)


def _default_router_llm(callbacks: Optional[list] = None) -> Any:
    """Lightweight, deterministic router bound to the RouteDecision schema."""
    llm = _make_llm(
        settings.router_model, settings.router_max_tokens, temperature=0,
        callbacks=callbacks,
    )
    return llm.with_structured_output(RouteDecision, method="function_calling")


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
    return llm.with_structured_output(TaskExtractionList, method="function_calling")


def _default_workout_extractor_llm(callbacks: Optional[list] = None) -> Any:
    """Deterministic extractor bound to the WorkoutPlan schema."""
    llm = _make_llm(
        settings.router_model, settings.router_max_tokens, temperature=0,
        callbacks=callbacks,
    )
    return llm.with_structured_output(WorkoutPlan, method="function_calling")


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


def _resolve_deadline(value: Optional[str], now: datetime) -> datetime:
    """Turn the extractor's optional ISO deadline into a concrete datetime.

    Falls back to end-of-day today when the model gives no parseable deadline,
    so a Task (whose ``deadline`` is required) can always be constructed.
    """
    if value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            logger.warning("unparseable deadline %r; defaulting to end of today", value)
    return now.replace(
        hour=settings.default_deadline_hour,
        minute=settings.default_deadline_minute,
        second=0,
        microsecond=0,
    )


def _attachments_text(state: JarvisState) -> str:
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
    open_tasks = [t for t in tasks if t.parent_id is None]

    def _match(cands: list[Task]) -> Optional[Task]:
        if not cands:
            return None
        if target_hint:
            hint = target_hint.lower()
            hits = [t for t in cands if hint in t.title.lower()]
            if hits:
                return sorted(hits, key=lambda t: t.deadline)[0]
        return sorted(cands, key=lambda t: t.deadline)[0]

    if target_date is not None:
        return _match([t for t in open_tasks if t.deadline.date() == target_date])

    today = now.date()
    todays = [t for t in open_tasks if t.deadline.date() == today]
    hit = _match(todays)
    if hit:
        return hit
    future = [t for t in open_tasks if t.deadline >= now]
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

    cands = [t for t in tasks if t.parent_id is None]
    if not include_completed:
        cands = [t for t in cands if t.status != TaskStatus.COMPLETED]
    if target_date is not None:
        cands = [t for t in cands if t.deadline.date() == target_date]
    if not cands:
        return None
    name = (name or "").strip().lower()
    if not name:
        return sorted(cands, key=lambda t: t.deadline)[0]
    exact = [t for t in cands if name == t.title.lower() or name in t.title.lower()]
    if exact:
        return sorted(exact, key=lambda t: t.deadline)[0]
    titles = {t.title.lower(): t for t in cands}
    close = difflib.get_close_matches(name, list(titles), n=1, cutoff=0.3)
    return titles[close[0]] if close else None


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #
def router_node(state: JarvisState, *, router_llm: Any) -> dict[str, Any]:
    """Classify the latest message and record the routing decision.

    A leading slash command bypasses the LLM router entirely (deterministic).
    """
    user_text = _last_human_message(state["messages"])

    command, _remainder = parse_command(user_text)
    if command is not None:
        return {
            "route": command.route,
            "active_tool": _TOOL_FOR_ROUTE.get(command.route),
            "command": command.name,
        }

    decision: RouteDecision = router_llm.invoke(
        [
            SystemMessage(content=ROUTER_SYSTEM_PROMPT),
            HumanMessage(content=user_text),
        ]
    )
    return {
        "route": decision.next_node,
        "active_tool": _TOOL_FOR_ROUTE[decision.next_node],
        "cognitive_load_status": decision.cognitive_load_status,
        "command": None,
    }


def chat_node(
    state: JarvisState, *, chat_llm: Any, chroma: Any = None
) -> dict[str, Any]:
    """Answer conversationally, grounded in retrieved document context."""
    # /yardim is deterministic — list commands without an LLM call.
    if state.get("command") == "yardim":
        return {"messages": [AIMessage(content=help_text())], "active_tool": None}

    context = ""
    if chroma is not None:
        query = _last_human_message(state["messages"])
        if query:
            try:
                results = chroma.query_documents(query, n_results=3)
                context = "\n\n".join(
                    r["text"] for r in results if r.get("text")
                )
            except Exception:
                # Retrieval is best-effort; never let it break the chat turn.
                context = ""

    attach = _attachments_text(state)
    if attach:
        context = (context + "\n\n" if context else "") + "[Attached by user]\n" + attach[:6000]

    system = CHAT_SYSTEM_PROMPT.format(
        context=context or "(no relevant context found)"
    )
    response = chat_llm.invoke([SystemMessage(content=system), *state["messages"]])
    return {
        "messages": [response],
        "retrieved_context": context or None,
        "active_tool": None,
    }


def pdf_tool_node(state: JarvisState) -> dict[str, Any]:
    """Execute the (mocked) PDF processing tool."""
    user_text = _last_human_message(state["messages"])
    match = _PDF_PATH_RE.search(user_text)
    file_path = match.group(0) if match else "<unspecified>.pdf"
    result = process_pdf.invoke({"file_path": file_path})
    return {
        "messages": [AIMessage(content=result)],
        "active_tool": "process_pdf",
    }


def _materials_from_attachments(state: JarvisState) -> list[Material]:
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
    parent: Task, context_text: str, subtask_llm: Any, now: datetime
) -> list[Task]:
    """Break an academic task into independent subtask rows via the LLM."""
    from core.subtasks import SUBTASK_SYSTEM_PROMPT, SubtaskPlan  # local import

    payload = (
        f"Parent task: {parent.title}\nDiscipline: {parent.discipline}\n"
        f"Subtype: {parent.subtype.value if parent.subtype else 'n/a'}\n"
        f"Deadline: {parent.deadline.isoformat()}\n\n"
        f"Material/spec (may be empty):\n{context_text or '(none)'}"
    )
    plan: Optional[SubtaskPlan] = await subtask_llm.ainvoke(
        [
            SystemMessage(content=SUBTASK_SYSTEM_PROMPT.format(now=now.isoformat(timespec="minutes"))),
            HumanMessage(content=payload),
        ]
    )
    subs: list[Task] = []
    for item in (plan.subtasks if plan else []):
        deadline = _resolve_deadline(item.deadline, now)
        subs.append(
            Task(
                title=item.title,
                deadline=min(deadline, parent.deadline),
                discipline=parent.discipline,
                estimated_hours=item.estimated_hours or settings.default_estimated_hours,
                category=TaskCategory.ACADEMIC,
                subtype=parent.subtype,
                parent_id=parent.id,
            )
        )
    return subs


async def task_tool_node(
    state: JarvisState,
    *,
    task_extractor_llm: Any = None,
    sqlite_manager: Any = None,
    subtask_llm: Any = None,
) -> dict[str, Any]:
    """Create/update tasks (and notes) from chat, honoring slash-command hints."""
    user_text = _last_human_message(state["messages"])
    command, remainder = parse_command(user_text)
    hints = COMMANDS[command.name].hints if command else {}
    working_text = remainder if command else user_text

    if sqlite_manager is None or task_extractor_llm is None:
        result = add_task.invoke(
            {"title": working_text or "Untitled task", "deadline": "TBD",
             "discipline": "General", "estimated_hours": 1.0}
        )
        return {"messages": [AIMessage(content=result)], "active_tool": "add_task"}

    now = datetime.now()
    tasks = await sqlite_manager.list_tasks()

    # --- /not : attach a note to the resolved task ------------------------ #
    if hints.get("operation") == "note":
        hint, _, note_text = working_text.partition(":")
        if not note_text.strip():
            hint, note_text = "", working_text
        target = _resolve_target_task(tasks, hint.strip() or None, None, now)
        if target is None:
            return {"messages": [AIMessage(content="Not eklenecek bir görev bulamadım.")],
                    "active_tool": "add_task"}
        target.notes = [*target.notes, Note(text=note_text.strip())]
        await sqlite_manager.update_task(target)
        return {"messages": [AIMessage(content=f"'{target.title}' görevine not eklendi.")],
                "active_tool": "add_task", "current_task": target}

    # --- /complete, /sil, /ertele : act on an existing task by name ------- #
    mgmt_op = hints.get("operation")
    if mgmt_op in {"complete", "delete", "reschedule"}:
        target_date, rest = _extract_date_token(working_text, now)
        if mgmt_op == "reschedule":
            # The date token is the NEW deadline; the rest is the task name.
            target = _resolve_task_by_name(tasks, rest, None)
            if target is None:
                return {"messages": [AIMessage(content="Ertelenecek görevi bulamadım.")],
                        "active_tool": "add_task"}
            new_deadline = (
                datetime.combine(target_date, target.deadline.time())
                if target_date else _resolve_deadline(None, now)
            )
            target.deadline = new_deadline
            await sqlite_manager.update_task(target)
            return {"messages": [AIMessage(content=(
                f"'{target.title}' → {target.deadline.strftime('%Y-%m-%d %H:%M')} olarak ertelendi."))],
                "active_tool": "add_task", "current_task": target}

        target = _resolve_task_by_name(tasks, rest, target_date)
        if target is None:
            return {"messages": [AIMessage(content="Eşleşen görev bulamadım.")],
                    "active_tool": "add_task"}
        if mgmt_op == "complete":
            await sqlite_manager.mark_task_completed(target.id)
            return {"messages": [AIMessage(content=f"'{target.title}' tamamlandı olarak işaretlendi.")],
                    "active_tool": "add_task", "current_task": target}
        await sqlite_manager.delete_task(target.id)
        return {"messages": [AIMessage(content=f"'{target.title}' silindi.")],
                "active_tool": "add_task"}

    # --- extract task ops ------------------------------------------------- #
    default_deadline_time = (
        f"{settings.default_deadline_hour:02d}:{settings.default_deadline_minute:02d}"
    )
    attach_text = _attachments_text(state)
    extractor_input = working_text
    if attach_text:
        extractor_input += f"\n\n[Attached material]\n{attach_text[:6000]}"
    try:
        extraction: Optional[TaskExtractionList] = await task_extractor_llm.ainvoke(
            [
                SystemMessage(content=TASK_EXTRACTION_SYSTEM_PROMPT.format(
                    now=now.isoformat(timespec="minutes"),
                    default_deadline_time=default_deadline_time,
                    default_discipline=settings.default_discipline,
                    default_estimated_hours=settings.default_estimated_hours,
                )),
                HumanMessage(content=extractor_input),
            ]
        )
    except Exception as exc:
        logger.exception("task extraction failed")
        return {"messages": [AIMessage(content=f"Couldn't parse that into a task: {exc}")],
                "active_tool": "add_task"}

    ops = extraction.tasks if extraction is not None else []
    if not ops:
        return {"messages": [AIMessage(content=(
            "Net bir görev çıkaramadım. Örn: 'yarın 9'da 1 saat kalkülüs tekrarı ekle'."))],
            "active_tool": "add_task"}

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
        task = Task(
            title=op.title or (working_text or "Untitled task"),
            deadline=_resolve_deadline(op.deadline, now),
            discipline=op.discipline or settings.default_discipline,
            estimated_hours=op.estimated_hours or settings.default_estimated_hours,
            category=category,
            subtype=subtype,
            materials=materials if category == TaskCategory.ACADEMIC else [],
        )
        await sqlite_manager.create_task(task)
        created.append(task)
        logger.info("created task id=%s title=%s cat=%s", task.id, task.title, category.value)

        # auto-generate subtasks for academic tasks (best effort)
        if category == TaskCategory.ACADEMIC and subtask_llm is not None:
            try:
                subs = await _generate_subtasks(task, attach_text, subtask_llm, now)
                for s in subs:
                    await sqlite_manager.create_task(s)
                if subs:
                    logger.info("generated %d subtasks for %s", len(subs), task.title)
            except Exception:  # noqa: BLE001 - subtask gen must not fail the create
                logger.exception("subtask generation failed for %s", task.title)

    msgs: list[str] = []
    if created:
        msgs.append(
            ("1 görev oluşturuldu:" if len(created) == 1 else f"{len(created)} görev oluşturuldu:")
            + "\n" + "\n".join(
                f"- '{t.title}' ({t.category.value}"
                + (f"/{t.subtype.value}" if t.subtype else "")
                + f"), {t.deadline.strftime('%Y-%m-%d %H:%M')}, {t.estimated_hours:g}h"
                for t in created
            )
        )
    if updated:
        msgs.append(
            ("1 görev güncellendi:" if len(updated) == 1 else f"{len(updated)} görev güncellendi:")
            + "\n" + "\n".join(
                f"- '{t.title}', {t.deadline.strftime('%Y-%m-%d %H:%M')}, {t.estimated_hours:g}h"
                for t in updated
            )
        )
    focus = (created + updated)[-1]
    return {
        "messages": [AIMessage(content="\n\n".join(msgs))],
        "active_tool": "add_task",
        "current_task": focus,
    }


async def workout_tool_node(
    state: JarvisState,
    *,
    workout_extractor_llm: Any = None,
    sqlite_manager: Any = None,
) -> dict[str, Any]:
    """Log a single workout or import a multi-day plan (text or attachment)."""
    user_text = _last_human_message(state["messages"])
    command, remainder = parse_command(user_text)
    working_text = remainder if command else user_text

    if sqlite_manager is None or workout_extractor_llm is None:
        return {"messages": [AIMessage(content="[mock] workout tool not wired.")],
                "active_tool": "log_workout"}

    now = datetime.now()
    attach_text = _attachments_text(state)
    source = working_text + (f"\n\n[Attached plan]\n{attach_text[:8000]}" if attach_text else "")
    try:
        plan: Optional[WorkoutPlan] = await workout_extractor_llm.ainvoke(
            [
                SystemMessage(content=WORKOUT_PLAN_SYSTEM_PROMPT.format(
                    now=now.date().isoformat())),
                HumanMessage(content=source),
            ]
        )
    except Exception as exc:
        logger.exception("workout extraction failed")
        return {"messages": [AIMessage(content=f"Antrenmanı çözümleyemedim: {exc}")],
                "active_tool": "log_workout"}

    items = plan.workouts if plan else []
    if not items:
        return {"messages": [AIMessage(content="Eklenecek bir antrenman bulamadım.")],
                "active_tool": "log_workout"}

    saved = 0
    for it in items:
        try:
            d = date_type.fromisoformat(it.date) if it.date else now.date()
        except ValueError:
            d = now.date()
        load = PhysicalLoad(date=d, duration_minutes=it.duration_minutes, rpe_score=it.rpe_score)
        await sqlite_manager.create_physical_load(load)
        saved += 1

    return {
        "messages": [AIMessage(content=f"{saved} antrenman eklendi.")],
        "active_tool": "log_workout",
    }


def route_selector(state: JarvisState) -> RouteTarget:
    """Conditional-edge function: send the run to the router's chosen node."""
    return state.get("route") or "chat_node"


# --------------------------------------------------------------------------- #
# Graph assembly
# --------------------------------------------------------------------------- #
def build_jarvis_graph(
    *,
    router_llm: Any = None,
    chat_llm: Any = None,
    chroma_manager: Any = None,
    sqlite_manager: Any = None,
    task_extractor_llm: Any = None,
    workout_extractor_llm: Any = None,
    subtask_llm: Any = None,
    usage_callback: Any = None,
) -> Any:
    """Build and compile the Jarvis-Academic routing graph.

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
        if workout_extractor_llm is None:
            workout_extractor_llm = _default_workout_extractor_llm(callbacks)
        if subtask_llm is None:
            try:
                sub_base = _make_llm(
                    settings.notes_model, settings.notes_model_max_tokens,
                    callbacks=callbacks,
                )
                from core.subtasks import SubtaskPlan

                subtask_llm = sub_base.with_structured_output(
                    SubtaskPlan, method="function_calling"
                )
            except Exception:  # pragma: no cover - missing key/package
                subtask_llm = None

    builder = StateGraph(JarvisState)
    builder.add_node("router_node", partial(router_node, router_llm=router_llm))
    builder.add_node(
        "chat_node", partial(chat_node, chat_llm=chat_llm, chroma=chroma_manager)
    )
    builder.add_node("pdf_tool_node", pdf_tool_node)
    builder.add_node(
        "task_tool_node",
        partial(
            task_tool_node,
            task_extractor_llm=task_extractor_llm,
            sqlite_manager=sqlite_manager,
            subtask_llm=subtask_llm,
        ),
    )
    builder.add_node(
        "workout_tool_node",
        partial(
            workout_tool_node,
            workout_extractor_llm=workout_extractor_llm,
            sqlite_manager=sqlite_manager,
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
            "workout_tool_node": "workout_tool_node",
        },
    )
    builder.add_edge("chat_node", END)
    builder.add_edge("pdf_tool_node", END)
    builder.add_edge("task_tool_node", END)
    builder.add_edge("workout_tool_node", END)

    return builder.compile()


__all__ = [
    "build_jarvis_graph",
    "chat_node",
    "pdf_tool_node",
    "route_selector",
    "router_node",
    "task_tool_node",
    "workout_tool_node",
]
