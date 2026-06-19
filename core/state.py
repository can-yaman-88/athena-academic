"""Graph state definition for the Athena-Academic agent.

:class:`AthenaState` is the single mutable object threaded through every node of
the LangGraph workflow. State transitions are **immutable by construction**: each
node returns a *partial* mapping of the keys it wants to change, and LangGraph
merges those into a new state. The ``messages`` channel uses the ``add_messages``
reducer, so returning ``{"messages": [msg]}`` appends rather than overwriting the
conversation history.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

try:  # Python 3.11+ has NotRequired in typing; fall back for older runtimes.
    from typing import NotRequired
except ImportError:  # pragma: no cover - Python < 3.11
    from typing_extensions import NotRequired

from core.schemas import Task

# Valid routing destinations the router may choose. Kept here (not in graph.py)
# so both the state and the structured-output schema share one definition.
RouteTarget = Literal[
    "chat_node", "pdf_tool_node", "task_tool_node", "workout_tool_node",
    "session_node", "idea_extractor_node"
]




class AthenaState(TypedDict):
    """State threaded through the Athena-Academic graph.

    Only ``messages`` is required to invoke the graph; every other key is
    populated by nodes as the run progresses, so they are ``NotRequired``.
    """

    # Conversation history. The add_messages reducer appends new messages
    # immutably and assigns ids, so nodes never mutate this list in place.
    messages: Annotated[list[AnyMessage], add_messages]

    # The task currently in focus, when one is active (reuses the Phase 1 schema).
    current_task: NotRequired[Optional[Task]]

    # Name of the tool the most recent tool node executed (or None for chat).
    active_tool: NotRequired[Optional[str]]



    # The destination the router selected; read by the conditional edge.
    route: NotRequired[Optional[RouteTarget]]

    # Document context retrieved from the vector store for the chat node.
    retrieved_context: NotRequired[Optional[str]]

    # Slash command name (without the leading '/') when the user issued one.
    command: NotRequired[Optional[str]]

    # N value extracted from command, like /fikir(3) -> 3
    n_val: NotRequired[Optional[int]]

    # Attached materials injected from chat uploads: [{name, markdown, path}].
    attachments: NotRequired[list]

    # Model slug override from the chat request, applied in chat_node if present.
    model_override: NotRequired[Optional[str]]

__all__ = [
    "AthenaState",
    "RouteTarget",
]
