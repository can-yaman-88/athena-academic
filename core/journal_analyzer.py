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
You analyze a user's daily journal/idea notebook entry and extract structured items.
You must extract the following items if they are present in the text:

1. GOAL (hedef): If the user explicitly sets a goal or writes "(hedef)".
2. TASK (görev): If the user assigns themselves a task or action item.
3. PROMISE (söz): If the user makes a promise to themselves or someone else.
4. CRITICISM (eleştiri): If the user criticizes something or provides negative feedback.
5. IDEA (fikir): If the user mentions a new idea, a realization, or something they want to try.

Return a list of these items. If none are found, return an empty list. Be concise in the content you extract.
"""


def _default_llm(callbacks: Optional[list] = None) -> Any:
    from core.graph import _make_llm

    llm = _make_llm(
        settings.notes_model, settings.notes_model_max_tokens, callbacks=callbacks
    )
    return llm.with_structured_output(JournalAnalysis, method="function_calling")


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
