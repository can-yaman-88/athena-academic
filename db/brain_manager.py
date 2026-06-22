"""Brain — Athena's long-term memory of durable facts about the user.

The Brain stores short "facts" (e.g. *"User is studying Computer Science"*,
*"Prefers bullet-point answers"*) so the agent can recall and personalise across
sessions. Two stores are kept in sync:

* **SQLite** (``brain_facts`` table, owned by :class:`db.sqlite_manager.SQLiteManager`)
  is the canonical record used by the Brain modal to list / edit / delete facts.
* **ChromaDB** (a dedicated collection, via :class:`db.chroma_manager.ChromaManager`)
  holds embeddings so the chat node can semantically recall relevant facts.

Each fact's SQLite ``id`` is reused as the Chroma ``doc_id`` so the two stores
stay aligned on add and delete. ChromaDB's API is synchronous, so blocking calls
are dispatched to a thread with :func:`asyncio.to_thread`.

Fact extraction from conversations is **manual / on-demand**: call
:meth:`extract_from_messages` (wired to a button in the UI), not automatically
after every turn.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Optional
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage

from config import settings
from db.chroma_manager import ChromaManager

logger = logging.getLogger("athena.brain")

# Prompt that mines a conversation transcript for durable, personal facts.
EXTRACT_SYSTEM_PROMPT = """\
You extract durable, long-term facts about the USER from a conversation, so an \
assistant can remember them in future sessions.

Return a STRICT JSON array. Each element is an object:
{"text": "<a single concise fact about the user, written in the third person>",
 "category": "identity|preference|fact|goal|project"}

Rules:
- Only include stable, reusable facts (who the user is, lasting preferences, \
ongoing goals/projects, important personal context).
- Do NOT include transient details, one-off task content, or facts about the \
assistant.
- Keep each fact short (one sentence). Write in the user's language.
- If there is nothing durable to remember, return [].
Return ONLY the JSON array."""


class BrainManager:
    """Long-term memory backed by SQLite (canonical) + ChromaDB (semantic)."""

    def __init__(
        self,
        sqlite_manager: Any,
        *,
        chroma: Optional[ChromaManager] = None,
        extractor_llm: Any = None,
    ) -> None:
        self._db = sqlite_manager
        self._chroma = chroma or ChromaManager(
            collection_name=settings.brain_collection
        )
        self._extractor_llm = extractor_llm

    def initialize(self) -> None:
        """Initialise the underlying Chroma collection (blocking)."""
        self._chroma.initialize()

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #
    async def list_facts(self) -> list[dict]:
        return await self._db.list_brain_facts()

    async def add_fact(
        self,
        text: str,
        *,
        category: str = "fact",
        source: str = "manual",
        pinned: bool = False,
        fact_id: Optional[str] = None,
    ) -> dict:
        """Persist a fact in SQLite and index it in ChromaDB."""
        text = (text or "").strip()
        if not text:
            raise ValueError("Fact text must be non-empty.")
        fact_id = fact_id or uuid4().hex
        fact = await self._db.upsert_brain_fact(
            {
                "id": fact_id,
                "text": text,
                "category": category,
                "source": source,
                "pinned": pinned,
            }
        )
        try:
            await asyncio.to_thread(
                self._chroma.add_document, text, {"fact_id": fact_id}, doc_id=fact_id
            )
        except Exception:  # noqa: BLE001 — embedding is best-effort
            logger.exception("failed to index brain fact %s in chroma", fact_id)
        return fact

    async def update_fact(
        self,
        fact_id: str,
        *,
        text: Optional[str] = None,
        category: Optional[str] = None,
        pinned: Optional[bool] = None,
    ) -> Optional[dict]:
        existing = await self._db.get_brain_fact(fact_id)
        if existing is None:
            return None
        if text is not None:
            existing["text"] = text.strip()
        if category is not None:
            existing["category"] = category
        if pinned is not None:
            existing["pinned"] = pinned
        fact = await self._db.upsert_brain_fact(existing)
        # Re-index: drop and re-add the embedding so it tracks the new text.
        try:
            await asyncio.to_thread(self._chroma.delete_document, fact_id)
            await asyncio.to_thread(
                self._chroma.add_document,
                fact["text"],
                {"fact_id": fact_id},
                doc_id=fact_id,
            )
        except Exception:  # noqa: BLE001
            logger.exception("failed to re-index brain fact %s", fact_id)
        return fact

    async def delete_fact(self, fact_id: str) -> None:
        await self._db.delete_brain_fact(fact_id)
        try:
            await asyncio.to_thread(self._chroma.delete_document, fact_id)
        except Exception:  # noqa: BLE001
            logger.exception("failed to remove brain fact %s from chroma", fact_id)

    # ------------------------------------------------------------------ #
    # Recall + extraction
    # ------------------------------------------------------------------ #
    async def query_relevant(self, text: str, n: int = 5) -> list[dict]:
        """Return up to ``n`` stored facts semantically relevant to ``text``."""
        text = (text or "").strip()
        if not text:
            return []
        try:
            results = await asyncio.to_thread(
                self._chroma.query_documents, text, n
            )
        except Exception:  # noqa: BLE001
            return []
        facts: list[dict] = []
        seen: set[str] = set()
        for r in results:
            fid = (r.get("metadata") or {}).get("fact_id") or (
                r.get("metadata") or {}
            ).get("doc_id")
            if not fid or fid in seen:
                continue
            seen.add(fid)
            facts.append({"id": fid, "text": r.get("text", ""),
                          "distance": r.get("distance")})
        return facts

    async def _is_duplicate(self, text: str) -> bool:
        nearest = await self.query_relevant(text, n=1)
        if not nearest:
            return False
        dist = nearest[0].get("distance")
        return dist is not None and dist <= settings.brain_dedup_distance

    async def extract_from_messages(
        self, messages: list[dict], *, llm: Any = None
    ) -> list[dict]:
        """Mine recent chat messages for durable facts and store new ones.

        ``messages`` is a list of ``{"role", "text"}`` dicts (Athena chat lines).
        Returns the facts that were newly added (after dedup). On-demand only.
        """
        llm = llm or self._extractor_llm
        if llm is None:
            raise RuntimeError("Brain extractor LLM is not configured.")

        transcript = "\n\n".join(
            f"{m.get('role', '?')}: {m.get('text', '')}"
            for m in messages
            if (m.get("text") or "").strip()
        )
        if not transcript.strip():
            return []

        try:
            resp = await llm.ainvoke(
                [
                    SystemMessage(content=EXTRACT_SYSTEM_PROMPT),
                    HumanMessage(
                        content="Conversation to analyze:\n\n"
                        + transcript
                        + "\n\nReturn the JSON array of durable facts now (or [])."
                    ),
                ]
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("brain extraction LLM failed: %s", exc)
            return []

        raw = getattr(resp, "content", resp)
        if isinstance(raw, list):
            raw = " ".join(
                b.get("text", "") if isinstance(b, dict) else str(b) for b in raw
            )
        facts = self._parse_fact_array(str(raw or ""))

        added: list[dict] = []
        for item in facts:
            if isinstance(item, str):
                text, category = item, "fact"
            elif isinstance(item, dict):
                text = (item.get("text") or "").strip()
                category = item.get("category", "fact")
            else:
                continue
            if len(text) < 5:
                continue
            if await self._is_duplicate(text):
                continue
            fact = await self.add_fact(text, category=category, source="auto")
            added.append(fact)
        return added

    @staticmethod
    def _parse_fact_array(text: str) -> list:
        text = re.sub(r"<think(?:ing)?>[\s\S]*?</think(?:ing)?>", "", text, flags=re.I)
        for candidate in (text, *re.findall(r"```(?:json)?\s*([\s\S]*?)```", text)):
            try:
                obj = json.loads(candidate.strip())
                if isinstance(obj, list):
                    return obj
            except Exception:  # noqa: BLE001
                continue
        a, b = text.find("["), text.rfind("]")
        if a >= 0 and b > a:
            try:
                obj = json.loads(text[a : b + 1])
                if isinstance(obj, list):
                    return obj
            except Exception:  # noqa: BLE001
                return []
        return []


__all__ = ["BrainManager", "EXTRACT_SYSTEM_PROMPT"]
