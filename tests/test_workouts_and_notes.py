"""Workout persistence + note empty-string normalization regressions."""

from __future__ import annotations

from datetime import date

import pytest

from core.schemas import PhysicalLoad, WorkoutStatus


def test_empty_note_normalized_to_none():
    """Regression: blank rich-text notes must become NULL, not ''."""
    assert PhysicalLoad(date=date.today(), duration_minutes=30, note="").note is None
    assert PhysicalLoad(date=date.today(), duration_minutes=30, note="   ").note is None
    assert PhysicalLoad(date=date.today(), duration_minutes=30, note="<p></p>").note is None
    assert PhysicalLoad(date=date.today(), duration_minutes=30, note="<p><br></p>").note is None


def test_real_note_preserved():
    load = PhysicalLoad(date=date.today(), duration_minutes=30, note="<p>iyi geçti</p>")
    assert load.note == "<p>iyi geçti</p>"


def test_note_cleared_on_assignment():
    """validate_assignment=True must also normalize on later mutation."""
    load = PhysicalLoad(date=date.today(), duration_minutes=30, note="<p>x</p>")
    load.note = ""
    assert load.note is None


async def test_workout_roundtrip(db):
    load = PhysicalLoad(date=date.today(), duration_minutes=45, title="tempo",
                        distance_km=8.0, status=WorkoutStatus.COMPLETED)
    await db.create_physical_load(load)
    fetched = await db.get_physical_load(load.id)
    assert fetched.title == "tempo"
    assert fetched.distance_km == 8.0


async def test_workout_note_blank_roundtrips_as_none(db):
    load = PhysicalLoad(date=date.today(), duration_minutes=30, note="")
    await db.create_physical_load(load)
    fetched = await db.get_physical_load(load.id)
    assert fetched.note is None
