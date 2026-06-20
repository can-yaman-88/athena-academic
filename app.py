"""FastAPI application for Athena-Academic.

Exposes the LangGraph agent (streaming chat), a PDF upload endpoint that runs the
in-process PDF->LaTeX engine in the background, task & workout CRUD, a PDF-job
history with artifact download, a two-category API cost meter, and a live log
stream. All shared components (agent graph, SQLite, ChromaDB, usage tracker, log
bus) are initialized once in the application lifespan and shared via ``app.state``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field, field_validator

from config import settings
from core.graph import build_athena_graph
from core.log_bus import LogBus, LogBusHandler
from core.note_analyzer import analyze_notes
from core.schemas import (
    AcademicSubtype,
    Idea,
    Material,
    Note,
    PhysicalLoad,
    Task,
    TaskCategory,
    TaskStatus,
    WorkoutStatus,
)
from core.usage_callback import AgentUsageCallback
from db.chroma_manager import ChromaManager
from db.exceptions import RecordNotFoundError
from db.sqlite_manager import SQLiteManager
from uuid import uuid4

from tools.pdf_engine import process_academic_pdf
from tools.pdf_engine.automation import AIClient, UsageTracker, build_engine_config
from tools.pdf_engine.wrapper import _extract_markdown

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("athena.api")


# --------------------------------------------------------------------------- #
# Lifespan: init shared resources once
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)

    # Live log bus: forward everything logged under "athena" to subscribers.
    log_bus = LogBus()
    log_bus.bind_loop(asyncio.get_running_loop())
    handler = LogBusHandler(log_bus)
    handler.setLevel(logging.INFO)
    logging.getLogger("athena").addHandler(handler)
    logging.getLogger("athena").setLevel(logging.INFO)
    app.state.log_bus = log_bus

    # Two-category cost meter (pdf vs agent), persisted to CSV.
    usage = UsageTracker(
        settings.usage_csv_path,
        pricing=settings.model_pricing,
        default_pricing=settings.default_model_pricing,
    )
    app.state.usage = usage

    sqlite = SQLiteManager()
    await sqlite.initialize()
    chroma = ChromaManager()
    await asyncio.to_thread(chroma.initialize)
    app.state.sqlite = sqlite
    app.state.chroma = chroma

    # Build the agent graph only when an OpenRouter key is available; otherwise
    # /chat reports 503 instead of crashing the whole app at startup.
    app.state.graph = None
    if os.environ.get(settings.openrouter_api_key_env):
        try:
            app.state.graph = build_athena_graph(
                chroma_manager=chroma,
                sqlite_manager=sqlite,
                usage_callback=AgentUsageCallback(usage),
            )
            logger.info("LangGraph agent ready")
        except Exception:  # pragma: no cover - defensive
            logger.exception("failed to build agent graph; /chat disabled")
    else:
        logger.warning(
            "%s not set; /chat is disabled until a key is provided",
            settings.openrouter_api_key_env,
        )

    # Background Runalyze auto-sync. The loop re-reads the token each cycle, so a
    # token added later (without a restart) still activates it.
    if _read_runalyze_token():
        logger.info(
            "Runalyze auto-sync enabled (every %d min)",
            settings.runalyze_sync_interval_min,
        )
    else:
        logger.info(
            "%s not set; Runalyze auto-sync idle until a token is provided",
            settings.runalyze_token_env,
        )
    app.state.runalyze_task = asyncio.create_task(_runalyze_sync_loop(app))

    try:
        yield
    finally:
        app.state.runalyze_task.cancel()
        try:
            await app.state.runalyze_task
        except asyncio.CancelledError:
            pass
        await sqlite.close()


app = FastAPI(title="Athena-Academic", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class Mention(BaseModel):
    """A reference the user explicitly picked in the chat box (@ or #).

    ``type`` is one of: task, subtask, workout, idea, model, tag. ``id`` is the
    object id (or the tag/model name). The backend resolves each to its real
    content so the model receives the actual referenced material, not just a label.
    """

    type: str
    id: str
    label: Optional[str] = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    attachment_ids: list[str] = Field(default_factory=list)
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    history: list[dict[str, str]] = Field(default_factory=list)
    mentions: list[Mention] = Field(default_factory=list)

class JournalRequest(BaseModel):
    date: str
    content: str

class DailyNoteRequest(BaseModel):
    date: Optional[str] = None
    content: str = ""

class JournalAnalyzeRequest(BaseModel):
    journal_ids: list[str]


class IdeaCreateRequest(BaseModel):
    title: str = ""
    content: str = ""


class IdeaUpdateRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


def _blank_deadline_to_none(value: Any) -> Any:
    """Treat an empty/whitespace deadline string as 'no deadline' (None).

    The frontend's datetime-local input yields "" when the user clears the
    field; without this a bare "" would fail datetime parsing (422). An omitted
    date must always mean a null deadline.
    """
    if isinstance(value, str) and not value.strip():
        return None
    return value


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    deadline: Optional[datetime] = None
    discipline: Optional[str] = None
    estimated_hours: float = Field(
        default_factory=lambda: settings.default_estimated_hours, gt=0
    )
    category: TaskCategory = TaskCategory.DAILY
    subtype: Optional[AcademicSubtype] = None
    parent_id: Optional[str] = None
    status: Optional[TaskStatus] = None

    _normalize_deadline = field_validator("deadline", mode="before")(
        _blank_deadline_to_none
    )


class TaskUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1)
    deadline: Optional[datetime] = None
    discipline: Optional[str] = Field(default=None, min_length=1)
    estimated_hours: Optional[float] = Field(default=None, gt=0)
    status: Optional[TaskStatus] = None
    category: Optional[TaskCategory] = None
    subtype: Optional[AcademicSubtype] = None
    progress: Optional[int] = Field(default=None, ge=0, le=100)

    _normalize_deadline = field_validator("deadline", mode="before")(
        _blank_deadline_to_none
    )


class NoteCreateRequest(BaseModel):
    text: str = Field(min_length=1)


class NoteUpdateRequest(BaseModel):
    text: str = Field(min_length=1)


class MaterialCreateRequest(BaseModel):
    kind: str = Field(default="link")
    name: str = Field(min_length=1)
    source: str = Field(min_length=1)


class WorkoutRequest(BaseModel):
    duration_minutes: int = Field(gt=0)
    rpe_score: Optional[int] = Field(default=None, ge=1, le=10)
    date: Optional[date] = None
    status: WorkoutStatus = WorkoutStatus.COMPLETED
    title: Optional[str] = None
    distance_km: Optional[float] = Field(default=None, ge=0)
    pace: Optional[str] = None
    avg_speed_kmh: Optional[float] = Field(default=None, ge=0)
    avg_hr: Optional[int] = Field(default=None, ge=0, le=260)
    note: Optional[str] = None


class WorkoutUpdateRequest(BaseModel):
    duration_minutes: Optional[int] = Field(default=None, gt=0)
    rpe_score: Optional[int] = Field(default=None, ge=1, le=10)
    date: Optional[date] = None
    status: Optional[WorkoutStatus] = None
    title: Optional[str] = None
    distance_km: Optional[float] = Field(default=None, ge=0)
    pace: Optional[str] = None
    avg_speed_kmh: Optional[float] = Field(default=None, ge=0)
    avg_hr: Optional[int] = Field(default=None, ge=0, le=260)
    note: Optional[str] = None


def _sse(payload: dict[str, Any]) -> str:
    """Format a dict as a Server-Sent Events data frame."""
    return f"data: {json.dumps(payload)}\n\n"


def _strip_html(text: str) -> str:
    """Reduce rich-text (HTML) note bodies to plain text for the analyzer LLM."""
    import re

    plain = re.sub(r"<[^>]+>", " ", text or "")
    plain = plain.replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", plain).strip()


# --------------------------------------------------------------------------- #
# Health + chat
# --------------------------------------------------------------------------- #
@app.get("/models")
async def list_models() -> dict[str, list[str]]:
    """Return the available model keys from settings."""
    return {"models": list(settings.available_models.keys())}


@app.get("/health")
async def health(request: Request) -> dict[str, Any]:
    """Liveness probe; reports whether the agent graph is available."""
    return {"status": "ok", "graph_ready": request.app.state.graph is not None}


@app.get("/tags")
async def list_tags(request: Request) -> list[str]:
    """Return merged set of task tags and hashtag-like tokens from journal content."""
    db: SQLiteManager = request.app.state.sqlite
    tasks = await db.list_tasks()
    tags: set[str] = set()
    for t in tasks:
        tags.update(t.tags or [])
    # Also include hashtags found in journal bodies.
    import re
    journals = await db.get_journals()
    for j in journals:
        for match in re.finditer(r"#([\w\p{L}\p{N}_-]+)", j.content, re.UNICODE):
            tags.add(match.group(1))
    return sorted(tags)


async def _resolve_message_mentions(message: str, db: SQLiteManager) -> str:
    """Replace @ and # tokens with their real content before sending to the LLM.

    Handles:
    - @model-name -> model slug note
    - @task-title / @task-id / quoted task title -> full task dump (notes, subtasks)
    - @workout-title / @workout-id -> workout details
    - #tag -> short note that tag usage means task/journal context
    """
    import re

    out = message

    # Models: map friendly display name to slug via settings.available_models.
    def replace_model(m: re.Match[str]) -> str:
        key = m.group(1).strip()
        for friendly, slug in settings.available_models.items():
            if friendly.lower() == key.lower():
                return f"[Model: {friendly} -> {slug}]"
        return m.group(0)

    out = re.sub(r"@([\w.-]+)\b", replace_model, out)

    # Tasks: resolve by ID if the token is a UUID-like id (length >= 10 and has hexdigits),
    # otherwise resolve by title substring / fuzzy match.
    async def task_dump(tid_or_title: str) -> str:
        tid_or_title_stripped = tid_or_title.strip().strip('"').strip("'")
        try:
            all_tasks = await db.list_tasks()
        except Exception:
            return "[görev bulunamadı]"

        # Direct id match?
        target = next((t for t in all_tasks if t.id == tid_or_title_stripped), None)
        if target is None:
            target = next(
                (
                    t
                    for t in all_tasks
                    if tid_or_title_stripped.lower() in t.title.lower()
                ),
                None,
            )
        if target is None:
            return "[görev bulunamadı]"

        parts = [
            f"Görev: {target.title}",
            f"Son tarih: {target.deadline.isoformat() if target.deadline else 'tarihsiz'}",
            f"Alan: {target.discipline}",
            f"Tahmini süre: {target.estimated_hours}h",
            f"Kategori: {target.category.value}",
            f"Durum: {target.status.value}",
            f"İlerleme: %{target.progress}",
        ]
        if target.tags:
            parts.append(f"Etiketler: {', '.join(target.tags)}")
        if target.notes:
            parts.append("Notlar:\n" + "\n".join(f"- {n.text}" for n in target.notes))
        subtasks = [t for t in all_tasks if t.parent_id == target.id]
        if subtasks:
            parts.append(
                "Alt görevler:\n"
                + "\n".join(
                    f"- {s.title} ({s.deadline.isoformat() if s.deadline else 'tarihsiz'})"
                    for s in subtasks
                )
            )
        return "\n".join(parts)

    # Match both @"title with spaces" and @simple_token
    task_pattern = re.compile(r'@"([^"]+)"|@([^\s]+)')

    async def replace_task(m: re.Match[str]) -> str:
        token = m.group(1) if m.group(1) is not None else m.group(2)
        return await task_dump(token)

    # We need to await inside an async helper; run substitution sequentially.
    async def resolve_tasks(text: str) -> str:
        result = []
        last = 0
        for m in task_pattern.finditer(text):
            result.append(text[last : m.start()])
            result.append(await replace_task(m))
            last = m.end()
        result.append(text[last:])
        return "".join(result)

    # Workouts: similar to tasks but simpler.
    async def workout_dump(token: str) -> str:
        token = token.strip().strip('"').strip("'")
        try:
            workouts = await db.list_physical_loads()
        except Exception:
            return "[antrenman bulunamadı]"
        target = next(
            (w for w in workouts if w.id == token or (w.title and token.lower() in w.title.lower())),
            None,
        )
        if target is None:
            return "[antrenman bulunamadı]"
        return (
            f"Antrenman: {target.title or target.date}\n"
            f"Tarih: {target.date}\n"
            f"Süre: {target.duration_minutes} dk\n"
            f"Durum: {target.status.value}"
            + (f"\nMesafe: {target.distance_km} km" if target.distance_km else "")
            + (f"\nTempo: {target.pace}/km" if target.pace else "")
            + (f"\nRPE: {target.rpe_score}" if target.rpe_score else "")
        )

    workout_pattern = re.compile(r'@"([^"]+)"|@([^\s]+)')

    async def resolve_workouts(text: str) -> str:
        result = []
        last = 0
        for m in workout_pattern.finditer(text):
            token = m.group(1) if m.group(1) is not None else m.group(2)
            # Skip tokens that were already replaced as models above.
            # Model replacements all start with '[Model:'.
            if text[m.start() : m.end()].startswith("@[") and "[Model:" in text[m.start() : m.end()]:
                result.append(text[last:m.start()])
                result.append("[Model zaten çözümlendi]")
                last = m.end()
                continue
            result.append(text[last:m.start()])
            result.append(await workout_dump(token))
            last = m.end()
        result.append(text[last:])
        return "".join(result)

    out = await resolve_tasks(out)

    # Tag hints: keep them visible but add a context note.
    def replace_tag(m: re.Match) -> str:
        return f"[{m.group(0)}]"

    out = re.sub(r"#([\w-]+)", replace_tag, out)
    return out


def _task_context_block(target: Task, all_tasks: list[Task]) -> str:
    """Full human-readable dump of a task incl. notes, materials and subtasks."""
    import re as _re

    def _plain(html: str) -> str:
        return _re.sub(r"<[^>]+>", " ", html or "").replace("&nbsp;", " ").strip()

    parts = [
        f"Görev: {target.title}",
        f"Son tarih: {target.deadline.isoformat() if target.deadline else 'tarihsiz'}",
        f"Alan: {target.discipline}",
        f"Tahmini süre: {target.estimated_hours}h",
        f"Kategori: {target.category.value}",
        f"Durum: {target.status.value}",
        f"İlerleme: %{target.progress}",
    ]
    if target.tags:
        parts.append(f"Etiketler: {', '.join(target.tags)}")
    if target.notes:
        parts.append("Notlar:\n" + "\n".join(f"- {_plain(n.text)}" for n in target.notes))
    if target.materials:
        parts.append(
            "Materyaller:\n"
            + "\n".join(
                f"- {m.name}" + (f" ({m.source})" if m.source else "")
                for m in target.materials
            )
        )
    subtasks = [t for t in all_tasks if t.parent_id == target.id]
    if subtasks:
        parts.append(
            "Alt görevler:\n"
            + "\n".join(
                f"- {s.title} (%{s.progress}, {s.status.value})" for s in subtasks
            )
        )
    return "\n".join(parts)


def _workout_context_block(target: PhysicalLoad) -> str:
    lines = [
        f"Antrenman: {target.title or target.date}",
        f"Tarih: {target.date}",
        f"Süre: {target.duration_minutes} dk",
        f"Durum: {target.status.value}",
    ]
    if target.distance_km:
        lines.append(f"Mesafe: {target.distance_km} km")
    if target.pace:
        lines.append(f"Tempo: {target.pace}/km")
    if target.avg_hr:
        lines.append(f"Ort. nabız: {target.avg_hr} bpm")
    if target.rpe_score:
        lines.append(f"RPE: {target.rpe_score}")
    if target.note:
        import re as _re
        lines.append("Not: " + _re.sub(r"<[^>]+>", " ", target.note).strip())
    return "\n".join(lines)


async def _resolve_structured_mentions(
    mentions: list["Mention"], db: SQLiteManager
) -> str:
    """Turn explicitly-picked @/# mentions into a real-content context block.

    Unlike the regex text resolver this is unambiguous: each mention carries the
    object id and type the user actually selected, so multi-word titles, subtasks,
    workouts and ideas all resolve to their full content.
    """
    if not mentions:
        return ""

    all_tasks: Optional[list[Task]] = None
    workouts: Optional[list[PhysicalLoad]] = None
    blocks: list[str] = []

    for m in mentions:
        kind = (m.type or "").lower()
        try:
            if kind in ("task", "subtask", "görev", "alt görev"):
                if all_tasks is None:
                    all_tasks = await db.list_tasks()
                target = next((t for t in all_tasks if t.id == m.id), None)
                if target:
                    blocks.append(_task_context_block(target, all_tasks))
            elif kind in ("workout", "antrenman"):
                if workouts is None:
                    workouts = await db.list_physical_loads()
                target = next((w for w in workouts if w.id == m.id), None)
                if target:
                    blocks.append(_workout_context_block(target))
            elif kind in ("idea", "fikir"):
                get_idea = getattr(db, "get_idea", None)
                if get_idea is not None:
                    try:
                        idea = await get_idea(m.id)
                        import re as _re
                        body = _re.sub(r"<[^>]+>", " ", idea.content or "").strip()
                        blocks.append(f"Fikir: {idea.title}\n{body}")
                    except Exception:
                        pass
            elif kind in ("model",):
                slug = settings.available_models.get(m.id, m.id)
                blocks.append(f"[Model talebi: {m.id} -> {slug}]")
            elif kind in ("tag", "etiket"):
                blocks.append(f"[Etiket bağlamı: #{m.id}]")
        except Exception:  # noqa: BLE001 - never break chat on a bad mention
            logger.exception("failed to resolve mention %s/%s", m.type, m.id)

    if not blocks:
        return ""
    return (
        "## Bağlam — kullanıcının bahsettiği öğeler\n"
        "(Aşağıdaki içerik kullanıcının @/# ile işaret ettiği gerçek verilerdir.)\n\n"
        + "\n\n".join(blocks)
    )


@app.post("/chat")
async def chat(request: Request, body: ChatRequest) -> StreamingResponse:
    """Stream the LangGraph agent's output for a user message as SSE.

    @/# mentions in the message are resolved against the local database so that
    the model receives the real referenced content.
    """
    graph = request.app.state.graph
    if graph is None:
        raise HTTPException(
            status_code=503,
            detail=f"Agent unavailable: {settings.openrouter_api_key_env} is not set.",
        )

    db: SQLiteManager = request.app.state.sqlite
    attachments: list[dict[str, Any]] = []
    for mid in body.attachment_ids:
        mat = await db.get_chat_material(mid)
        if mat:
            attachments.append(
                {"name": mat["name"], "markdown": mat["markdown"],
                 "path": mat["source_path"], "markdown_path": None}
            )

    # Prefer the explicit structured mentions the user picked in the UI (robust:
    # carries ids/types). Fall back to the regex text resolver for typed mentions.
    structured_ctx = await _resolve_structured_mentions(body.mentions, db)
    if structured_ctx:
        resolved_message = f"{structured_ctx}\n\n---\n\n{body.message}"
    else:
        resolved_message = await _resolve_message_mentions(body.message, db)

    async def event_stream() -> AsyncIterator[str]:
        from langchain_core.messages import AIMessage, SystemMessage
        history_msgs = []
        if body.system_prompt:
            history_msgs.append(SystemMessage(content=body.system_prompt))
            
        for h in body.history[-10:]:  # Keep last 10 messages for context
            if h.get("role") == "user":
                history_msgs.append(HumanMessage(content=h.get("text", "")))
            elif h.get("role") == "agent":
                history_msgs.append(AIMessage(content=h.get("text", "")))
        
        override_slug = body.model
        if override_slug:
            override_slug = settings.available_models.get(override_slug, override_slug)

        state = {
            "messages": history_msgs + [HumanMessage(content=resolved_message)],
            "attachments": attachments,
            "model_override": override_slug,
        }
        try:
            async for update in graph.astream(state, stream_mode="updates"):
                for node, partial in update.items():
                    if not isinstance(partial, dict):
                        continue
                    for msg in partial.get("messages", []) or []:
                        content = getattr(msg, "content", "")
                        if content:
                            yield _sse(
                                {"type": "message", "node": node, "content": content}
                            )
                    if partial.get("active_tool"):
                        yield _sse(
                            {"type": "tool", "active_tool": partial["active_tool"]}
                        )
            yield _sse({"type": "done"})
        except Exception as exc:  # pragma: no cover - surfaced to client
            logger.exception("chat stream failed")
            yield _sse({"type": "error", "error": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
_TEXT_EXTS = {".md", ".markdown", ".txt", ".json"}


async def _extract_upload_markdown(path: Path, usage: Any) -> tuple[str, str]:
    """Return (kind, markdown) for a chat-attached file.

    PDFs are always converted to Markdown (pymupdf4llm). Images go through the
    vision model. Text/MD/JSON are used as-is. Failures degrade to a short note
    rather than raising.
    """
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            md, _ = await asyncio.to_thread(_extract_markdown, path)
            return "pdf", md or "(PDF had no extractable text layer.)"
        except Exception:  # noqa: BLE001
            logger.exception("PDF markdown extraction failed")
            return "pdf", "(PDF could not be parsed.)"
    if suffix in _IMAGE_EXTS:
        try:
            from PIL import Image

            cfg = build_engine_config()
            image = await asyncio.to_thread(Image.open, str(path))
            async with AIClient(cfg, usage) as ai:
                md = await ai.describe_image_markdown(image, path.name)
            return "image", md
        except Exception as exc:  # noqa: BLE001 - needs key/network
            logger.exception("image transcription failed")
            return "image", f"(Image not transcribed: {exc})"
    if suffix in _TEXT_EXTS:
        try:
            return "file", await asyncio.to_thread(
                path.read_text, encoding="utf-8", errors="replace"
            )
        except Exception:  # noqa: BLE001
            return "file", ""
    return "file", ""


@app.post("/chat/upload")
async def chat_upload(
    request: Request, file: UploadFile = File(...)
) -> dict[str, Any]:
    """Accept a chat attachment (PDF/image/text), convert to Markdown, persist it."""
    db: SQLiteManager = request.app.state.sqlite
    filename = Path(file.filename or "attachment").name
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.uploads_dir / f"{uuid4().hex}_{filename}"
    content = await file.read()
    await asyncio.to_thread(dest.write_bytes, content)

    kind, markdown = await _extract_upload_markdown(dest, request.app.state.usage)
    material_id = uuid4().hex
    await db.create_chat_material(
        id=material_id, name=filename, kind=kind, source_path=str(dest),
        markdown=markdown,
    )
    logger.info("Yeni eklenti yüklendi: %s (%s)", filename, kind)
    preview = markdown[:500]
    return {
        "id": material_id,
        "name": filename,
        "kind": kind,
        "markdown_preview": preview,
        "chars": len(markdown),
    }


# --------------------------------------------------------------------------- #
# PDF upload + jobs
# --------------------------------------------------------------------------- #
@app.post("/upload")
async def upload(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    instructions: str = Form(""),
    processing_instructions: Optional[str] = Form(None),
) -> dict[str, Any]:
    """Save an uploaded PDF and run the in-process engine in the background."""
    instructions = instructions or processing_instructions or ""
    filename = Path(file.filename or "upload.pdf").name  # strip any path traversal
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.uploads_dir / filename

    content = await file.read()
    await asyncio.to_thread(dest.write_bytes, content)

    # Pre-generate the job id so the caller can correlate this upload with its
    # row in /pdf_jobs immediately (the background task persists under this id).
    job_id = str(uuid4())
    background_tasks.add_task(
        process_academic_pdf,
        str(dest),
        instructions,
        chroma_manager=request.app.state.chroma,
        usage_tracker=request.app.state.usage,
        log_bus=request.app.state.log_bus,
        sqlite_manager=request.app.state.sqlite,
        job_id=job_id,
    )
    logger.info(
        "Yeni PDF İşlenmek Üzere Sıraya Alındı: %s (%d bytes)", filename, len(content)
    )
    return {
        "status": "accepted",
        "job_id": job_id,
        "filename": filename,
        "message": "PDF saved and queued for processing.",
    }


@app.get("/pdf_jobs")
async def pdf_jobs(request: Request, limit: int = 100) -> dict[str, Any]:
    """List past PDF jobs (most recent first) for the automation page."""
    db: SQLiteManager = request.app.state.sqlite
    jobs = await db.list_pdf_jobs(limit=limit)
    return {"jobs": [j.model_dump(mode="json") for j in jobs]}


@app.get("/pdf_jobs/{job_id}/artifact/{name}")
async def pdf_job_artifact(request: Request, job_id: str, name: str) -> FileResponse:
    """Download a single artifact produced by a PDF job (by file name)."""
    db: SQLiteManager = request.app.state.sqlite
    try:
        job = await db.get_pdf_job(job_id)
    except RecordNotFoundError:
        raise HTTPException(status_code=404, detail="PDF job not found")
    # Only serve files actually recorded on the job (prevents path traversal).
    match = next((a for a in job.artifacts if Path(a).name == name), None)
    if match is None or not Path(match).exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(match, filename=name)


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
@app.get("/dashboard_data")
async def dashboard_data(request: Request) -> dict[str, Any]:
    """Return current tasks and the pending count."""
    db: SQLiteManager = request.app.state.sqlite
    tasks = await db.list_tasks()
    pending_count = len(db.get_pending_tasks())
    return {
        "tasks": [t.model_dump(mode="json") for t in tasks],
        "pending_count": pending_count,
    }


# --------------------------------------------------------------------------- #
# Task CRUD
# --------------------------------------------------------------------------- #
@app.get("/tasks")
async def list_tasks(
    request: Request,
    status: Optional[TaskStatus] = None,
    category: Optional[TaskCategory] = None,
) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    tasks = await db.list_tasks(status)
    if category is not None:
        tasks = [t for t in tasks if t.category == category]
    return {"tasks": [t.model_dump(mode="json") for t in tasks]}


@app.post("/tasks", status_code=201)
async def create_task(request: Request, body: TaskCreateRequest) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    task = Task(
        title=body.title,
        deadline=body.deadline,
        discipline=body.discipline or settings.default_discipline,
        estimated_hours=body.estimated_hours,
        category=body.category,
        subtype=body.subtype if body.category == TaskCategory.ACADEMIC else None,
        parent_id=body.parent_id,
        status=body.status or TaskStatus.PENDING,
    )
    await db.create_task(task)
    return task.model_dump(mode="json")


@app.get("/tasks/{task_id}/subtasks")
async def list_subtasks(request: Request, task_id: str) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    subs = await db.list_subtasks(task_id)
    return {"subtasks": [s.model_dump(mode="json") for s in subs]}


@app.patch("/tasks/{task_id}")
async def update_task(request: Request, task_id: str, body: TaskUpdateRequest) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    try:
        task = await db.get_task(task_id)
    except RecordNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")
    updates = body.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(task, field_name, value)
    await db.update_task(task)
    return task.model_dump(mode="json")


@app.post("/tasks/{task_id}/complete")
async def complete_task(request: Request, task_id: str, background_tasks: BackgroundTasks) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    try:
        task = await db.mark_task_completed(task_id)
        
        if task.is_spaced_repetition:
            from core.spaced_repetition import handle_spaced_repetition_completion
            usage = getattr(request.app.state, "usage", None)
            log_bus = getattr(request.app.state, "log_bus", None)
            background_tasks.add_task(
                handle_spaced_repetition_completion,
                task,
                db,
                usage,
                log_bus
            )
            
    except RecordNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.model_dump(mode="json")


@app.delete("/tasks/{task_id}")
async def delete_task(request: Request, task_id: str) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    try:
        await db.delete_task(task_id)
    except RecordNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "deleted", "id": task_id}


# --------------------------------------------------------------------------- #
# Task notes + materials
# --------------------------------------------------------------------------- #
async def _get_task_or_404(db: SQLiteManager, task_id: str) -> Task:
    try:
        return await db.get_task(task_id)
    except RecordNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")


@app.post("/tasks/{task_id}/notes")
async def add_note(request: Request, task_id: str, body: NoteCreateRequest) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    task = await _get_task_or_404(db, task_id)
    note = Note(text=body.text)
    task.notes = [*task.notes, note]
    await db.update_task(task)
    return task.model_dump(mode="json")


@app.patch("/tasks/{task_id}/notes/{note_id}")
async def edit_note(
    request: Request, task_id: str, note_id: str, body: NoteUpdateRequest
) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    task = await _get_task_or_404(db, task_id)
    found = False
    for n in task.notes:
        if n.id == note_id:
            n.text = body.text
            found = True
    if not found:
        raise HTTPException(status_code=404, detail="Note not found")
    task.notes = list(task.notes)  # trigger assignment validation
    await db.update_task(task)
    return task.model_dump(mode="json")


@app.delete("/tasks/{task_id}/notes/{note_id}")
async def delete_note(request: Request, task_id: str, note_id: str) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    task = await _get_task_or_404(db, task_id)
    task.notes = [n for n in task.notes if n.id != note_id]
    await db.update_task(task)
    return task.model_dump(mode="json")


@app.post("/tasks/{task_id}/materials")
async def add_material(
    request: Request, task_id: str, body: MaterialCreateRequest
) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    task = await _get_task_or_404(db, task_id)
    task.materials = [
        *task.materials,
        Material(kind=body.kind, name=body.name, source=body.source),
    ]
    await db.update_task(task)
    return task.model_dump(mode="json")


@app.post("/tasks/{task_id}/files")
async def upload_task_file(
    request: Request, task_id: str, file: UploadFile = File(...)
) -> dict[str, Any]:
    """Attach a RAW file to a task — stored untouched and NEVER sent to the AI.

    Unlike chat uploads (which are converted to Markdown and fed to the model),
    these are pure references the user keeps alongside the task; only the file
    *name* is ever used elsewhere (e.g. subtask generation context).
    """
    db: SQLiteManager = request.app.state.sqlite
    task = await _get_task_or_404(db, task_id)
    filename = Path(file.filename or "file").name
    dest_dir = settings.data_dir / "task_files" / task_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    material = Material(kind="file", name=filename, source=filename)
    dest = dest_dir / f"{material.id}_{filename}"
    content = await file.read()
    await asyncio.to_thread(dest.write_bytes, content)
    material.source = str(dest)
    task.materials = [*task.materials, material]
    await db.update_task(task)
    return task.model_dump(mode="json")


@app.get("/tasks/{task_id}/materials/{material_id}/download")
async def download_task_file(
    request: Request, task_id: str, material_id: str
) -> FileResponse:
    """Download a raw file attached to a task."""
    db: SQLiteManager = request.app.state.sqlite
    task = await _get_task_or_404(db, task_id)
    mat = next((m for m in task.materials if m.id == material_id), None)
    if mat is None or mat.kind != "file" or not mat.source or not Path(mat.source).exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(mat.source, filename=mat.name)


@app.post("/tasks/{task_id}/generate_subtasks")
async def generate_subtasks(request: Request, task_id: str) -> dict[str, Any]:
    """Use the high-capacity model to break an academic task into subtasks."""
    db: SQLiteManager = request.app.state.sqlite
    parent = await _get_task_or_404(db, task_id)
    from core.graph import _generate_subtasks, _make_llm, _make_structured_llm
    from core.subtasks import SubtaskPlan

    try:
        base = _make_llm(
            settings.notes_model, settings.notes_model_max_tokens,
            callbacks=[AgentUsageCallback(request.app.state.usage)],
        )
        sub_llm = _make_structured_llm(base, SubtaskPlan)
    except Exception as exc:  # noqa: BLE001 - no key/package
        raise HTTPException(status_code=503, detail=f"Subtask model unavailable: {exc}")

    context = "\n\n".join(
        m.name for m in parent.materials
    )  # material text is referenced; titles ground the breakdown
    subs = await _generate_subtasks(parent, context, sub_llm, datetime.now())
    for s in subs:
        await db.create_task(s)
    return {"created": len(subs), "subtasks": [s.model_dump(mode="json") for s in subs]}


@app.post("/notes/analyze")
async def analyze_all_notes(request: Request) -> dict[str, Any]:
    """Send every task's notes to the high-capacity model and apply extracted metrics."""
    db: SQLiteManager = request.app.state.sqlite
    usage = request.app.state.usage
    tasks = await db.list_tasks()
    payload = [
        {
            "id": t.id,
            "title": t.title,
            "category": t.category.value,
            "subtype": t.subtype.value if t.subtype else None,
            "progress": t.progress,
            "notes": [_strip_html(n.text) for n in t.notes],
        }
        for t in tasks
        if t.notes
    ]
    if not payload:
        return {"task_progress_updates": 0, "message": "No notes to analyze."}

    # Tests can inject a fake structured-output runnable on app.state.notes_llm.
    injected = getattr(request.app.state, "notes_llm", None)
    try:
        analysis = await analyze_notes(
            payload, llm=injected, callbacks=[AgentUsageCallback(usage)]
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the client
        logger.exception("note analysis failed")
        raise HTTPException(status_code=503, detail=f"Note analysis failed: {exc}")

    valid_ids = {t.id for t in tasks}
    applied_progress = 0
    for upd in analysis.task_progress_updates:
        if upd.task_id not in valid_ids:
            continue
        t = await db.get_task(upd.task_id)
        t.progress = upd.progress
        if upd.progress >= 100:
            t.status = TaskStatus.COMPLETED
        await db.update_task(t)
        applied_progress += 1

    return {"task_progress_updates": applied_progress}


# --------------------------------------------------------------------------- #
# Workout (PhysicalLoad) CRUD
# --------------------------------------------------------------------------- #
@app.get("/workouts")
async def list_workouts(request: Request) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    loads = await db.list_physical_loads()
    return {"workouts": [load.model_dump(mode="json") for load in loads]}


@app.post("/workouts")
async def create_workout(request: Request, body: WorkoutRequest) -> dict[str, Any]:
    """Record a workout with its (optional) metrics."""
    db: SQLiteManager = request.app.state.sqlite
    load = PhysicalLoad(
        date=body.date or date.today(),
        duration_minutes=body.duration_minutes,
        rpe_score=body.rpe_score,
        status=body.status,
        title=body.title,
        distance_km=body.distance_km,
        pace=body.pace,
        avg_speed_kmh=body.avg_speed_kmh,
        avg_hr=body.avg_hr,
        note=body.note,
    )
    await db.create_physical_load(load)
    return {"physical_load": load.model_dump(mode="json")}


@app.post("/workouts/{load_id}/complete")
async def complete_workout(request: Request, load_id: str) -> dict[str, Any]:
    """Mark a planned workout as completed (it becomes a recorded actual)."""
    db: SQLiteManager = request.app.state.sqlite
    try:
        load = await db.get_physical_load(load_id)
    except RecordNotFoundError:
        raise HTTPException(status_code=404, detail="Workout not found")
    load.status = WorkoutStatus.COMPLETED
    await db.update_physical_load(load)
    return load.model_dump(mode="json")


@app.post("/workouts/upload")
async def upload_workouts(
    request: Request, file: UploadFile = File(...)
) -> dict[str, Any]:
    """Import workout data (JSON/CSV/.FIT) as completed (actual) sessions."""
    from tools.workout_import import parse_workouts

    db: SQLiteManager = request.app.state.sqlite
    filename = Path(file.filename or "workouts").name
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.uploads_dir / f"{uuid4().hex}_{filename}"
    content = await file.read()
    await asyncio.to_thread(dest.write_bytes, content)

    # Files with an unknown/missing extension but JSON content (e.g. uploads sent
    # as application/octet-stream) are still parsed as JSON rather than rejected.
    if dest.suffix.lower() not in (".json", ".csv", ".fit"):
        if content.lstrip()[:1] in (b"[", b"{"):
            dest = dest.with_suffix(dest.suffix + ".json")
            await asyncio.to_thread(dest.write_bytes, content)

    try:
        records = await asyncio.to_thread(parse_workouts, dest)
    except Exception as exc:  # noqa: BLE001
        logger.exception("workout import failed")
        raise HTTPException(status_code=400, detail=f"Could not parse file: {exc}")

    created = []
    for rec in records:
        load = PhysicalLoad(
            date=date.fromisoformat(rec["date"]),
            duration_minutes=rec["duration_minutes"],
            rpe_score=rec.get("rpe_score"),
            status=WorkoutStatus.COMPLETED,
            title=rec.get("title"),
            distance_km=rec.get("distance_km"),
            pace=rec.get("pace"),
            avg_speed_kmh=rec.get("avg_speed_kmh"),
            avg_hr=rec.get("avg_hr"),
        )
        await db.create_physical_load(load)
        created.append(load.model_dump(mode="json"))
    return {"imported": len(created), "workouts": created}


def _read_runalyze_token() -> Optional[str]:
    """Read the Runalyze personal-API token from the env, falling back to .env.

    In Docker the token arrives via the ``environment:`` block; the ``.env``
    fallback covers bare ``uvicorn`` runs where python-dotenv isn't installed.
    """
    token = os.environ.get(settings.runalyze_token_env)
    if token and token.strip():
        return token.strip()
    env_file = settings.base_dir / ".env"
    if env_file.exists():
        prefix = f"{settings.runalyze_token_env}="
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith(prefix):
                return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def _runalyze_activity_to_load(act: dict[str, Any]) -> Optional[PhysicalLoad]:
    """Map one Runalyze activity dict to a completed ``PhysicalLoad`` (or None).

    The Runalyze Personal API returns activities as a flat JSON list. Relevant
    fields: ``date_time`` (ISO; NOT ``time``), ``duration``/``elapsed_time``
    (seconds), ``distance`` (km), ``hr_avg``, ``rpe`` (0 when unset), ``trimp``,
    ``title``, and ``sport``/``type`` objects each carrying a ``name``.
    """
    act_id = act.get("id")
    date_raw = act.get("date_time") or act.get("time")
    if not act_id or not date_raw:
        return None
    try:
        day = date.fromisoformat(str(date_raw).split("T")[0])
    except ValueError:
        return None

    seconds = act.get("duration") or act.get("elapsed_time") or 0
    duration_min = max(1, round(seconds / 60))

    # RPE is stored only when Runalyze actually reports it — no fabricated
    # difficulty (cognitive-load scoring was removed). Clamp a real value to 1-10.
    raw_rpe = act.get("rpe")
    rpe = max(1, min(10, int(raw_rpe))) if raw_rpe else None

    sport = act.get("sport") if isinstance(act.get("sport"), dict) else {}
    typ = act.get("type") if isinstance(act.get("type"), dict) else {}
    title = act.get("title") or sport.get("name") or typ.get("name") or "Runalyze"

    distance = act.get("distance")
    distance_km = float(distance) if distance else None
    hr_avg = act.get("hr_avg")
    avg_hr = int(hr_avg) if hr_avg else None

    pace: Optional[str] = None
    avg_speed_kmh: Optional[float] = None
    minutes = seconds / 60 if seconds else float(duration_min)
    if distance_km and distance_km > 0 and minutes > 0:
        avg_speed_kmh = round(distance_km / (minutes / 60), 2)
        pace_min = minutes / distance_km
        m = int(pace_min)
        s = int(round((pace_min - m) * 60))
        if s == 60:
            m, s = m + 1, 0
        pace = f"{m}:{s:02d}"

    return PhysicalLoad(
        id=f"runalyze_{act_id}",
        date=day,
        duration_minutes=duration_min,
        rpe_score=rpe,
        status=WorkoutStatus.COMPLETED,
        title=title,
        distance_km=distance_km,
        pace=pace,
        avg_speed_kmh=avg_speed_kmh,
        avg_hr=avg_hr,
    )


async def _sync_runalyze_activities(db: SQLiteManager, token: str) -> int:
    """Pull recent Runalyze activities and upsert them as completed workouts.

    Pages through ``/api/v1/activity?page=N`` (newest first) until an empty page,
    the page cap, or activities older than the lookback window. ``create_physical_load``
    is an INSERT-OR-REPLACE, so re-syncing refreshes edited activities. Returns the
    number of workouts created or updated. Raises ``httpx`` errors to the caller.
    """
    import httpx

    cutoff = date.today() - timedelta(days=settings.runalyze_sync_lookback_days)
    base_url = "https://runalyze.com/api/v1/activity"
    headers = {"token": token, "Accept": "application/json"}
    synced = 0

    # Runalyze can be slow; use a generous timeout instead of httpx's 5s default.
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        for page in range(1, settings.runalyze_sync_max_pages + 1):
            resp = await client.get(base_url, headers=headers, params={"page": page})
            resp.raise_for_status()
            data = resp.json()
            activities = data if isinstance(data, list) else data.get("data", [])
            if not activities:
                break

            reached_cutoff = False
            for act in activities:
                load = _runalyze_activity_to_load(act)
                if load is None:
                    continue
                if load.date < cutoff:
                    reached_cutoff = True
                    continue
                
                try:
                    existing = await db.get_physical_load(load.id)
                    if existing.note:
                        load.note = existing.note
                except RecordNotFoundError:
                    pass
                
                await db.create_physical_load(load)  # INSERT OR REPLACE = upsert
                synced += 1

            if reached_cutoff:
                break

    return synced


async def _runalyze_sync_loop(app: FastAPI) -> None:
    """Background loop: pull Runalyze activities on startup, then every interval.

    Re-reads the token each cycle (so it can be added without a restart) and
    swallows per-cycle errors so a transient failure never kills the loop.
    """
    interval = settings.runalyze_sync_interval_min * 60
    db: SQLiteManager = app.state.sqlite
    while True:
        token = _read_runalyze_token()
        if token:
            try:
                n = await _sync_runalyze_activities(db, token)
                if n:
                    logger.info("Runalyze auto-sync: %d workout(s) imported/updated", n)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - never let the loop die
                logger.warning("Runalyze auto-sync failed; retrying next cycle", exc_info=True)
        await asyncio.sleep(interval)


@app.post("/workouts/sync/runalyze")
async def sync_runalyze(request: Request) -> dict[str, Any]:
    """Fetch recent activities from Runalyze and upsert them as completed workouts."""
    import httpx

    db: SQLiteManager = request.app.state.sqlite
    token = _read_runalyze_token()
    if not token:
        raise HTTPException(
            status_code=400,
            detail=f"{settings.runalyze_token_env} bulunamadı. Lütfen .env dosyanıza ekleyin.",
        )

    try:
        imported = await _sync_runalyze_activities(db, token)
    except httpx.TimeoutException:
        logger.warning("Runalyze API request timed out")
        raise HTTPException(
            status_code=504,
            detail="Runalyze API zaman aşımına uğradı. Lütfen biraz sonra tekrar deneyin.",
        )
    except httpx.HTTPStatusError as exc:
        logger.warning("Runalyze API returned %s", exc.response.status_code)
        detail = (
            "Token geçersiz veya yetkisiz."
            if exc.response.status_code in (401, 403)
            else f"HTTP {exc.response.status_code}"
        )
        raise HTTPException(status_code=502, detail=f"Runalyze API Hatası: {detail}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Runalyze API request failed")
        raise HTTPException(status_code=502, detail=f"Runalyze API Hatası: {exc}")

    return {"imported": imported}


@app.patch("/workouts/{load_id}")
async def update_workout(request: Request, load_id: str, body: WorkoutUpdateRequest) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    try:
        load = await db.get_physical_load(load_id)
    except RecordNotFoundError:
        raise HTTPException(status_code=404, detail="Workout not found")
    updates = body.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(load, field_name, value)
    await db.update_physical_load(load)
    return load.model_dump(mode="json")


@app.delete("/workouts/{load_id}")
async def delete_workout(request: Request, load_id: str) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    try:
        await db.delete_physical_load(load_id)
    except RecordNotFoundError:
        raise HTTPException(status_code=404, detail="Workout not found")
    return {"status": "deleted", "id": load_id}


# --------------------------------------------------------------------------- #
# Cost usage + live logs
# --------------------------------------------------------------------------- #
@app.get("/usage")
async def usage(request: Request) -> dict[str, Any]:
    """Two-category API cost/usage snapshot: PDF automation vs. agent."""
    tracker: UsageTracker = request.app.state.usage
    return tracker.snapshot()
@app.get("/usage/logs")
async def usage_logs(request: Request, limit: int = 50) -> dict[str, Any]:
    """Return the raw usage rows (newest first)."""
    from tools.pdf_engine.automation.usage import UsageTracker
    tracker: UsageTracker = request.app.state.usage
    path = tracker._csv_path
    if not path or not path.exists():
        return {"logs": []}
    
    import csv
    try:
        with path.open("r", encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        return {"logs": rows[-limit:][::-1]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/logs/stream")
async def logs_stream(request: Request) -> StreamingResponse:
    """Stream backend/PDF-engine logs live as SSE (recent buffer first)."""
    bus: LogBus = request.app.state.log_bus
    queue = bus.subscribe()

    async def event_stream() -> AsyncIterator[str]:
        try:
            for record in bus.recent(300):
                yield _sse(record)
            while True:
                if await request.is_disconnected():
                    break
                try:
                    record = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield _sse(record)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"  # comment frame keeps the connection open
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------------------------------- #
# Journals
# --------------------------------------------------------------------------- #
from core.schemas import Journal, JournalItem

@app.get("/journals")
async def get_journals(request: Request) -> list[dict[str, Any]]:
    db: SQLiteManager = request.app.state.sqlite
    journals = await db.get_journals()
    return [j.model_dump() for j in journals]

@app.post("/journals")
async def upsert_journal(request: Request, body: JournalRequest) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    # Try to find existing journal for this date
    journals = await db.get_journals()
    existing = next((j for j in journals if j.date == body.date), None)
    
    if existing:
        existing.content = body.content
        existing.processed = False
        saved = await db.upsert_journal(existing)
    else:
        new_j = Journal(date=body.date, content=body.content)
        saved = await db.upsert_journal(new_j)
    
    return saved.model_dump()

@app.delete("/journals/{journal_id}")
async def delete_journal(request: Request, journal_id: str) -> dict[str, str]:
    db: SQLiteManager = request.app.state.sqlite
    await db.delete_journal(journal_id)
    return {"status": "ok"}

@app.get("/journal-items")
async def get_journal_items(request: Request) -> list[dict[str, Any]]:
    db: SQLiteManager = request.app.state.sqlite
    items = await db.get_journal_items()
    return [i.model_dump() for i in items]

@app.delete("/journal-items/{item_id}")
async def delete_journal_item(request: Request, item_id: str) -> dict[str, str]:
    db: SQLiteManager = request.app.state.sqlite
    await db.delete_journal_item(item_id)
    return {"status": "ok"}

@app.post("/journals/ai-analyze")
async def analyze_journals(request: Request, body: JournalAnalyzeRequest) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    from core.journal_analyzer import analyze_journal
    from core.usage_callback import AgentUsageCallback

    extracted_items_count = 0
    for jid in body.journal_ids:
        try:
            journal = await db.get_journal(jid)
            if not journal.processed:
                analysis = await analyze_journal(
                    journal.content, 
                    callbacks=[AgentUsageCallback(request.app.state.usage)]
                )
                
                for item in analysis.items:
                    new_item = JournalItem(
                        journal_id=journal.id,
                        type=item.type,
                        content=item.content
                    )
                    await db.upsert_journal_item(new_item)
                
                journal.processed = True
                await db.upsert_journal(journal)
                extracted_items_count += len(analysis.items)
        except Exception as exc:
            logger.error("Failed to analyze journal %s: %s", jid, exc)

    return {"status": "ok", "extracted": extracted_items_count}


# --------------------------------------------------------------------------- #
# Daily Notes
# --------------------------------------------------------------------------- #
from core.schemas import DailyNote

@app.get("/daily_notes")
async def get_daily_notes(request: Request) -> list[dict[str, Any]]:
    db: SQLiteManager = request.app.state.sqlite
    # This assumes db.get_daily_notes() exists
    notes = await db.get_daily_notes()
    return [n.model_dump(mode="json") for n in notes]

@app.post("/daily_notes")
async def upsert_daily_note(request: Request, body: DailyNoteRequest) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite

    # Default to today when the client omits the date.
    note_date = datetime.fromisoformat(body.date).date() if body.date else date.today()

    # Try to find existing note for this date
    notes = await db.get_daily_notes()
    existing = next((n for n in notes if n.date == note_date), None)

    if existing:
        existing.content = body.content
        existing.updated_at = datetime.now()
        saved = await db.upsert_daily_note(existing)
    else:
        new_n = DailyNote(date=note_date, content=body.content)
        saved = await db.upsert_daily_note(new_n)

    return saved.model_dump(mode="json")

# --------------------------------------------------------------------------- #
# SSE Logging
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Ideas (free-form notes with materials; no AI processing)
# --------------------------------------------------------------------------- #
async def _get_idea_or_404(db: SQLiteManager, idea_id: str) -> Idea:
    try:
        return await db.get_idea(idea_id)
    except RecordNotFoundError:
        raise HTTPException(status_code=404, detail="Idea not found")


@app.get("/ideas")
async def list_ideas(request: Request) -> list[dict[str, Any]]:
    db: SQLiteManager = request.app.state.sqlite
    ideas = await db.list_ideas()
    return [i.model_dump(mode="json") for i in ideas]


@app.post("/ideas")
async def create_idea(request: Request, body: IdeaCreateRequest) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    idea = Idea(title=body.title, content=body.content)
    await db.upsert_idea(idea)
    return idea.model_dump(mode="json")


@app.patch("/ideas/{idea_id}")
async def update_idea(
    request: Request, idea_id: str, body: IdeaUpdateRequest
) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    idea = await _get_idea_or_404(db, idea_id)
    updates = body.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(idea, field_name, value)
    idea.updated_at = datetime.now()
    await db.upsert_idea(idea)
    return idea.model_dump(mode="json")


@app.delete("/ideas/{idea_id}")
async def delete_idea(request: Request, idea_id: str) -> dict[str, str]:
    db: SQLiteManager = request.app.state.sqlite
    await db.delete_idea(idea_id)
    return {"status": "deleted", "id": idea_id}


@app.post("/ideas/{idea_id}/materials")
async def add_idea_material(
    request: Request, idea_id: str, body: MaterialCreateRequest
) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    idea = await _get_idea_or_404(db, idea_id)
    idea.materials = [
        *idea.materials,
        Material(kind=body.kind, name=body.name, source=body.source),
    ]
    idea.updated_at = datetime.now()
    await db.upsert_idea(idea)
    return idea.model_dump(mode="json")


@app.post("/ideas/{idea_id}/files")
async def upload_idea_file(
    request: Request, idea_id: str, file: UploadFile = File(...)
) -> dict[str, Any]:
    """Attach a raw file to an idea — stored untouched, never sent to the AI."""
    db: SQLiteManager = request.app.state.sqlite
    idea = await _get_idea_or_404(db, idea_id)
    filename = Path(file.filename or "file").name
    dest_dir = settings.data_dir / "idea_files" / idea_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    material = Material(kind="file", name=filename, source=filename)
    dest = dest_dir / f"{material.id}_{filename}"
    content = await file.read()
    await asyncio.to_thread(dest.write_bytes, content)
    material.source = str(dest)
    idea.materials = [*idea.materials, material]
    idea.updated_at = datetime.now()
    await db.upsert_idea(idea)
    return idea.model_dump(mode="json")


@app.get("/ideas/{idea_id}/materials/{material_id}/download")
async def download_idea_file(
    request: Request, idea_id: str, material_id: str
) -> FileResponse:
    db: SQLiteManager = request.app.state.sqlite
    idea = await _get_idea_or_404(db, idea_id)
    mat = next((m for m in idea.materials if m.id == material_id), None)
    if mat is None or mat.kind != "file" or not mat.source or not Path(mat.source).exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(mat.source, filename=mat.name)


__all__ = ["app"]
