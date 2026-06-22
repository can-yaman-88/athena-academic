"""FastAPI application for Athena-Academic.

Exposes the LangGraph agent (streaming chat), a PDF upload endpoint that runs the
in-process PDF->LaTeX engine in the background, task & idea CRUD, a PDF-job
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
from fastapi.staticfiles import StaticFiles
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
    NotePage,
    Task,
    TaskCategory,
    TaskStatus,
)
from core.usage_callback import AgentUsageCallback
from db.brain_manager import BrainManager
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

    # Brain (long-term memory): canonical rows in SQLite, embeddings in a
    # dedicated Chroma collection. The extractor LLM is built only when a key is
    # available (manual extraction is a no-op otherwise).
    brain_extractor_llm = None
    if os.environ.get(settings.openrouter_api_key_env):
        try:
            from core.graph import _make_llm

            brain_extractor_llm = _make_llm(
                settings.brain_model, settings.brain_model_max_tokens,
                callbacks=[AgentUsageCallback(usage)],
            )
        except Exception:  # pragma: no cover - defensive
            logger.exception("failed to build brain extractor LLM")
    brain = BrainManager(sqlite, extractor_llm=brain_extractor_llm)
    await asyncio.to_thread(brain.initialize)
    app.state.brain = brain

    # Build the agent graph only when an OpenRouter key is available; otherwise
    # /chat reports 503 instead of crashing the whole app at startup.
    app.state.graph = None
    if os.environ.get(settings.openrouter_api_key_env):
        try:
            app.state.graph = build_athena_graph(
                chroma_manager=chroma,
                brain_manager=brain,
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

    try:
        yield
    finally:
        await sqlite.close()


app = FastAPI(title="Athena-Academic", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve editor-uploaded inline assets (images/files) by URL so the rich-text
# editor can embed them: <img src="${API_URL}/uploads/files/<name>">.
settings.uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    "/uploads/files",
    StaticFiles(directory=str(settings.uploads_dir)),
    name="uploads",
)


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class Mention(BaseModel):
    """A reference the user explicitly picked in the chat box (@ or #).

    ``type`` is one of: task, subtask, idea, model, tag. ``id`` is the
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


class BrainFactRequest(BaseModel):
    """Create a long-term memory fact manually."""

    text: str = Field(min_length=1)
    category: str = "fact"
    pinned: bool = False


class BrainFactUpdateRequest(BaseModel):
    text: Optional[str] = None
    category: Optional[str] = None
    pinned: Optional[bool] = None


class BrainExtractRequest(BaseModel):
    """Recent chat lines to mine for durable facts (on-demand extraction)."""

    history: list[dict] = Field(default_factory=list)


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


async def _resolve_structured_mentions(
    mentions: list["Mention"], db: SQLiteManager
) -> str:
    """Turn explicitly-picked @/# mentions into a real-content context block.

    Unlike the regex text resolver this is unambiguous: each mention carries the
    object id and type the user actually selected, so multi-word titles, subtasks
    and ideas all resolve to their full content.
    """
    if not mentions:
        return ""

    all_tasks: Optional[list[Task]] = None
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
        # Multi-mode streaming:
        #   - "messages": token-level deltas (we forward only chat_node tokens so
        #     tool-node extractor JSON never leaks into the chat bubble);
        #   - "custom":   live Deep Research progress (research_node stream writer);
        #   - "updates":  final per-node messages + active tool for the tool nodes.
        streamed_delta = False
        try:
            async for mode, chunk in graph.astream(
                state, stream_mode=["messages", "custom", "updates"]
            ):
                if mode == "messages":
                    msg, meta = chunk
                    if (meta or {}).get("langgraph_node") != "chat_node":
                        continue
                    text = getattr(msg, "content", "")
                    if isinstance(text, list):
                        text = "".join(
                            b.get("text", "") if isinstance(b, dict) else str(b)
                            for b in text
                        )
                    if text:
                        streamed_delta = True
                        yield _sse({"type": "delta", "content": text})
                elif mode == "custom":
                    if isinstance(chunk, dict) and chunk.get("type") == "research_progress":
                        yield _sse(chunk)
                elif mode == "updates":
                    for node, partial in chunk.items():
                        if not isinstance(partial, dict):
                            continue
                        tool = partial.get("active_tool")
                        if tool:
                            yield _sse({"type": "tool_start", "tool": tool})
                        for msg in partial.get("messages", []) or []:
                            content = getattr(msg, "content", "")
                            if not content:
                                continue
                            # chat_node text already arrived as deltas; only emit
                            # the whole message when nothing streamed (e.g. the
                            # deterministic /yardim reply).
                            if node == "chat_node" and streamed_delta:
                                continue
                            yield _sse(
                                {"type": "message", "node": node, "content": content}
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
# Brain (long-term memory) CRUD + on-demand extraction
# --------------------------------------------------------------------------- #
@app.get("/brain")
async def list_brain(request: Request) -> dict[str, Any]:
    brain: BrainManager = request.app.state.brain
    return {"facts": await brain.list_facts()}


@app.post("/brain")
async def create_brain_fact(request: Request, body: BrainFactRequest) -> dict[str, Any]:
    brain: BrainManager = request.app.state.brain
    fact = await brain.add_fact(
        body.text, category=body.category, source="manual", pinned=body.pinned
    )
    return {"fact": fact}


@app.patch("/brain/{fact_id}")
async def update_brain_fact(
    request: Request, fact_id: str, body: BrainFactUpdateRequest
) -> dict[str, Any]:
    brain: BrainManager = request.app.state.brain
    fact = await brain.update_fact(
        fact_id, text=body.text, category=body.category, pinned=body.pinned
    )
    if fact is None:
        raise HTTPException(status_code=404, detail="Fact not found")
    return {"fact": fact}


@app.delete("/brain/{fact_id}")
async def delete_brain_fact(request: Request, fact_id: str) -> dict[str, Any]:
    brain: BrainManager = request.app.state.brain
    await brain.delete_fact(fact_id)
    return {"status": "deleted", "id": fact_id}


@app.post("/brain/extract")
async def extract_brain_facts(
    request: Request, body: BrainExtractRequest
) -> dict[str, Any]:
    """Mine the supplied recent chat history for durable facts (on-demand)."""
    brain: BrainManager = request.app.state.brain
    try:
        added = await brain.extract_from_messages(body.history)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return {"added": added, "count": len(added)}


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


# --------------------------------------------------------------------------- #
# Notes (Notion-style nested pages; rich-text HTML, page-in-page ≤ 3 levels)
# --------------------------------------------------------------------------- #
class NoteCreateRequest(BaseModel):
    title: str = ""
    content: str = ""
    parent_id: Optional[str] = None


class NoteUpdateRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None


async def _get_note_or_404(db: SQLiteManager, note_id: str) -> NotePage:
    try:
        return await db.get_note(note_id)
    except RecordNotFoundError:
        raise HTTPException(status_code=404, detail="Note not found")


@app.get("/notes")
async def list_notes(request: Request) -> list[dict[str, Any]]:
    db: SQLiteManager = request.app.state.sqlite
    notes = await db.list_notes()
    return [n.model_dump(mode="json") for n in notes]


@app.get("/notes/{note_id}")
async def get_note(request: Request, note_id: str) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    note = await _get_note_or_404(db, note_id)
    return note.model_dump(mode="json")


@app.get("/notes/{note_id}/children")
async def list_note_children(request: Request, note_id: str) -> list[dict[str, Any]]:
    db: SQLiteManager = request.app.state.sqlite
    children = await db.list_child_notes(note_id)
    return [n.model_dump(mode="json") for n in children]


@app.post("/notes")
async def create_note(request: Request, body: NoteCreateRequest) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    depth = 0
    if body.parent_id:
        parent = await _get_note_or_404(db, body.parent_id)
        if parent.depth >= 2:
            raise HTTPException(
                status_code=400,
                detail="En fazla 3 seviye iç içe sayfa olabilir (sayfa→sayfa→sayfa).",
            )
        depth = parent.depth + 1
    note = NotePage(
        title=body.title, content=body.content, parent_id=body.parent_id, depth=depth
    )
    await db.upsert_note(note)
    return note.model_dump(mode="json")


@app.patch("/notes/{note_id}")
async def update_note(
    request: Request, note_id: str, body: NoteUpdateRequest
) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    note = await _get_note_or_404(db, note_id)
    updates = body.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(note, field_name, value)
    note.updated_at = datetime.now().astimezone()
    await db.upsert_note(note)
    return note.model_dump(mode="json")


@app.delete("/notes/{note_id}")
async def delete_note(request: Request, note_id: str) -> dict[str, str]:
    db: SQLiteManager = request.app.state.sqlite
    await db.delete_note(note_id)
    return {"status": "deleted", "id": note_id}


# --------------------------------------------------------------------------- #
# Inline editor uploads (images/files embedded directly in note/idea bodies)
# --------------------------------------------------------------------------- #
@app.post("/uploads/inline")
async def upload_inline(file: UploadFile = File(...)) -> dict[str, Any]:
    """Save an editor-embedded asset and return a servable URL."""
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    filename = Path(file.filename or "file").name
    stored = f"{uuid4().hex}_{filename}"
    dest = settings.uploads_dir / stored
    content = await file.read()
    await asyncio.to_thread(dest.write_bytes, content)
    suffix = Path(filename).suffix.lower()
    kind = "image" if suffix in _IMAGE_EXTS else "file"
    return {"url": f"/uploads/files/{stored}", "name": filename, "kind": kind}


__all__ = ["app"]
