import logging
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from config import settings
from core.schemas import JournalItemType

logger = logging.getLogger("athena.journals")


class JournalItemPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: JournalItemType = Field(description="Category of the extracted item.")
    content: str = Field(description="The extracted content (idea, promise, etc).")


class JournalAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[JournalItemPayload] = Field(default_factory=list)


JOURNAL_ANALYSIS_SYSTEM_PROMPT = """\
You are Athena's journal-analysis engine. You read a user's daily journal / idea
notebook ("günüm") entry and extract structured items. Extract every item of the
following kinds that is genuinely present — a single entry may contain several:

1. GOAL (hedef): the user sets a goal or intention, or explicitly tags "(hedef)".
2. CRITICISM (eleştiri): the user criticizes something or gives negative feedback
   (about themselves, their day, a tool, or others).
3. IDEA (fikir): the user mentions a new idea, a realization, or something they
   want to try or explore.

Guidelines:
- Quote the user's own meaning faithfully; summarize concisely, do not embellish
  or invent items that are not in the text.
- Do NOT extract tasks, to-dos, or promises — those are handled elsewhere.
- Keep each 'content' to one tight sentence in the user's language (usually Turkish).
- If the entry contains none of these item types, return an empty list.
"""


def _default_llm(callbacks: Optional[list] = None) -> Any:
    from core.graph import _make_llm, _make_structured_llm

    llm = _make_llm(
        settings.notes_model, settings.notes_model_max_tokens, callbacks=callbacks
    )
    return _make_structured_llm(llm, JournalAnalysis)


async def analyze_journal(
    journal_content: str,
    *,
    llm: Any = None,
    callbacks: Optional[list] = None,
) -> JournalAnalysis:
    """Run journal analysis over a single journal entry text."""
    if not journal_content.strip():
        return JournalAnalysis()

    if llm is None:
        llm = _default_llm(callbacks)

    result: Optional[JournalAnalysis] = await llm.ainvoke(
        [
            SystemMessage(content=JOURNAL_ANALYSIS_SYSTEM_PROMPT),
            HumanMessage(content=journal_content),
        ]
    )
    return result or JournalAnalysis()
