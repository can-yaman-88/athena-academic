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
from datetime import date, datetime
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
from pydantic import BaseModel, Field

from config import settings
from core.graph import build_athena_graph
from core.log_bus import LogBus, LogBusHandler
from core.note_analyzer import analyze_notes
from core.schemas import (
    AcademicSubtype,
    LoadAdjustment,
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

from tools.agentic_tools import calculate_cognitive_allowance
from tools.agentic_tools.load_balancer import evaluate_load
from tools.pdf_engine import process_academic_pdf
from tools.pdf_engine.automation import UsageTracker, build_engine_config
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


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    attachment_ids: list[str] = Field(default_factory=list)


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    deadline: datetime
    discipline: str = Field(default_factory=lambda: settings.default_discipline)
    estimated_hours: float = Field(
        default_factory=lambda: settings.default_estimated_hours, gt=0
    )
    category: TaskCategory = TaskCategory.DAILY
    subtype: Optional[AcademicSubtype] = None
    parent_id: Optional[str] = None


class TaskUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1)
    deadline: Optional[datetime] = None
    discipline: Optional[str] = Field(default=None, min_length=1)
    estimated_hours: Optional[float] = Field(default=None, gt=0)
    status: Optional[TaskStatus] = None
    category: Optional[TaskCategory] = None
    subtype: Optional[AcademicSubtype] = None
    progress: Optional[int] = Field(default=None, ge=0, le=100)


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
    rpe_score: int = Field(ge=1, le=10)
    date: Optional[date] = None
    status: WorkoutStatus = WorkoutStatus.COMPLETED
    title: Optional[str] = None
    distance_km: Optional[float] = Field(default=None, ge=0)
    pace: Optional[str] = None
    avg_speed_kmh: Optional[float] = Field(default=None, ge=0)
    avg_hr: Optional[int] = Field(default=None, ge=0, le=260)


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


def _sse(payload: dict[str, Any]) -> str:
    """Format a dict as a Server-Sent Events data frame."""
    return f"data: {json.dumps(payload)}\n\n"


async def _today_cognitive_load(db: SQLiteManager) -> dict[str, Any]:
    """Total cognitive load today = today's workout load + today's note adjustments."""
    today = date.today()
    loads = await db.list_physical_loads()
    # Only COMPLETED workouts (today) contribute to cognitive load; planned ones don't.
    workout_load = sum(
        load.calculated_load
        for load in loads
        if load.date == today and load.status == WorkoutStatus.COMPLETED
    )
    adjustments = await db.list_load_adjustments(today)
    adj_load = sum(a.amount for a in adjustments)
    total = float(workout_load) + float(adj_load)

    if total <= 0:
        return {
            "calculated_load": 0.0,
            "heavy_cognitive_blocked": False,
            "block_duration_hours": 0,
            "recommended_tasks": [],
            "blocked_until": None,
            "directive": "No load logged today — full cognitive capacity available.",
            "workout_load": float(workout_load),
            "note_load": float(adj_load),
        }
    result = evaluate_load(total).model_dump(mode="json")
    result["workout_load"] = float(workout_load)
    result["note_load"] = float(adj_load)
    return result


# --------------------------------------------------------------------------- #
# Health + chat
# --------------------------------------------------------------------------- #
@app.get("/health")
async def health(request: Request) -> dict[str, Any]:
    """Liveness probe; reports whether the agent graph is available."""
    return {"status": "ok", "graph_ready": request.app.state.graph is not None}


@app.post("/chat")
async def chat(request: Request, body: ChatRequest) -> StreamingResponse:
    """Stream the LangGraph agent's output for a user message as SSE."""
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

    async def event_stream() -> AsyncIterator[str]:
        state = {
            "messages": [HumanMessage(content=body.message)],
            "attachments": attachments,
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
) -> dict[str, Any]:
    """Save an uploaded PDF and run the in-process engine in the background."""
    filename = Path(file.filename or "upload.pdf").name  # strip any path traversal
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.uploads_dir / filename

    content = await file.read()
    await asyncio.to_thread(dest.write_bytes, content)

    background_tasks.add_task(
        process_academic_pdf,
        str(dest),
        instructions,
        chroma_manager=request.app.state.chroma,
        usage_tracker=request.app.state.usage,
        log_bus=request.app.state.log_bus,
        sqlite_manager=request.app.state.sqlite,
    )
    logger.info("queued upload %s (%d bytes) for processing", filename, len(content))
    return {
        "status": "accepted",
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
    """Return current tasks, pending count, and today's cognitive load."""
    db: SQLiteManager = request.app.state.sqlite
    tasks = await db.list_tasks()
    pending_count = len(db.get_pending_tasks())
    cognitive_load = await _today_cognitive_load(db)
    return {
        "tasks": [t.model_dump(mode="json") for t in tasks],
        "pending_count": pending_count,
        "cognitive_load": cognitive_load,
    }


# --------------------------------------------------------------------------- #
# Task CRUD
# --------------------------------------------------------------------------- #
@app.get("/tasks")
async def list_tasks(request: Request, status: Optional[TaskStatus] = None) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    tasks = await db.list_tasks(status)
    return {"tasks": [t.model_dump(mode="json") for t in tasks]}


@app.post("/tasks")
async def create_task(request: Request, body: TaskCreateRequest) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    task = Task(
        title=body.title,
        deadline=body.deadline,
        discipline=body.discipline,
        estimated_hours=body.estimated_hours,
        category=body.category,
        subtype=body.subtype if body.category == TaskCategory.ACADEMIC else None,
        parent_id=body.parent_id,
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
async def complete_task(request: Request, task_id: str) -> dict[str, Any]:
    db: SQLiteManager = request.app.state.sqlite
    try:
        task = await db.mark_task_completed(task_id)
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
    from core.graph import _generate_subtasks, _make_llm
    from core.subtasks import SubtaskPlan

    try:
        base = _make_llm(
            settings.notes_model, settings.notes_model_max_tokens,
            callbacks=[AgentUsageCallback(request.app.state.usage)],
        )
        sub_llm = base.with_structured_output(SubtaskPlan, method="function_calling")
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
            "notes": [n.text for n in t.notes],
        }
        for t in tasks
        if t.notes
    ]
    if not payload:
        return {"cognitive_load_additions": 0, "task_progress_updates": 0,
                "message": "No notes to analyze."}

    # Tests can inject a fake structured-output runnable on app.state.notes_llm.
    injected = getattr(request.app.state, "notes_llm", None)
    try:
        analysis = await analyze_notes(
            payload, llm=injected, callbacks=[AgentUsageCallback(usage)]
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the client
        logger.exception("note analysis failed")
        raise HTTPException(status_code=503, detail=f"Note analysis failed: {exc}")

    today = date.today()
    valid_ids = {t.id for t in tasks}
    for add in analysis.cognitive_load_additions:
        await db.create_load_adjustment(
            LoadAdjustment(date=today, amount=add.amount, reason=add.reason,
                           task_id=add.task_id if add.task_id in valid_ids else None)
        )
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

    return {
        "cognitive_load_additions": len(analysis.cognitive_load_additions),
        "task_progress_updates": applied_progress,
        "added_load": sum(a.amount for a in analysis.cognitive_load_additions),
    }


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
    """Record a workout (with optional metrics) and return the load directive."""
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
    )
    await db.create_physical_load(load)
    allowance = calculate_cognitive_allowance.invoke(
        {"rpe_score": body.rpe_score, "duration": float(body.duration_minutes)}
    )
    return {
        "physical_load": load.model_dump(mode="json"),
        "cognitive_allowance": allowance.model_dump(mode="json"),
    }


@app.post("/workouts/{load_id}/complete")
async def complete_workout(request: Request, load_id: str) -> dict[str, Any]:
    """Mark a planned workout completed so it counts toward cognitive load."""
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
            rpe_score=rec["rpe_score"],
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


@app.get("/logs/stream")
async def logs_stream(request: Request) -> StreamingResponse:
    """Stream backend/PDF-engine logs live as SSE (recent buffer first)."""
    bus: LogBus = request.app.state.log_bus
    queue = bus.subscribe()

    async def event_stream() -> AsyncIterator[str]:
        try:
            for record in bus.recent(100):
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


__all__ = ["app"]
