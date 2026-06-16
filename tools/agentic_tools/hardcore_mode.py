"""Hardcore Mode — a Socratic tutor chain that refuses to write code.

When Hardcore Mode is enabled, Jarvis-Academic must not hand the user answers or
code. Instead it interrogates their reasoning, points out logical flaws as
questions, demands that they perform linear-algebra/physics calculations by hand,
and points them at the relevant documentation. This module provides the system
prompt, the validated I/O models, and a chain factory.

The no-code rule is enforced on the *output*: :class:`HardcoreResponse` strips any
fenced code block the model emits and flags it, so the guarantee holds even if the
LLM slips.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, ConfigDict, Field, model_validator

HARDCORE_MODE_SYSTEM_PROMPT = """\
You are Jarvis-Academic operating in HARDCORE MODE. Your job is to make the user
think for themselves, not to do their work for them.

ABSOLUTE RULES:
1. You are STRICTLY FORBIDDEN from generating code snippets of any kind — no
   functions, no examples, no pseudocode that could be copy-pasted. If the user
   asks for code, refuse and redirect them to reason it out themselves.
2. Act as a Socratic tutor: respond primarily with probing questions that expose
   the gaps and logical flaws in the user's reasoning. Do not state conclusions
   they can reach themselves.
3. For linear algebra, physics, and other quantitative problems, DEMAND that the
   user perform the calculation by hand. Ask them to show each step; do not do
   the arithmetic for them.
4. When they need a fact or API, point them to the official documentation (name
   the source/section) rather than reproducing it.

Be rigorous, direct, and encouraging — the goal is mastery, not comfort.\
"""

SOCRATIC_NUDGE = (
    "In Hardcore Mode I will not hand you code. Describe the underlying logic in "
    "plain words and walk me through your reasoning step by step — what is the "
    "first thing that must be true?"
)

# Matches triple-backtick fenced code blocks (the form copy-pasteable code takes).
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)


def enforce_no_code(text: str) -> tuple[str, bool]:
    """Strip fenced code blocks from ``text``.

    Returns the cleaned text and whether any code block was found and removed.
    """
    cleaned = _CODE_FENCE_RE.sub(
        "[code snippet removed — Hardcore Mode forbids code]", text
    )
    return cleaned, cleaned != text


class HardcoreQuery(BaseModel):
    """Validated input to the Hardcore Mode chain."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(
        min_length=1, description="The user's question or problem statement."
    )
    subject: Optional[str] = Field(
        default=None, description="Optional subject area (e.g. 'linear algebra')."
    )


class HardcoreResponse(BaseModel):
    """Validated Hardcore Mode reply with the no-code guarantee enforced."""

    model_config = ConfigDict(extra="forbid")

    response: str = Field(description="The Socratic, code-free tutor response.")
    contained_forbidden_code: bool = Field(
        default=False,
        description="True if the raw model output contained code that was stripped.",
    )

    @model_validator(mode="before")
    @classmethod
    def _strip_forbidden_code(cls, data: Any) -> Any:
        """Remove any fenced code, flagging it and appending a Socratic nudge."""
        if isinstance(data, str):
            data = {"response": data}
        if not isinstance(data, dict):
            return data
        text = data.get("response", "") or ""
        cleaned, had_code = enforce_no_code(text)
        if had_code:
            cleaned = (cleaned.rstrip() + "\n\n" + SOCRATIC_NUDGE).strip()
        return {**data, "response": cleaned, "contained_forbidden_code": had_code}


def _to_hardcore_response(message: Any) -> HardcoreResponse:
    """Convert an LLM message (or string) into a validated HardcoreResponse."""
    content = getattr(message, "content", message)
    if not isinstance(content, str):
        content = str(content)
    return HardcoreResponse(response=content)


def build_hardcore_chain(llm: Any = None) -> Runnable:
    """Build the Hardcore Mode chain: prompt | llm | no-code validator.

    Args:
        llm: A chat model runnable. Defaults to the configured OpenRouter chat
            model (``core.graph._default_chat_llm``). Inject a fake for testing.

    Returns:
        A runnable accepting ``{"question": str, "subject": str}`` and returning a
        validated :class:`HardcoreResponse`.
    """
    if llm is None:
        from core.graph import _default_chat_llm

        llm = _default_chat_llm()

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", HARDCORE_MODE_SYSTEM_PROMPT),
            ("human", "Subject: {subject}\n\nQuestion: {question}"),
        ]
    )
    return prompt | llm | RunnableLambda(_to_hardcore_response)


def ask_hardcore(
    question: str,
    subject: Optional[str] = None,
    *,
    chain: Optional[Runnable] = None,
    llm: Any = None,
) -> HardcoreResponse:
    """Validate the query and run it through the Hardcore Mode chain.

    Args:
        question: The user's question or problem.
        subject: Optional subject area for context.
        chain: A prebuilt chain to reuse; built on demand if omitted.
        llm: LLM to use when building the chain (ignored if ``chain`` is given).

    Returns:
        A validated :class:`HardcoreResponse`.
    """
    query = HardcoreQuery(question=question, subject=subject)
    chain = chain or build_hardcore_chain(llm=llm)
    return chain.invoke(
        {"question": query.question, "subject": query.subject or "general"}
    )


__all__ = [
    "HARDCORE_MODE_SYSTEM_PROMPT",
    "HardcoreQuery",
    "HardcoreResponse",
    "ask_hardcore",
    "build_hardcore_chain",
    "enforce_no_code",
]
