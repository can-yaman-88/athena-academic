"""Iterative Deep Research engine (Think → Search → Extract → Synthesize).

Adapted from Odysseus's ``src/deep_research.py`` and refactored to run inside
Athena's LangGraph ``research_node``:

* The LLM is any LangChain chat model (``ChatOpenAI`` pointed at OpenRouter);
  the engine calls ``await llm.ainvoke([...])``.
* Web search + page fetching come from :mod:`tools.agentic_tools.search_backend`
  (SearXNG-backed).
* Live progress is reported through a ``progress`` callback so the node can
  forward phases to the SSE stream.

The public entry point is :meth:`DeepResearchEngine.research`, which returns
``(report_markdown, sources)``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Callable, Optional

from langchain_core.messages import HumanMessage

from config import settings
from core.prompt_templates import (
    RESEARCH_EXTRACT_PROMPT,
    RESEARCH_FINAL_PROMPT,
    RESEARCH_PLAN_PROMPT,
    RESEARCH_QUERY_PROMPT,
    RESEARCH_STOP_PROMPT,
    RESEARCH_SYNTHESIZE_PROMPT,
)
from tools.agentic_tools.search_backend import fetch_webpage_content, searxng_search

logger = logging.getLogger("athena.research")

ProgressFn = Callable[[dict[str, Any]], None]


class DeepResearchEngine:
    """Run multi-round web research and synthesise a Markdown report."""

    def __init__(
        self,
        *,
        llm: Any,
        progress: Optional[ProgressFn] = None,
        min_rounds: Optional[int] = None,
        max_rounds: Optional[int] = None,
        max_urls_per_round: Optional[int] = None,
        max_content_chars: Optional[int] = None,
        time_budget_seconds: Optional[int] = None,
    ) -> None:
        self.llm = llm
        self._progress = progress
        self.min_rounds = min_rounds or settings.research_min_rounds
        self.max_rounds = max_rounds or settings.research_max_rounds
        self.max_urls_per_round = (
            max_urls_per_round or settings.research_max_urls_per_round
        )
        self.max_content_chars = (
            max_content_chars or settings.research_max_content_chars
        )
        self.time_budget = time_budget_seconds or settings.research_time_budget_seconds

        self._start_time = 0.0
        self.urls_fetched: set[str] = set()
        self.sources: list[dict[str, str]] = []

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _emit(self, **kwargs: Any) -> None:
        if self._progress:
            try:
                self._progress(kwargs)
            except Exception:  # noqa: BLE001 — progress must never break research
                pass

    def _time_exceeded(self) -> bool:
        return (time.time() - self._start_time) > self.time_budget

    async def _llm_text(self, prompt: str) -> str:
        """Invoke the chat model with a single user message; return text."""
        resp = await self.llm.ainvoke([HumanMessage(content=prompt)])
        content = getattr(resp, "content", resp)
        if isinstance(content, list):  # some providers return content blocks
            content = " ".join(
                b.get("text", "") if isinstance(b, dict) else str(b) for b in content
            )
        return str(content or "").strip()

    @staticmethod
    def _parse_json_object(text: str) -> Optional[dict]:
        text = re.sub(r"<think(?:ing)?>[\s\S]*?</think(?:ing)?>", "", text, flags=re.I)
        # Direct, fenced, then first {...} span.
        for candidate in (text, *re.findall(r"```(?:json)?\s*([\s\S]*?)```", text)):
            try:
                obj = json.loads(candidate.strip())
                if isinstance(obj, dict):
                    return obj
            except Exception:  # noqa: BLE001
                continue
        a, b = text.find("{"), text.rfind("}")
        if a >= 0 and b > a:
            try:
                obj = json.loads(text[a : b + 1])
                if isinstance(obj, dict):
                    return obj
            except Exception:  # noqa: BLE001
                return None
        return None

    # ------------------------------------------------------------------ #
    # Phases
    # ------------------------------------------------------------------ #
    async def _create_plan(self, question: str) -> str:
        now = datetime.now().date().isoformat()
        try:
            return await self._llm_text(
                RESEARCH_PLAN_PROMPT.format(now=now, question=question)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("plan generation failed: %s", exc)
            return ""

    async def _generate_queries(
        self, question: str, report: str, round_num: int, num_queries: int = 3
    ) -> list[str]:
        now = datetime.now().date().isoformat()
        try:
            raw = await self._llm_text(
                RESEARCH_QUERY_PROMPT.format(
                    now=now,
                    question=question,
                    report=report or "(empty)",
                    round_num=round_num,
                    num_queries=num_queries,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("query generation failed: %s", exc)
            return []
        queries = []
        for line in raw.splitlines():
            q = re.sub(r"^[\s\d\.\-\*\)`\"']+", "", line).strip().strip('"')
            if q:
                queries.append(q)
        return queries[:num_queries] or ([question] if round_num == 1 else [])

    async def _fetch_and_extract(
        self, result: dict[str, str], question: str
    ) -> Optional[dict]:
        url = result["url"]
        title = result.get("title", "")
        self._emit(phase="reading", url=url, title=title or url,
                   total_sources=len(self.urls_fetched))
        page = await fetch_webpage_content(url, timeout=10)
        if not page.get("success") or not page.get("content"):
            return None

        content = page["content"]
        if len(content) > self.max_content_chars:
            content = content[: self.max_content_chars]

        prompt = (
            RESEARCH_EXTRACT_PROMPT.format(goal=question)
            + "\n\n[Web page content]\n"
            + content
        )
        try:
            raw = await self._llm_text(prompt)
        except Exception as exc:  # noqa: BLE001
            logger.warning("extraction LLM failed for %s: %s", url, exc)
            return None

        parsed = self._parse_json_object(raw)
        if not parsed:
            return None
        if parsed.get("relevant") is False:
            return None
        summary = (parsed.get("summary") or "").strip()
        if not summary:
            return None
        return {
            "url": url,
            "title": title or page.get("title", "") or url,
            "summary": summary,
            "evidence": (parsed.get("evidence") or "").strip(),
        }

    async def _search_and_extract(
        self, queries: list[str], question: str
    ) -> list[dict]:
        # Search all queries concurrently.
        search_results = await asyncio.gather(
            *(searxng_search(q, max_results=8) for q in queries),
            return_exceptions=True,
        )

        to_fetch: list[dict[str, str]] = []
        for res in search_results:
            if isinstance(res, Exception) or not res:
                continue
            for r in res:
                url = r.get("url", "")
                if url and url not in self.urls_fetched:
                    self.urls_fetched.add(url)
                    to_fetch.append(r)
                if len(to_fetch) >= self.max_urls_per_round * len(queries):
                    break

        if not to_fetch or self._time_exceeded():
            return []

        extracted = await asyncio.gather(
            *(self._fetch_and_extract(r, question) for r in to_fetch),
            return_exceptions=True,
        )
        findings: list[dict] = []
        for item in extracted:
            if isinstance(item, Exception) or not item:
                continue
            findings.append(item)
            self.sources.append({"url": item["url"], "title": item["title"]})
        return findings

    @staticmethod
    def _format_findings(findings: list[dict]) -> str:
        blocks = []
        for i, f in enumerate(findings, 1):
            block = f"[{i}] {f['title']} ({f['url']})\n{f['summary']}"
            if f.get("evidence"):
                block += f"\nEvidence: {f['evidence']}"
            blocks.append(block)
        return "\n\n".join(blocks)

    async def _synthesize(
        self, question: str, findings: list[dict], report: str
    ) -> str:
        try:
            return await self._llm_text(
                RESEARCH_SYNTHESIZE_PROMPT.format(
                    question=question,
                    report=report or "(empty)",
                    new_findings=self._format_findings(findings),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("synthesis failed: %s", exc)
            return report

    async def _should_stop(self, question: str, report: str, round_num: int) -> bool:
        try:
            raw = await self._llm_text(
                RESEARCH_STOP_PROMPT.format(
                    question=question,
                    report=report,
                    round_num=round_num,
                    max_rounds=self.max_rounds,
                )
            )
        except Exception:  # noqa: BLE001
            return False
        clean = re.sub(r"<think(?:ing)?>[\s\S]*?</think(?:ing)?>", "", raw, flags=re.I)
        clean = re.sub(r"^[\s*_`\"'>#\-]+", "", clean).upper()
        return clean.startswith("YES")

    async def _final_report(self, question: str, report: str) -> str:
        now = datetime.now().date().isoformat()
        try:
            return await self._llm_text(
                RESEARCH_FINAL_PROMPT.format(now=now, question=question, report=report)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("final polish failed: %s", exc)
            return report

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #
    async def research(self, question: str) -> tuple[str, list[dict]]:
        """Run the iterative research loop. Returns ``(report, sources)``."""
        self._start_time = time.time()
        findings: list[dict] = []
        report = ""

        self._emit(phase="planning")
        await self._create_plan(question)

        for round_num in range(1, self.max_rounds + 1):
            if self._time_exceeded():
                logger.info("research time budget reached at round %d", round_num)
                break

            self._emit(phase="searching", round=round_num,
                       total_sources=len(self.urls_fetched))
            queries = await self._generate_queries(question, report, round_num)
            if not queries:
                break

            round_findings = await self._search_and_extract(queries, question)
            if round_findings:
                findings.extend(round_findings)
                self._emit(phase="reading", round=round_num,
                           new_sources=len(round_findings),
                           total_sources=len(self.urls_fetched),
                           total_findings=len(findings))

            if findings:
                self._emit(phase="analyzing", round=round_num,
                           total_findings=len(findings))
                report = await self._synthesize(question, findings, report)

            if round_num >= self.min_rounds and report:
                if await self._should_stop(question, report, round_num):
                    break

        self._emit(phase="writing", total_sources=len(self.urls_fetched),
                   total_findings=len(findings))
        if not report:
            if not findings:
                return (
                    "Bu konu hakkında web araması ile bilgi toplanamadı "
                    "(arama servisi kapalı olabilir).",
                    [],
                )
            report = self._format_findings(findings)

        final = await self._final_report(question, report)
        self._emit(phase="done", total_sources=len(self.urls_fetched),
                   total_findings=len(findings))

        # De-duplicate sources by URL, preserving order.
        seen: set[str] = set()
        unique_sources = []
        for s in self.sources:
            if s["url"] not in seen:
                seen.add(s["url"])
                unique_sources.append(s)
        return final, unique_sources


__all__ = ["DeepResearchEngine"]
