"""Agentic tools for Athena-Academic.

Exposes the bindable LangChain ``@tool`` functions as ``AGENTIC_TOOLS`` (ready to
attach to the LangGraph agent), plus the Hardcore Mode chain and all Pydantic I/O
models.
"""

from tools.agentic_tools.hardcore_mode import (
    HARDCORE_MODE_SYSTEM_PROMPT,
    HardcoreQuery,
    HardcoreResponse,
    ask_hardcore,
    build_hardcore_chain,
)
from tools.agentic_tools.load_balancer import (
    CognitiveAllowanceInput,
    CognitiveAllowanceResult,
    calculate_cognitive_allowance,
)

# Bindable tools for the LangGraph agent (Hardcore Mode is a chain, not a tool).
AGENTIC_TOOLS = [calculate_cognitive_allowance]

__all__ = [
    "AGENTIC_TOOLS",
    "CognitiveAllowanceInput",
    "CognitiveAllowanceResult",
    "HARDCORE_MODE_SYSTEM_PROMPT",
    "HardcoreQuery",
    "HardcoreResponse",
    "ask_hardcore",
    "build_hardcore_chain",
    "calculate_cognitive_allowance",
]
