"""Agentic tools for Athena-Academic.

Exposes the Hardcore Mode chain and its Pydantic I/O models. ``AGENTIC_TOOLS`` is
the (currently empty) list of bindable LangChain ``@tool`` functions for the
LangGraph agent — kept so tools can be re-added without touching call sites.
"""

from tools.agentic_tools.hardcore_mode import (
    HARDCORE_MODE_SYSTEM_PROMPT,
    HardcoreQuery,
    HardcoreResponse,
    ask_hardcore,
    build_hardcore_chain,
)

# Bindable tools for the LangGraph agent (Hardcore Mode is a chain, not a tool).
AGENTIC_TOOLS: list = []

__all__ = [
    "AGENTIC_TOOLS",
    "HARDCORE_MODE_SYSTEM_PROMPT",
    "HardcoreQuery",
    "HardcoreResponse",
    "ask_hardcore",
    "build_hardcore_chain",
]
