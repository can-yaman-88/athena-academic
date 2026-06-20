"""DB-layer task tests, with focus on the null-deadline regressions."""

from __future__ import annotations

from datetime import datetime

import pytest

from core.schemas import AcademicSubtype, Note, Task, TaskCategory, TaskStatus


async def test_create_and_get_task_roundtrip(db):
    task = Task(title="Rapor yaz", discipline="genel", category=TaskCategory.DAILY)
    await db.create_task(task)
    fetched = await db.get_task(task.id)
    assert fetched.title == "Rapor yaz"
    assert fetched.category == TaskCategory.DAILY


async def test_task_with_null_deadline_roundtrips(db):
    """Regression: a task with no deadline must persist and load (not crash).

    Previously ``_row_to_task`` called ``datetime.fromisoformat(None)``.
    """
    task = Task(title="Tarihsiz", discipline="genel", deadline=None)
    await db.create_task(task)
    fetched = await db.get_task(task.id)
    assert fetched.deadline is None


async def test_task_with_deadline_roundtrips(db):
    dl = datetime(2026, 7, 1, 9, 30)
    task = Task(title="Teslim", discipline="genel", deadline=dl)
    await db.create_task(task)
    fetched = await db.get_task(task.id)
    assert fetched.deadline == dl


async def test_list_tasks_mixed_deadlines(db):
    await db.create_task(Task(title="A", discipline="g", deadline=datetime(2026, 7, 1)))
    await db.create_task(Task(title="B", discipline="g", deadline=None))
    tasks = await db.list_tasks()
    assert {t.title for t in tasks} == {"A", "B"}


async def test_update_task_progress_and_status(db):
    task = Task(title="Proje", discipline="cs", category=TaskCategory.ACADEMIC,
                subtype=AcademicSubtype.PROJECT)
    await db.create_task(task)
    task.progress = 75
    task.status = TaskStatus.COMPLETED
    await db.update_task(task)
    fetched = await db.get_task(task.id)
    assert fetched.progress == 75
    assert fetched.status == TaskStatus.COMPLETED


async def test_task_notes_persist(db):
    task = Task(title="Notlu", discipline="g", notes=[Note(text="ilk not")])
    await db.create_task(task)
    fetched = await db.get_task(task.id)
    assert len(fetched.notes) == 1
    assert fetched.notes[0].text == "ilk not"


async def test_delete_task(db):
    task = Task(title="Sil", discipline="g")
    await db.create_task(task)
    await db.delete_task(task.id)
    tasks = await db.list_tasks()
    assert all(t.id != task.id for t in tasks)
