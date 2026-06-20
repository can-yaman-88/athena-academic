"""End-to-end HTTP tests via FastAPI TestClient.

These exercise the real request/response path (routing, Pydantic request models,
DB writes) against the temp store configured in conftest. They are the
regression guard for the "every write returns 500 / commands don't work"
experience.
"""

from __future__ import annotations

import pytest

pytest.importorskip("chromadb")  # full app needs the vector store at startup


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    import app as app_module

    with TestClient(app_module.app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_task_crud_cycle(client):
    # create
    r = client.post("/tasks", json={"title": "Proje raporu", "category": "academic",
                                    "subtype": "project"})
    assert r.status_code == 201, r.text
    task = r.json()
    tid = task["id"]

    # patch progress
    r = client.patch(f"/tasks/{tid}", json={"progress": 60})
    assert r.status_code == 200
    assert r.json()["progress"] == 60

    # add a note
    r = client.post(f"/tasks/{tid}/notes", json={"text": "ilerleme kaydı"})
    assert r.status_code == 200

    # complete
    r = client.post(f"/tasks/{tid}/complete")
    assert r.status_code == 200

    # list reflects it
    r = client.get("/tasks")
    assert r.status_code == 200
    assert any(t["id"] == tid for t in r.json()["tasks"])


def test_create_task_without_deadline(client):
    """Regression: a deadline-less task must create and serialize (deadline null)."""
    r = client.post("/tasks", json={"title": "Tarihsiz", "category": "daily"})
    assert r.status_code == 201, r.text
    assert r.json()["deadline"] is None


def test_create_task_blank_deadline_string(client):
    """An empty deadline string (cleared form field) coerces to null, not a 422."""
    r = client.post("/tasks", json={"title": "Boş tarih", "category": "daily",
                                    "deadline": ""})
    assert r.status_code == 201, r.text
    assert r.json()["deadline"] is None


def test_patch_task_clear_deadline(client):
    """Clearing the deadline on update (empty string) nulls it."""
    r = client.post("/tasks", json={"title": "Tarihli", "category": "daily",
                                    "deadline": "2026-07-01T09:00"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    assert r.json()["deadline"] is not None
    r = client.patch(f"/tasks/{tid}", json={"deadline": ""})
    assert r.status_code == 200, r.text
    assert r.json()["deadline"] is None


def test_idea_blank_create_then_update(client):
    r = client.post("/ideas", json={"title": "", "content": ""})
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    r = client.patch(f"/ideas/{iid}", json={"title": "Fikir", "content": "<p>x</p>"})
    assert r.status_code == 200
    assert r.json()["title"] == "Fikir"


def test_workout_create_and_note_save(client):
    r = client.post("/workouts", json={"duration_minutes": 45, "title": "tempo",
                                       "distance_km": 8.0})
    assert r.status_code == 200, r.text
    wid = r.json()["physical_load"]["id"]
    # save a note (the "Failed to fetch" path)
    r = client.patch(f"/workouts/{wid}", json={"note": "<p>iyi geçti</p>"})
    assert r.status_code == 200
    assert r.json()["note"] == "<p>iyi geçti</p>"
    # clearing the note normalizes to null
    r = client.patch(f"/workouts/{wid}", json={"note": ""})
    assert r.status_code == 200
    assert r.json()["note"] is None


def test_daily_note_upsert(client):
    r = client.post("/daily_notes", json={"content": "günlük not"})
    assert r.status_code == 200, r.text
    assert r.json()["content"] == "günlük not"


def test_usage_has_both_cost_keys(client):
    r = client.get("/usage")
    assert r.status_code == 200
    body = r.json()
    # Backend exposes total_cost_usd; cost_usd alias kept for older clients.
    assert "total_cost_usd" in body["pdf"]
    assert "cost_usd" in body["pdf"]
