"""Async SQLite persistence for Jarvis-Academic structured records.

:class:`SQLiteManager` owns a single :mod:`aiosqlite` connection and provides
typed CRUD for the three domain schemas, plus an in-memory **idempotency
queue** of pending tasks that is rehydrated from disk on startup.

Resilience:
    - The database is opened in WAL mode with a ``busy_timeout`` so concurrent
      readers don't block writers and SQLite itself waits briefly on locks.
    - Writes are serialised through an :class:`asyncio.Lock` to avoid the
      process competing with itself for the write lock.
    - Every statement runs through :meth:`_with_retry`, which retries on
      transient "database is locked"/"busy" errors with exponential backoff and
      otherwise wraps failures in :class:`~db.exceptions.DatabaseError`.

Idempotency:
    Records carry client-generated UUID4 ids, so all writes use
    ``INSERT OR REPLACE``: re-inserting the same id is a no-op-equivalent
    upsert rather than an error. The pending-task queue is a dict keyed by id,
    so loading or enqueuing the same task twice cannot create duplicates.
"""

from __future__ import annotations

import asyncio
from datetime import date as date_type
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Awaitable, Callable, Optional, TypeVar

import aiosqlite

import json

from config import settings
from core.schemas import (
    AcademicSubtype,
    LoadAdjustment,
    Material,
    Note,
    PdfJob,
    PdfJobStatus,
    PhysicalLoad,
    StudySession,
    Task,
    TaskCategory,
    TaskStatus,
    WorkoutStatus,
)
from db.exceptions import DatabaseError, RecordNotFoundError

T = TypeVar("T")

_CREATE_TASKS = """
CREATE TABLE IF NOT EXISTS tasks (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    deadline        TEXT NOT NULL,
    discipline      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    estimated_hours REAL NOT NULL,
    category        TEXT NOT NULL DEFAULT 'daily',
    subtype         TEXT,
    parent_id       TEXT,
    progress        INTEGER NOT NULL DEFAULT 0,
    materials       TEXT NOT NULL DEFAULT '[]',
    notes           TEXT NOT NULL DEFAULT '[]'
);
"""

# (column, "ALTER ... ADD COLUMN" clause) for migrating pre-v2 task tables.
_TASK_COLUMN_MIGRATIONS = [
    ("category", "category TEXT NOT NULL DEFAULT 'daily'"),
    ("subtype", "subtype TEXT"),
    ("parent_id", "parent_id TEXT"),
    ("progress", "progress INTEGER NOT NULL DEFAULT 0"),
    ("materials", "materials TEXT NOT NULL DEFAULT '[]'"),
    ("notes", "notes TEXT NOT NULL DEFAULT '[]'"),
]

_CREATE_TASKS_STATUS_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks (status);"
)

_CREATE_STUDY_SESSIONS = """
CREATE TABLE IF NOT EXISTS study_sessions (
    id               TEXT PRIMARY KEY,
    topic            TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    retention_score  REAL NOT NULL
);
"""

_CREATE_PHYSICAL_LOADS = """
CREATE TABLE IF NOT EXISTS physical_loads (
    id               TEXT PRIMARY KEY,
    date             TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    rpe_score        INTEGER NOT NULL,
    calculated_load  REAL NOT NULL,
    status           TEXT NOT NULL DEFAULT 'completed',
    title            TEXT,
    distance_km      REAL,
    pace             TEXT,
    avg_speed_kmh    REAL,
    avg_hr           INTEGER
);
"""

# (column, ADD COLUMN clause) for migrating pre-v2 physical_loads tables.
_LOAD_COLUMN_MIGRATIONS = [
    ("status", "status TEXT NOT NULL DEFAULT 'completed'"),
    ("title", "title TEXT"),
    ("distance_km", "distance_km REAL"),
    ("pace", "pace TEXT"),
    ("avg_speed_kmh", "avg_speed_kmh REAL"),
    ("avg_hr", "avg_hr INTEGER"),
]

_CREATE_CHAT_MATERIALS = """
CREATE TABLE IF NOT EXISTS chat_materials (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'file',
    source_path TEXT,
    markdown    TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
"""

_CREATE_LOAD_ADJUSTMENTS = """
CREATE TABLE IF NOT EXISTS load_adjustments (
    id       TEXT PRIMARY KEY,
    date     TEXT NOT NULL,
    amount   REAL NOT NULL,
    reason   TEXT NOT NULL DEFAULT '',
    task_id  TEXT
);
"""

_CREATE_LOAD_ADJ_DATE_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_load_adj_date ON load_adjustments (date);"
)

_CREATE_PDF_JOBS = """
CREATE TABLE IF NOT EXISTS pdf_jobs (
    id               TEXT PRIMARY KEY,
    filename         TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'processing',
    created_at       TEXT NOT NULL,
    completed_at     TEXT,
    artifacts        TEXT NOT NULL DEFAULT '[]',
    cost_usd         REAL NOT NULL DEFAULT 0,
    chunks_ingested  INTEGER NOT NULL DEFAULT 0,
    error            TEXT,
    summary          TEXT NOT NULL DEFAULT ''
);
"""


class SQLiteManager:
    """Async CRUD manager backed by a single ``aiosqlite`` connection."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        *,
        busy_timeout_ms: int | None = None,
        max_retries: int | None = None,
        retry_base_delay: float | None = None,
    ) -> None:
        self._db_path = Path(db_path) if db_path is not None else settings.sqlite_path
        self._busy_timeout_ms = (
            busy_timeout_ms
            if busy_timeout_ms is not None
            else settings.db_busy_timeout_ms
        )
        self._max_retries = (
            max_retries if max_retries is not None else settings.db_max_retries
        )
        self._retry_base_delay = (
            retry_base_delay
            if retry_base_delay is not None
            else settings.db_retry_base_delay
        )

        self._conn: Optional[aiosqlite.Connection] = None
        self._write_lock = asyncio.Lock()
        # Idempotency queue: pending tasks keyed by id (re-adds are no-ops).
        self._pending_tasks: dict[str, Task] = {}

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def initialize(self) -> None:
        """Open the connection, apply PRAGMAs, create tables, load the queue."""
        if self._conn is not None:
            return

        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            conn = await aiosqlite.connect(self._db_path)
        except aiosqlite.Error as exc:  # pragma: no cover - connection failure
            raise DatabaseError(
                f"Failed to open SQLite database at {self._db_path}: {exc}"
            ) from exc

        conn.row_factory = aiosqlite.Row
        self._conn = conn

        try:
            await conn.execute("PRAGMA journal_mode=WAL;")
            await conn.execute("PRAGMA foreign_keys=ON;")
            await conn.execute("PRAGMA synchronous=NORMAL;")
            await conn.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms};")
            await self._create_tables()
            await self.load_pending_tasks()
        except aiosqlite.Error as exc:
            await self.close()
            raise DatabaseError(f"Failed to initialise database: {exc}") from exc

    async def _create_tables(self) -> None:
        conn = self._require_conn()
        await conn.execute(_CREATE_TASKS)
        await conn.execute(_CREATE_TASKS_STATUS_INDEX)
        await conn.execute(_CREATE_STUDY_SESSIONS)
        await conn.execute(_CREATE_PHYSICAL_LOADS)
        await conn.execute(_CREATE_LOAD_ADJUSTMENTS)
        await conn.execute(_CREATE_LOAD_ADJ_DATE_INDEX)
        await conn.execute(_CREATE_CHAT_MATERIALS)
        await conn.execute(_CREATE_PDF_JOBS)
        await conn.commit()
        await self._migrate_task_columns()

    async def _migrate_task_columns(self) -> None:
        """Add any v2 task columns missing from a pre-existing DB (idempotent)."""
        conn = self._require_conn()
        async with conn.execute("PRAGMA table_info(tasks)") as cursor:
            existing = {row[1] for row in await cursor.fetchall()}
        added = False
        for column, clause in _TASK_COLUMN_MIGRATIONS:
            if column not in existing:
                await conn.execute(f"ALTER TABLE tasks ADD COLUMN {clause}")
                added = True
        if added:
            await conn.commit()
        await self._migrate_load_columns()

    async def _migrate_load_columns(self) -> None:
        """Add any v2 physical_loads columns missing from a pre-existing DB."""
        conn = self._require_conn()
        async with conn.execute("PRAGMA table_info(physical_loads)") as cursor:
            existing = {row[1] for row in await cursor.fetchall()}
        added = False
        for column, clause in _LOAD_COLUMN_MIGRATIONS:
            if column not in existing:
                await conn.execute(f"ALTER TABLE physical_loads ADD COLUMN {clause}")
                added = True
        if added:
            await conn.commit()

    async def close(self) -> None:
        """Close the underlying connection if open."""
        if self._conn is not None:
            try:
                await self._conn.close()
            finally:
                self._conn = None

    async def __aenter__(self) -> "SQLiteManager":
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        await self.close()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _require_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise DatabaseError(
                "SQLiteManager is not initialised; call initialize() first."
            )
        return self._conn

    async def _with_retry(self, operation: Callable[[], Awaitable[T]]) -> T:
        """Run ``operation`` retrying on transient lock/busy errors."""
        delay = self._retry_base_delay
        last_exc: Optional[aiosqlite.Error] = None

        for attempt in range(self._max_retries + 1):
            try:
                return await operation()
            except aiosqlite.OperationalError as exc:
                message = str(exc).lower()
                is_transient = "locked" in message or "busy" in message
                if is_transient and attempt < self._max_retries:
                    last_exc = exc
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                raise DatabaseError(
                    f"SQLite operational error after {attempt + 1} attempt(s): {exc}"
                ) from exc
            except aiosqlite.Error as exc:
                raise DatabaseError(f"SQLite error: {exc}") from exc

        # Exhausted retries on a transient error.
        raise DatabaseError(
            f"SQLite remained locked after {self._max_retries + 1} attempts: {last_exc}"
        ) from last_exc

    async def _write(self, sql: str, params: tuple[object, ...]) -> None:
        """Execute a single write statement under the write lock, then commit."""
        conn = self._require_conn()

        async def op() -> None:
            await conn.execute(sql, params)
            await conn.commit()

        async with self._write_lock:
            await self._with_retry(op)

    async def _fetchone(
        self, sql: str, params: tuple[object, ...]
    ) -> Optional[aiosqlite.Row]:
        conn = self._require_conn()

        async def op() -> Optional[aiosqlite.Row]:
            async with conn.execute(sql, params) as cursor:
                return await cursor.fetchone()

        return await self._with_retry(op)

    async def _fetchall(
        self, sql: str, params: tuple[object, ...]
    ) -> list[aiosqlite.Row]:
        conn = self._require_conn()

        async def op() -> list[aiosqlite.Row]:
            async with conn.execute(sql, params) as cursor:
                return list(await cursor.fetchall())

        return await self._with_retry(op)

    # ------------------------------------------------------------------ #
    # Row <-> model conversion
    # ------------------------------------------------------------------ #
    @staticmethod
    def _row_to_task(row: aiosqlite.Row) -> Task:
        keys = set(row.keys())

        def _json(col: str) -> list:
            raw = row[col] if col in keys else None
            try:
                return json.loads(raw) if raw else []
            except (ValueError, TypeError):
                return []

        subtype_raw = row["subtype"] if "subtype" in keys else None
        return Task(
            id=row["id"],
            title=row["title"],
            deadline=datetime.fromisoformat(row["deadline"]),
            discipline=row["discipline"],
            status=TaskStatus(row["status"]),
            estimated_hours=row["estimated_hours"],
            category=TaskCategory(row["category"] if "category" in keys and row["category"] else "daily"),
            subtype=AcademicSubtype(subtype_raw) if subtype_raw else None,
            parent_id=row["parent_id"] if "parent_id" in keys else None,
            progress=row["progress"] if "progress" in keys and row["progress"] is not None else 0,
            materials=[Material(**m) for m in _json("materials")],
            notes=[Note(**n) for n in _json("notes")],
        )

    @staticmethod
    def _row_to_study_session(row: aiosqlite.Row) -> StudySession:
        return StudySession(
            id=row["id"],
            topic=row["topic"],
            duration_minutes=row["duration_minutes"],
            retention_score=row["retention_score"],
        )

    @staticmethod
    def _row_to_physical_load(row: aiosqlite.Row) -> PhysicalLoad:
        # calculated_load is computed by the model, not passed in.
        keys = set(row.keys())
        status = row["status"] if "status" in keys and row["status"] else "completed"
        return PhysicalLoad(
            id=row["id"],
            date=date_type.fromisoformat(row["date"]),
            duration_minutes=row["duration_minutes"],
            rpe_score=row["rpe_score"],
            status=WorkoutStatus(status),
            title=row["title"] if "title" in keys else None,
            distance_km=row["distance_km"] if "distance_km" in keys else None,
            pace=row["pace"] if "pace" in keys else None,
            avg_speed_kmh=row["avg_speed_kmh"] if "avg_speed_kmh" in keys else None,
            avg_hr=row["avg_hr"] if "avg_hr" in keys else None,
        )

    # ------------------------------------------------------------------ #
    # Tasks
    # ------------------------------------------------------------------ #
    async def create_task(self, task: Task) -> Task:
        """Upsert a task (idempotent on id) and sync the pending queue."""
        await self._write(
            """
            INSERT OR REPLACE INTO tasks
                (id, title, deadline, discipline, status, estimated_hours,
                 category, subtype, parent_id, progress, materials, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.id,
                task.title,
                task.deadline.isoformat(),
                task.discipline,
                task.status.value,
                task.estimated_hours,
                task.category.value,
                task.subtype.value if task.subtype else None,
                task.parent_id,
                task.progress,
                json.dumps([m.model_dump(mode="json") for m in task.materials]),
                json.dumps([n.model_dump(mode="json") for n in task.notes]),
            ),
        )
        self._sync_queue(task)
        return task

    async def get_task(self, task_id: str) -> Task:
        row = await self._fetchone("SELECT * FROM tasks WHERE id = ?", (task_id,))
        if row is None:
            raise RecordNotFoundError(f"Task not found: {task_id}")
        return self._row_to_task(row)

    async def list_tasks(self, status: TaskStatus | None = None) -> list[Task]:
        if status is None:
            rows = await self._fetchall("SELECT * FROM tasks ORDER BY deadline", ())
        else:
            rows = await self._fetchall(
                "SELECT * FROM tasks WHERE status = ? ORDER BY deadline",
                (status.value,),
            )
        return [self._row_to_task(row) for row in rows]

    async def list_subtasks(self, parent_id: str) -> list[Task]:
        rows = await self._fetchall(
            "SELECT * FROM tasks WHERE parent_id = ? ORDER BY deadline", (parent_id,)
        )
        return [self._row_to_task(row) for row in rows]

    async def update_task(self, task: Task) -> Task:
        """Replace an existing task; raises if the id is unknown."""
        await self.get_task(task.id)  # existence check -> RecordNotFoundError
        return await self.create_task(task)

    async def set_task_status(self, task_id: str, status: TaskStatus) -> Task:
        """Update only a task's status and keep the pending queue in sync."""
        task = await self.get_task(task_id)
        await self._write(
            "UPDATE tasks SET status = ? WHERE id = ?",
            (status.value, task_id),
        )
        task.status = status
        self._sync_queue(task)
        return task

    async def mark_task_completed(self, task_id: str) -> Task:
        """Convenience wrapper: mark a task completed and evict it from the queue."""
        return await self.set_task_status(task_id, TaskStatus.COMPLETED)

    async def delete_task(self, task_id: str) -> None:
        await self.get_task(task_id)  # existence check
        await self._write("DELETE FROM tasks WHERE id = ?", (task_id,))
        self._pending_tasks.pop(task_id, None)

    # ------------------------------------------------------------------ #
    # Idempotency queue
    # ------------------------------------------------------------------ #
    async def load_pending_tasks(self) -> list[Task]:
        """(Re)load all pending tasks from disk into the in-memory queue."""
        rows = await self._fetchall(
            "SELECT * FROM tasks WHERE status = ? ORDER BY deadline",
            (TaskStatus.PENDING.value,),
        )
        self._pending_tasks = {
            row["id"]: self._row_to_task(row) for row in rows
        }
        return list(self._pending_tasks.values())

    def _sync_queue(self, task: Task) -> None:
        """Add/refresh or evict a task from the pending queue based on status."""
        if task.status == TaskStatus.PENDING:
            self._pending_tasks[task.id] = task
        else:
            self._pending_tasks.pop(task.id, None)

    def get_pending_tasks(self) -> list[Task]:
        """Snapshot of the in-memory pending-task queue."""
        return list(self._pending_tasks.values())

    @property
    def pending_count(self) -> int:
        return len(self._pending_tasks)

    # ------------------------------------------------------------------ #
    # Study sessions
    # ------------------------------------------------------------------ #
    async def create_study_session(self, session: StudySession) -> StudySession:
        await self._write(
            """
            INSERT OR REPLACE INTO study_sessions
                (id, topic, duration_minutes, retention_score)
            VALUES (?, ?, ?, ?)
            """,
            (
                session.id,
                session.topic,
                session.duration_minutes,
                session.retention_score,
            ),
        )
        return session

    async def get_study_session(self, session_id: str) -> StudySession:
        row = await self._fetchone(
            "SELECT * FROM study_sessions WHERE id = ?", (session_id,)
        )
        if row is None:
            raise RecordNotFoundError(f"StudySession not found: {session_id}")
        return self._row_to_study_session(row)

    async def list_study_sessions(self) -> list[StudySession]:
        rows = await self._fetchall("SELECT * FROM study_sessions", ())
        return [self._row_to_study_session(row) for row in rows]

    async def delete_study_session(self, session_id: str) -> None:
        await self.get_study_session(session_id)  # existence check
        await self._write("DELETE FROM study_sessions WHERE id = ?", (session_id,))

    # ------------------------------------------------------------------ #
    # Physical loads
    # ------------------------------------------------------------------ #
    async def create_physical_load(self, load: PhysicalLoad) -> PhysicalLoad:
        await self._write(
            """
            INSERT OR REPLACE INTO physical_loads
                (id, date, duration_minutes, rpe_score, calculated_load,
                 status, title, distance_km, pace, avg_speed_kmh, avg_hr)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                load.id,
                load.date.isoformat(),
                load.duration_minutes,
                load.rpe_score,
                load.calculated_load,
                load.status.value,
                load.title,
                load.distance_km,
                load.pace,
                load.avg_speed_kmh,
                load.avg_hr,
            ),
        )
        return load

    async def get_physical_load(self, load_id: str) -> PhysicalLoad:
        row = await self._fetchone(
            "SELECT * FROM physical_loads WHERE id = ?", (load_id,)
        )
        if row is None:
            raise RecordNotFoundError(f"PhysicalLoad not found: {load_id}")
        return self._row_to_physical_load(row)

    async def update_physical_load(self, load: PhysicalLoad) -> PhysicalLoad:
        """Replace an existing physical load (idempotent upsert); raises if absent."""
        await self.get_physical_load(load.id)  # existence check
        return await self.create_physical_load(load)

    async def list_physical_loads(self) -> list[PhysicalLoad]:
        rows = await self._fetchall(
            "SELECT * FROM physical_loads ORDER BY date", ()
        )
        return [self._row_to_physical_load(row) for row in rows]

    # ------------------------------------------------------------------ #
    # Cognitive load adjustments (day-scoped, from note analysis)
    # ------------------------------------------------------------------ #
    async def create_load_adjustment(self, adj: LoadAdjustment) -> LoadAdjustment:
        await self._write(
            """
            INSERT OR REPLACE INTO load_adjustments (id, date, amount, reason, task_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (adj.id, adj.date.isoformat(), adj.amount, adj.reason, adj.task_id),
        )
        return adj

    async def list_load_adjustments(
        self, on_date: date_type | None = None
    ) -> list[LoadAdjustment]:
        if on_date is None:
            rows = await self._fetchall("SELECT * FROM load_adjustments", ())
        else:
            rows = await self._fetchall(
                "SELECT * FROM load_adjustments WHERE date = ?", (on_date.isoformat(),)
            )
        return [
            LoadAdjustment(
                id=row["id"],
                date=date_type.fromisoformat(row["date"]),
                amount=row["amount"],
                reason=row["reason"] or "",
                task_id=row["task_id"],
            )
            for row in rows
        ]

    # ------------------------------------------------------------------ #
    # Chat-uploaded materials (PDF->MD / image->MD attachments)
    # ------------------------------------------------------------------ #
    async def create_chat_material(
        self, *, id: str, name: str, kind: str, source_path: str, markdown: str
    ) -> dict:
        await self._write(
            """
            INSERT OR REPLACE INTO chat_materials
                (id, name, kind, source_path, markdown, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (id, name, kind, source_path, markdown, datetime.now().isoformat()),
        )
        return {"id": id, "name": name, "kind": kind, "source_path": source_path,
                "markdown": markdown}

    async def get_chat_material(self, material_id: str) -> Optional[dict]:
        row = await self._fetchone(
            "SELECT * FROM chat_materials WHERE id = ?", (material_id,)
        )
        if row is None:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "kind": row["kind"],
            "source_path": row["source_path"],
            "markdown": row["markdown"] or "",
        }

    async def delete_physical_load(self, load_id: str) -> None:
        await self.get_physical_load(load_id)  # existence check
        await self._write("DELETE FROM physical_loads WHERE id = ?", (load_id,))

    # ------------------------------------------------------------------ #
    # PDF jobs
    # ------------------------------------------------------------------ #
    @staticmethod
    def _row_to_pdf_job(row: aiosqlite.Row) -> PdfJob:
        try:
            artifacts = json.loads(row["artifacts"]) if row["artifacts"] else []
        except (ValueError, TypeError):
            artifacts = []
        return PdfJob(
            id=row["id"],
            filename=row["filename"],
            status=PdfJobStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            completed_at=(
                datetime.fromisoformat(row["completed_at"])
                if row["completed_at"]
                else None
            ),
            artifacts=artifacts,
            cost_usd=row["cost_usd"],
            chunks_ingested=row["chunks_ingested"],
            error=row["error"],
            summary=row["summary"] or "",
        )

    async def create_pdf_job(self, job: PdfJob) -> PdfJob:
        """Upsert a PDF job (idempotent on id)."""
        await self._write(
            """
            INSERT OR REPLACE INTO pdf_jobs
                (id, filename, status, created_at, completed_at, artifacts,
                 cost_usd, chunks_ingested, error, summary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.id,
                job.filename,
                job.status.value,
                job.created_at.isoformat(),
                job.completed_at.isoformat() if job.completed_at else None,
                json.dumps(job.artifacts),
                job.cost_usd,
                job.chunks_ingested,
                job.error,
                job.summary,
            ),
        )
        return job

    async def update_pdf_job(self, job: PdfJob) -> PdfJob:
        """Persist the current state of a PDF job (upsert)."""
        return await self.create_pdf_job(job)

    async def get_pdf_job(self, job_id: str) -> PdfJob:
        row = await self._fetchone("SELECT * FROM pdf_jobs WHERE id = ?", (job_id,))
        if row is None:
            raise RecordNotFoundError(f"PdfJob not found: {job_id}")
        return self._row_to_pdf_job(row)

    async def list_pdf_jobs(self, limit: int = 100) -> list[PdfJob]:
        rows = await self._fetchall(
            "SELECT * FROM pdf_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [self._row_to_pdf_job(row) for row in rows]


__all__ = ["SQLiteManager"]
