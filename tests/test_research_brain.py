"""Deep Research engine + Brain manager + research_node coverage.

Network and LLM calls are faked, so these run fully offline and deterministically.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage

from tools.agentic_tools.deep_research import DeepResearchEngine
from tools.agentic_tools import search_backend
from tools.agentic_tools import deep_research as dr_module
from db.brain_manager import BrainManager


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class FakeLLM:
    """A chat model whose reply is computed from the last message's content."""

    def __init__(self, fn):
        self._fn = fn
        self.calls: list[str] = []

    async def ainvoke(self, messages):
        prompt = messages[-1].content
        self.calls.append(prompt)
        return SimpleNamespace(content=self._fn(prompt))


def _research_reply(prompt: str) -> str:
    p = prompt.lower()
    if "search queries" in p:
        return "kuantum bilgisayar temelleri\nkuantum üstünlüğü 2025"
    if "extract information relevant" in p or "strict json object" in p:
        return '{"summary": "Kuantum bilgisayarlar kübit kullanır.", "evidence": "kübit", "relevant": true}'
    if "improving a research report" in p:
        return "# Rapor\nKuantum bilgisayarlar kübitlerle çalışır [1]."
    if "decide whether" in p or "yes or no" in p:
        return "YES"
    if "finalizing" in p:
        return "# Nihai Rapor\nKapsamlı özet [1]."
    return "- alt soru 1\n- alt soru 2"  # plan


class FakeChroma:
    """In-memory stand-in for ChromaManager (no embedding model needed)."""

    def __init__(self):
        self.docs: dict[str, str] = {}

    def initialize(self):
        pass

    def add_document(self, text, metadata=None, doc_id=None):
        self.docs[doc_id] = text
        return [f"{doc_id}:0"]

    def query_documents(self, query, n_results=3):
        q = query.strip().lower()
        out = []
        for did, txt in self.docs.items():
            t = txt.lower()
            dist = 0.0 if (q in t or t in q) else 0.9
            out.append({"id": f"{did}:0", "text": txt,
                        "metadata": {"fact_id": did, "doc_id": did}, "distance": dist})
        out.sort(key=lambda r: r["distance"])
        return out[:n_results]

    def delete_document(self, doc_id):
        self.docs.pop(doc_id, None)

    def count(self):
        return len(self.docs)


@pytest.fixture
def patch_search(monkeypatch):
    """Fake SearXNG + page fetch inside the deep_research module namespace."""
    async def fake_search(query, max_results=8, **kw):
        return [
            {"url": "https://example.com/a", "title": "A", "snippet": "s"},
            {"url": "https://example.com/b", "title": "B", "snippet": "s"},
        ]

    async def fake_fetch(url, timeout=10):
        return {"success": True, "content": "Kuantum bilgisayarlar kübit kullanır. " * 20,
                "title": "Sayfa", "url": url}

    monkeypatch.setattr(dr_module, "searxng_search", fake_search)
    monkeypatch.setattr(dr_module, "fetch_webpage_content", fake_fetch)


# --------------------------------------------------------------------------- #
# Deep Research engine
# --------------------------------------------------------------------------- #
def test_parse_json_object_variants():
    p = DeepResearchEngine._parse_json_object
    assert p('{"a": 1}') == {"a": 1}
    assert p('```json\n{"a": 2}\n```') == {"a": 2}
    assert p('noise before {"a": 3} after') == {"a": 3}
    assert p("<think>hmm</think>{\"a\": 4}") == {"a": 4}
    assert p("not json at all") is None


async def test_research_full_loop(patch_search):
    events: list[dict] = []
    engine = DeepResearchEngine(
        llm=FakeLLM(_research_reply),
        progress=lambda d: events.append(d),
        min_rounds=1,
        max_rounds=2,
    )
    report, sources = await engine.research("Kuantum bilgisayarlar nedir?")

    assert "Nihai Rapor" in report
    assert len(sources) == 2
    assert {s["url"] for s in sources} == {"https://example.com/a", "https://example.com/b"}
    phases = {e.get("phase") for e in events}
    assert {"planning", "searching", "reading", "analyzing", "writing", "done"} <= phases


async def test_research_no_results_is_graceful(monkeypatch):
    async def empty_search(query, max_results=8, **kw):
        return []

    monkeypatch.setattr(dr_module, "searxng_search", empty_search)
    engine = DeepResearchEngine(llm=FakeLLM(_research_reply), min_rounds=1, max_rounds=1)
    report, sources = await engine.research("boş konu")
    assert sources == []
    assert "bilgi toplanamadı" in report


def test_extract_readable_strips_chrome():
    html = """
    <html><head><title>Başlık</title></head>
    <body><nav>menu</nav><script>var x=1;</script>
    <article><p>Önemli içerik burada.</p></article>
    <footer>alt</footer></body></html>
    """
    title, text = search_backend._extract_readable(html)
    assert title == "Başlık"
    assert "Önemli içerik burada." in text
    assert "menu" not in text and "var x" not in text


# --------------------------------------------------------------------------- #
# Brain manager
# --------------------------------------------------------------------------- #
@pytest.fixture
async def brain(db):
    mgr = BrainManager(db, chroma=FakeChroma())
    mgr.initialize()
    return mgr


async def test_brain_add_list_query_delete(brain):
    fact = await brain.add_fact("Kullanıcı bilgisayar mühendisliği okuyor", category="identity")
    listed = await brain.list_facts()
    assert any(f["id"] == fact["id"] for f in listed)

    hits = await brain.query_relevant("bilgisayar mühendisliği")
    assert any(h["id"] == fact["id"] for h in hits)

    await brain.delete_fact(fact["id"])
    assert all(f["id"] != fact["id"] for f in await brain.list_facts())


async def test_brain_update_fact(brain):
    fact = await brain.add_fact("eski metin")
    updated = await brain.update_fact(fact["id"], text="yeni metin", pinned=True)
    assert updated["text"] == "yeni metin"
    assert updated["pinned"] is True


async def test_brain_extract_and_dedup(brain):
    def extractor(prompt: str) -> str:
        return (
            '[{"text": "Kullanıcı Python tercih ediyor", "category": "preference"},'
            ' {"text": "Kullanıcı bullet point sever", "category": "preference"}]'
        )

    history = [
        {"role": "user", "text": "Python'da kod yazmayı seviyorum ve bullet point isterim"},
        {"role": "assistant", "text": "Tamam."},
    ]
    added = await brain.extract_from_messages(history, llm=FakeLLM(extractor))
    assert len(added) == 2

    # Re-running with the same facts must dedup (vector distance below threshold).
    again = await brain.extract_from_messages(history, llm=FakeLLM(extractor))
    assert again == []


async def test_brain_extract_requires_llm(db):
    mgr = BrainManager(db, chroma=FakeChroma())  # no extractor llm
    with pytest.raises(RuntimeError):
        await mgr.extract_from_messages([{"role": "user", "text": "hi"}])


# --------------------------------------------------------------------------- #
# research_node (graph integration)
# --------------------------------------------------------------------------- #
async def test_research_node_saves_idea(db, patch_search):
    from core.graph import research_node

    state = {"messages": [HumanMessage(content="/arastir kuantum bilgisayarlar")]}
    result = await research_node(
        state, research_llm=FakeLLM(_research_reply), sqlite_manager=db
    )

    msg = result["messages"][0].content
    assert "Nihai Rapor" in msg
    assert "Kaynaklar" in msg  # sources appended
    assert result["active_tool"] == "deep_research"

    ideas = await db.list_ideas()
    assert len(ideas) == 1
    assert "kuantum" in ideas[0].title.lower()


async def test_research_node_without_llm_is_mock(db):
    from core.graph import research_node

    state = {"messages": [HumanMessage(content="/arastir x")]}
    result = await research_node(state, research_llm=None, sqlite_manager=db)
    assert "[mock]" in result["messages"][0].content
