"""Bound Python tools the graph's tool nodes execute.

These are real LangChain tools (decorated with ``@tool``, complete signatures and
schemas) so the routing and dispatch logic is fully exercised end to end. Their
*bodies* are mocked for Phase 2 — they return clear, well-formed strings instead
of touching the database or filesystem. The real implementations (ChromaDB
ingestion for PDFs, :meth:`db.sqlite_manager.SQLiteManager.create_task` for tasks)
arrive in a later phase; the tool contracts here are designed to match them.
"""

from __future__ import annotations

from langchain_core.tools import tool


@tool
def process_pdf(file_path: str) -> str:
    """Extract and ingest the text of an academic PDF into the knowledge base.

    Args:
        file_path: Absolute or relative path to the PDF document to process.

    Returns:
        A human-readable summary of what was ingested.
    """
    # Phase 2 mock: real ingestion (chunk + embed into ChromaDB) lands later.
    return (
        f"[mock] Queued PDF '{file_path}' for ingestion. "
        "Document parsing and embedding are not yet wired up in Phase 2."
    )


@tool
def add_task(
    title: str,
    deadline: str,
    discipline: str,
    estimated_hours: float,
) -> str:
    """Create a new academic task and schedule it for tracking.

    Args:
        title: Short description of the task.
        deadline: Due date/time in ISO 8601 format (e.g. '2026-07-01T09:00').
        discipline: Subject or field the task belongs to.
        estimated_hours: Estimated effort in hours (must be positive).

    Returns:
        A human-readable confirmation of the created task.
    """
    # Phase 2 mock: real persistence via SQLiteManager.create_task lands later.
    return (
        f"[mock] Created task '{title}' for {discipline}, due {deadline}, "
        f"estimated {estimated_hours}h. Persistence is not yet wired up in Phase 2."
    )


# Tools grouped by the node that owns them, so graph wiring stays declarative.
PDF_TOOLS = [process_pdf]
TASK_TOOLS = [add_task]


__all__ = ["PDF_TOOLS", "TASK_TOOLS", "add_task", "process_pdf"]
