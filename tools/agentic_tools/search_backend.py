"""Web search + page fetching for Deep Research, backed by a SearXNG instance.

Adapted from Odysseus's ``services/search`` module but trimmed to the two
operations the iterative research engine needs:

* :func:`searxng_search` — query a self-hosted SearXNG instance (JSON API) and
  return a list of ``{"url", "title", "snippet"}`` results.
* :func:`fetch_webpage_content` — fetch a URL and extract readable text + title
  with BeautifulSoup.

Both are async (``httpx``) and degrade gracefully: network/parse errors return
an empty result rather than raising, so a flaky source never aborts a research
run. The SearXNG base URL comes from :data:`config.settings.searxng_url`.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from config import settings

logger = logging.getLogger("athena.research.search")

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 Athena-Academic/1.0"
)


async def searxng_search(
    query: str, max_results: int = 10, *, categories: str = "general"
) -> list[dict[str, str]]:
    """Search ``query`` via SearXNG's JSON API and return ranked web results.

    Returns ``[{"url", "title", "snippet"}, ...]`` (possibly empty). Requires the
    SearXNG instance to have the ``json`` output format enabled.
    """
    query = (query or "").strip()
    if not query:
        return []

    base = settings.searxng_url.rstrip("/")
    params = {
        "q": query,
        "format": "json",
        "categories": categories,
        "safesearch": "0",
    }
    try:
        async with httpx.AsyncClient(
            timeout=20.0, headers={"User-Agent": _USER_AGENT}, follow_redirects=True
        ) as client:
            resp = await client.get(f"{base}/search", params=params)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:  # noqa: BLE001 — best-effort; surfaced as empty
        logger.warning("SearXNG search failed for %r: %s", query[:80], exc)
        return []

    results: list[dict[str, str]] = []
    for item in payload.get("results", []) or []:
        url = (item.get("url") or "").strip()
        if not url:
            continue
        results.append(
            {
                "url": url,
                "title": (item.get("title") or "").strip(),
                "snippet": (item.get("content") or "").strip(),
            }
        )
        if len(results) >= max_results:
            break
    return results


def _extract_readable(html: str) -> tuple[str, str]:
    """Return ``(title, text)`` extracted from raw HTML via BeautifulSoup."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    # Strip non-content nodes that pollute the extracted text.
    for tag in soup(
        ["script", "style", "noscript", "header", "footer", "nav", "aside", "form"]
    ):
        tag.decompose()

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    main = soup.find("article") or soup.find("main") or soup.body or soup
    text = main.get_text(separator="\n", strip=True) if main else ""
    # Collapse runs of blank lines.
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return title, "\n".join(lines)


async def fetch_webpage_content(
    url: str, timeout: int = 10
) -> dict[str, Any]:
    """Fetch ``url`` and return ``{"success", "content", "title", "url"}``.

    Non-HTML responses, network errors and empty bodies all yield
    ``{"success": False, ...}`` so callers can skip them quietly.
    """
    fail = {"success": False, "content": "", "title": "", "url": url}
    try:
        async with httpx.AsyncClient(
            timeout=float(timeout),
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.debug("fetch failed for %s: %s", url, exc)
        return fail

    ctype = resp.headers.get("content-type", "")
    if "html" not in ctype and "text" not in ctype:
        return fail

    try:
        title, text = _extract_readable(resp.text)
    except Exception as exc:  # noqa: BLE001
        logger.debug("parse failed for %s: %s", url, exc)
        return fail

    if not text.strip():
        return fail
    return {"success": True, "content": text, "title": title, "url": url}


__all__ = ["searxng_search", "fetch_webpage_content"]
