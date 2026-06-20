"""Ideas, daily notes, and journal persistence."""

from __future__ import annotations

from datetime import date

import pytest

from core.schemas import DailyNote, Idea, Journal


async def test_idea_create_empty_then_update(db):
    """Regression: creating a blank idea (the '+ Fikir Ekle' flow) must work."""
    idea = Idea(title="", content="")
    await db.upsert_idea(idea)
    fetched = await db.get_idea(idea.id)
    assert fetched.title == ""

    fetched.title = "Yeni fikir"
    fetched.content = "<p>içerik</p>"
    await db.upsert_idea(fetched)
    again = await db.get_idea(idea.id)
    assert again.title == "Yeni fikir"
    assert again.content == "<p>içerik</p>"


async def test_idea_delete(db):
    idea = Idea(title="Sil", content="")
    await db.upsert_idea(idea)
    await db.delete_idea(idea.id)
    assert all(i.id != idea.id for i in await db.list_ideas())


async def test_daily_note_upsert_is_idempotent_per_date(db):
    today = date.today()
    await db.upsert_daily_note(DailyNote(date=today, content="ilk"))
    notes = await db.get_daily_notes()
    existing = next(n for n in notes if n.date == today)
    existing.content = "güncel"
    await db.upsert_daily_note(existing)
    notes = await db.get_daily_notes()
    same_day = [n for n in notes if n.date == today]
    assert len(same_day) == 1
    assert same_day[0].content == "güncel"


async def test_journal_roundtrip(db):
    journal = Journal(date="2026-06-20", content="bugün koştum")
    await db.upsert_journal(journal)
    fetched = await db.get_journal(journal.id)
    assert fetched.content == "bugün koştum"
    assert fetched.processed is False
