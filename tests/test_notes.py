"""Notion-style nested Notes: CRUD, depth limit, recursive delete."""

from __future__ import annotations

import pytest

from core.schemas import NotePage


async def test_note_crud_roundtrip(db):
    note = NotePage(title="İlk Not", content="<p>merhaba</p>")
    await db.upsert_note(note)
    fetched = await db.get_note(note.id)
    assert fetched.title == "İlk Not"
    assert fetched.depth == 0
    assert fetched.parent_id is None

    notes = await db.list_notes()
    assert any(n.id == note.id for n in notes)

    await db.delete_note(note.id)
    assert all(n.id != note.id for n in await db.list_notes())


async def test_recursive_delete_removes_descendants(db):
    root = NotePage(title="kök", depth=0)
    await db.upsert_note(root)
    child = NotePage(title="çocuk", parent_id=root.id, depth=1)
    await db.upsert_note(child)
    grandchild = NotePage(title="torun", parent_id=child.id, depth=2)
    await db.upsert_note(grandchild)

    assert {n.id for n in await db.list_child_notes(root.id)} == {child.id}
    await db.delete_note(root.id)
    remaining = {n.id for n in await db.list_notes()}
    assert root.id not in remaining
    assert child.id not in remaining
    assert grandchild.id not in remaining


# --- HTTP: depth limit enforcement ---------------------------------------- #
@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    import app as app_module

    with TestClient(app_module.app) as c:
        yield c


def test_notes_http_depth_limit(client):
    a = client.post("/notes", json={"title": "A"}).json()
    assert a["depth"] == 0
    b = client.post("/notes", json={"title": "B", "parent_id": a["id"]}).json()
    assert b["depth"] == 1
    c = client.post("/notes", json={"title": "C", "parent_id": b["id"]}).json()
    assert c["depth"] == 2
    # 4th level must be rejected.
    r = client.post("/notes", json={"title": "D", "parent_id": c["id"]})
    assert r.status_code == 400

    # children endpoint + recursive delete via HTTP
    kids = client.get(f"/notes/{a['id']}/children").json()
    assert [k["id"] for k in kids] == [b["id"]]
    assert client.delete(f"/notes/{a['id']}").status_code == 200
    assert client.get(f"/notes/{c['id']}").status_code == 404


def test_inline_upload_serves_url(client):
    files = {"file": ("pic.png", b"\x89PNG\r\n\x1a\n fake", "image/png")}
    r = client.post("/uploads/inline", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "image"
    assert body["url"].startswith("/uploads/files/")
    # the returned URL is actually served
    assert client.get(body["url"]).status_code == 200
