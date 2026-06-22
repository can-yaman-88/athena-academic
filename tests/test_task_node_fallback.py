"""task_tool_node behavior: self-sufficient commands + null-by-default deadlines.

These guard the "I just sent a plan and got 'net bir görev çıkaramadım'" and the
"long plan throws a memory error" complaints: any non-empty input must yield a
task, even when the extractor LLM returns nothing or raises.
"""

from __future__ import annotations

from datetime import datetime

from langchain_core.messages import HumanMessage

from core.graph import _generate_subtasks, task_tool_node
from core.prompt_templates import TaskExtraction, TaskExtractionList
from core.schemas import Task, TaskCategory
from core.subtasks import SubtaskItem, SubtaskPlan


class _FakeLLM:
    """Stand-in for the structured extractor LLM."""

    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc

    async def ainvoke(self, _messages):
        if self._exc is not None:
            raise self._exc
        return self._result


def _state(text: str) -> dict:
    return {"messages": [HumanMessage(content=text)]}


async def test_empty_extraction_still_creates_task(db):
    """Empty extractor result → deterministic single task, not a giving-up message."""
    llm = _FakeLLM(result=TaskExtractionList(tasks=[]))
    out = await task_tool_node(
        _state("/agorev acayip uzun ve dağınık bir görev metni"),
        task_extractor_llm=llm, sqlite_manager=db, subtask_llm=None,
    )
    tasks = await db.list_tasks()
    assert len(tasks) == 1
    assert tasks[0].deadline is None
    assert "çıkaramadım" not in out["messages"][0].content.lower()


async def test_extractor_exception_falls_back(db):
    """A raised extractor (e.g. long-input failure) still produces a task."""
    llm = _FakeLLM(exc=RuntimeError("boom"))
    out = await task_tool_node(
        _state("/plan çok büyük ve uzun bir proje planı"),
        task_extractor_llm=llm, sqlite_manager=db, subtask_llm=None,
    )
    tasks = await db.list_tasks()
    assert len(tasks) == 1
    assert "Couldn't parse" not in out["messages"][0].content


async def test_blank_input_does_not_create(db):
    """A truly empty command body is the only case that creates nothing."""
    llm = _FakeLLM(result=TaskExtractionList(tasks=[]))
    await task_tool_node(
        _state("/agorev    "),
        task_extractor_llm=llm, sqlite_manager=db, subtask_llm=None,
    )
    tasks = await db.list_tasks()
    assert len(tasks) == 0


async def test_fallback_preserves_detail_in_notes(db):
    """The first line becomes the title; the rest is kept in notes (nothing lost)."""
    llm = _FakeLLM(result=TaskExtractionList(tasks=[]))
    text = "/agorev Başlık satırı\nikinci satır detay\nüçüncü satır"
    await task_tool_node(
        _state(text), task_extractor_llm=llm, sqlite_manager=db, subtask_llm=None,
    )
    tasks = await db.list_tasks()
    assert tasks[0].title == "Başlık satırı"
    assert tasks[0].notes and "ikinci satır detay" in tasks[0].notes[0].text


async def test_omitted_date_yields_null_deadline(db):
    """When the extractor returns a task with no deadline, it persists as null."""
    op = TaskExtraction(operation="create", title="Tarihsiz görev",
                        deadline=None, category="daily")
    llm = _FakeLLM(result=TaskExtractionList(tasks=[op]))
    await task_tool_node(
        _state("/agorev bir şeyler yap"),
        task_extractor_llm=llm, sqlite_manager=db, subtask_llm=None,
    )
    tasks = await db.list_tasks()
    assert len(tasks) == 1
    assert tasks[0].deadline is None


async def test_subtasks_with_null_deadline_parent_do_not_crash():
    """Regression: a deadline-less parent must not crash subtask generation.

    `_generate_subtasks` formatted `parent.deadline.isoformat()` unconditionally,
    raising 'NoneType has no attribute isoformat' now that parents are often
    deadline-less. Children inherit null when the parent has no deadline.
    """
    parent = Task(title="Tarihsiz proje", discipline="cs",
                  category=TaskCategory.ACADEMIC, deadline=None)
    plan = SubtaskPlan(subtasks=[
        SubtaskItem(title="Adım 1", deadline=None),
        SubtaskItem(title="Adım 2", deadline=None),
    ])
    subtask_llm = _FakeLLM(result=plan)
    subs = await _generate_subtasks(parent, "", subtask_llm, datetime.now())
    assert len(subs) == 2
    assert all(s.deadline is None for s in subs)
    assert all(s.parent_id == parent.id for s in subs)
