"""LangChain callback that records agent-side LLM usage into the cost meter.

Every chat/router/task-extraction call made through ``langchain-openai`` fires
``on_llm_end`` with an :class:`~langchain_core.outputs.LLMResult`. This handler
pulls the token counts out of that result, prices them from
:data:`config.settings.model_pricing`, and records them into the shared
:class:`~tools.pdf_engine.automation.usage.UsageTracker` under the ``"agent"``
category — keeping agent spend separate from PDF-pipeline spend.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from config import settings

logger = logging.getLogger("jarvis.usage")

_CATEGORY = "agent"


def _extract_tokens(result: LLMResult) -> tuple[int, int, str, float | None]:
    """Return (prompt_tokens, completion_tokens, model, native_cost) from an LLMResult.

    Handles both the ``llm_output['token_usage']`` shape (chat models) and the
    per-generation ``usage_metadata`` shape. ``native_cost`` is OpenRouter's own
    USD figure when present (else None → priced from the table).
    """
    model = ""
    prompt_tokens = 0
    completion_tokens = 0
    native_cost: float | None = None

    def _cost(usage: dict) -> float | None:
        for key in ("cost", "total_cost", "cost_usd"):
            if usage.get(key) is not None:
                try:
                    return float(usage[key])
                except (TypeError, ValueError):
                    pass
        return None

    out = result.llm_output or {}
    if isinstance(out, dict):
        model = out.get("model_name") or out.get("model") or ""
        usage = out.get("token_usage") or out.get("usage") or {}
        if isinstance(usage, dict):
            prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
            completion_tokens = int(usage.get("completion_tokens", 0) or 0)
            native_cost = _cost(usage)

    if not (prompt_tokens or completion_tokens):
        # Fall back to usage_metadata on the generation messages.
        for gen_list in result.generations:
            for gen in gen_list:
                msg = getattr(gen, "message", None)
                meta = getattr(msg, "usage_metadata", None)
                if meta:
                    prompt_tokens += int(meta.get("input_tokens", 0) or 0)
                    completion_tokens += int(meta.get("output_tokens", 0) or 0)
                resp_meta = getattr(msg, "response_metadata", None)
                if isinstance(resp_meta, dict):
                    if not model:
                        model = resp_meta.get("model_name") or resp_meta.get("model") or ""
                    if native_cost is None:
                        tu = resp_meta.get("token_usage") or resp_meta.get("usage") or {}
                        if isinstance(tu, dict):
                            native_cost = _cost(tu)

    return prompt_tokens, completion_tokens, model or "unknown", native_cost


class AgentUsageCallback(BaseCallbackHandler):
    """Records agent LLM token usage/cost into the shared UsageTracker."""

    def __init__(self, usage_tracker: Any) -> None:
        self._usage = usage_tracker

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        try:
            prompt_tokens, completion_tokens, model, native_cost = _extract_tokens(
                response
            )
            if not (prompt_tokens or completion_tokens):
                return
            # native_cost (OpenRouter's own figure) wins; else UsageTracker prices
            # from the table / default fallback so cost is never silently zero.
            self._usage.record(
                _CATEGORY,
                model,
                prompt_tokens,
                completion_tokens,
                cost_usd=native_cost,
                label="agent",
            )
        except Exception:  # noqa: BLE001 - usage tracking must never break a turn
            logger.debug("failed to record agent usage", exc_info=True)


__all__ = ["AgentUsageCallback"]
