"""Token & cost usage tracking, split into independent categories.

Adapted from the upstream ``core/state.py:UsageTracker``. Two changes for
Athena-Academic:

1. A **category** dimension (``"pdf"`` vs ``"agent"``) so the dashboard can show
   two separate meters — spend inside the PDF automation vs. spend on the chat
   agent / router / task extraction.
2. **Cumulative** totals (not daily-reset) warm-loaded from the CSV on startup,
   so the meters survive restarts. Every individual call is still appended to the
   CSV for historical analysis.

All public methods are thread-safe; ``record`` is safe to call from worker
threads and from async code alike.
"""

from __future__ import annotations

import csv
import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

# Logged under the "athena" namespace so cost lines stream to the live log panel.
log = logging.getLogger("athena.pdf_engine.usage")

_VALID_CATEGORIES = ("pdf", "agent")

_USAGE_CSV_HEADER = [
    "timestamp",
    "category",
    "model",
    "label",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cost_usd",
]


@dataclass
class _ModelUsage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0


class UsageTracker:
    """Aggregates API usage per category/model and persists each call to CSV."""

    def __init__(
        self,
        csv_path: Optional[Path] = None,
        *,
        pricing: Optional[dict[str, tuple[float, float]]] = None,
        default_pricing: Optional[tuple[float, float]] = None,
    ) -> None:
        self._lock = threading.Lock()
        self._csv_path = Path(csv_path) if csv_path else None
        # pricing: slug -> (prompt_per_1m, completion_per_1m); used when a caller
        # records without a precomputed cost.
        self._pricing = {self._norm_slug(k): v for k, v in (pricing or {}).items()}
        self._default_pricing = default_pricing
        self._by_cat: dict[str, dict[str, _ModelUsage]] = {
            c: {} for c in _VALID_CATEGORIES
        }
        self._init_csv()
        self._warm_load()

    # ------------------------------------------------------------------ #
    def _init_csv(self) -> None:
        if not self._csv_path:
            return
        try:
            if not self._csv_path.exists():
                self._csv_path.parent.mkdir(parents=True, exist_ok=True)
                with self._csv_path.open("w", encoding="utf-8", newline="") as fh:
                    csv.writer(fh).writerow(_USAGE_CSV_HEADER)
        except Exception:  # pragma: no cover - cost logging is never critical
            pass

    def _warm_load(self) -> None:
        """Rebuild cumulative totals from the CSV so restarts keep the meters."""
        if not self._csv_path or not self._csv_path.exists():
            return
        try:
            with self._csv_path.open("r", encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    cat = (row.get("category") or "").strip()
                    if cat not in self._by_cat:
                        continue
                    model = row.get("model") or "unknown"
                    mu = self._by_cat[cat].setdefault(model, _ModelUsage())
                    mu.calls += 1
                    mu.prompt_tokens += int(row.get("prompt_tokens") or 0)
                    mu.completion_tokens += int(row.get("completion_tokens") or 0)
                    mu.cost_usd += float(row.get("cost_usd") or 0.0)
        except Exception:  # pragma: no cover - tolerate a malformed history file
            pass

    @staticmethod
    def _norm_slug(model: str) -> str:
        """Normalize an OpenRouter model slug for tolerant pricing lookup."""
        s = (model or "").strip().lower()
        # Drop variant qualifiers like ":free", ":nitro", ":beta".
        if ":" in s:
            s = s.split(":", 1)[0]
        return s

    def _price_for(self, model: str) -> Optional[tuple[float, float]]:
        norm = self._norm_slug(model)
        if norm in self._pricing:
            return self._pricing[norm]
        # Substring match (e.g. provider returns a dated/variant slug).
        for slug, price in self._pricing.items():
            if slug and (slug in norm or norm in slug):
                return price
        return self._default_pricing

    def _estimate_cost(self, model: str, prompt_t: int, completion_t: int) -> float:
        price = self._price_for(model)
        if not price:
            return 0.0
        p_per_1m, c_per_1m = price
        return (prompt_t / 1_000_000) * p_per_1m + (completion_t / 1_000_000) * c_per_1m

    # ------------------------------------------------------------------ #
    def record(
        self,
        category: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: Optional[float] = None,
        label: str = "",
    ) -> None:
        """Record one API call under ``category`` (``"pdf"`` or ``"agent"``)."""
        if category not in self._by_cat:
            category = "agent"
        pt = int(prompt_tokens or 0)
        ct = int(completion_tokens or 0)
        cost = (
            float(cost_usd)
            if cost_usd is not None
            else self._estimate_cost(model, pt, ct)
        )
        with self._lock:
            mu = self._by_cat[category].setdefault(model, _ModelUsage())
            mu.calls += 1
            mu.prompt_tokens += pt
            mu.completion_tokens += ct
            mu.cost_usd += cost
            self._append_csv(category, model, label, pt, ct, cost)
        log.info(
            "cost · %s · %s%s · in=%d out=%d ≈$%.4f",
            category,
            model,
            f" · {label}" if label else "",
            pt,
            ct,
            cost,
        )

    def _append_csv(
        self, category: str, model: str, label: str, pt: int, ct: int, cost: float
    ) -> None:
        if not self._csv_path:
            return
        try:
            now = datetime.now().isoformat(timespec="seconds")
            with self._csv_path.open("a", encoding="utf-8", newline="") as fh:
                csv.writer(fh).writerow(
                    [now, category, model, label, pt, ct, pt + ct, f"{cost:.6f}"]
                )
        except Exception:  # pragma: no cover - cost logging is never critical
            pass

    # ------------------------------------------------------------------ #
    def _category_snapshot(self, models: dict[str, _ModelUsage]) -> dict:
        total_calls = sum(u.calls for u in models.values())
        total_prompt = sum(u.prompt_tokens for u in models.values())
        total_completion = sum(u.completion_tokens for u in models.values())
        total_tokens = total_prompt + total_completion
        total_cost = sum(u.cost_usd for u in models.values())
        return {
            "calls": total_calls,
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
            "avg_cost_per_call_usd": round(total_cost / total_calls, 6)
            if total_calls
            else 0.0,
            "avg_tokens_per_call": round(total_tokens / total_calls, 1)
            if total_calls
            else 0.0,
            "models": {
                m: {
                    "calls": u.calls,
                    "prompt_tokens": u.prompt_tokens,
                    "completion_tokens": u.completion_tokens,
                    "cost_usd": round(u.cost_usd, 6),
                }
                for m, u in models.items()
            },
        }

    def snapshot(self) -> dict:
        """Per-category totals + averages, plus a grand total."""
        with self._lock:
            cats = {
                cat: self._category_snapshot(models)
                for cat, models in self._by_cat.items()
            }
        grand_cost = sum(c["total_cost_usd"] for c in cats.values())
        grand_tokens = sum(c["total_tokens"] for c in cats.values())
        return {
            **cats,
            "total": {
                "total_cost_usd": round(grand_cost, 6),
                "total_tokens": grand_tokens,
            },
        }


__all__ = ["UsageTracker"]
