"""Cognitive load balancer — gate heavy mental work after hard training.

Jarvis-Academic tracks physical training load and uses it to protect the user's
cognitive budget. A brutal endurance session (heavy triathlon, long orienteering)
leaves little capacity for demanding intellectual work the same day, so this tool
computes a training-load score and, above a threshold, issues a directive that
blocks heavy cognitive tasks and steers the user toward low-effort, mechanical
work instead.

The load formula matches Phase 1's ``PhysicalLoad.calculated_load``
(``duration_minutes * rpe_score``) so the two stay consistent.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field

# Above this training-load score, heavy cognitive work is blocked.
HEAVY_LOAD_THRESHOLD: float = 800.0
# How long the block lasts once triggered.
BLOCK_DURATION_HOURS: int = 12

# Low-cognitive-effort tasks to recommend while heavy work is blocked.
MECHANICAL_TASKS: list[str] = [
    "Anki spaced-repetition reviews",
    "sync notes and run backups",
    "organize files and tidy your workspace",
    "light review reading (no new hard problems)",
]


class CognitiveAllowanceInput(BaseModel):
    """Validated arguments for :func:`calculate_cognitive_allowance`."""

    model_config = ConfigDict(extra="forbid")

    rpe_score: int = Field(
        ge=1,
        le=10,
        description="Rating of Perceived Exertion (1-10 Borg CR10) for the session.",
    )
    duration: float = Field(
        gt=0, description="Session duration in minutes; must be positive."
    )


class CognitiveAllowanceResult(BaseModel):
    """Validated directive describing the user's current cognitive allowance."""

    model_config = ConfigDict(extra="forbid")

    calculated_load: float = Field(
        description="Training load score (rpe_score * duration)."
    )
    heavy_cognitive_blocked: bool = Field(
        description="True if demanding cognitive work should be blocked right now."
    )
    block_duration_hours: int = Field(
        ge=0, description="Hours the block remains in effect (0 when not blocked)."
    )
    recommended_tasks: list[str] = Field(
        description="Low-effort tasks to do instead while blocked."
    )
    blocked_until: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp the block lifts (None when not blocked).",
    )
    directive: str = Field(description="Human-readable instruction for the user.")


def evaluate_load(total_load: float) -> CognitiveAllowanceResult:
    """Turn a raw total cognitive-load score into an allowance directive.

    Shared by the workout tool and the dashboard, which sums today's workout load
    with day-scoped note-derived load adjustments before evaluating the threshold.
    """
    total_load = float(total_load)

    if total_load > HEAVY_LOAD_THRESHOLD:
        blocked_until = datetime.now(timezone.utc) + timedelta(
            hours=BLOCK_DURATION_HOURS
        )
        directive = (
            f"Total cognitive load is {total_load:.0f} (> {HEAVY_LOAD_THRESHOLD:.0f}). "
            f"Heavy cognitive work is BLOCKED for the next {BLOCK_DURATION_HOURS} "
            "hours — do not start demanding tasks such as writing a physics engine "
            "from scratch, hard proofs, or dense new theory. Recover with mechanical, "
            "low-effort work instead: " + ", ".join(MECHANICAL_TASKS) + "."
        )
        return CognitiveAllowanceResult(
            calculated_load=total_load,
            heavy_cognitive_blocked=True,
            block_duration_hours=BLOCK_DURATION_HOURS,
            recommended_tasks=list(MECHANICAL_TASKS),
            blocked_until=blocked_until,
            directive=directive,
        )

    directive = (
        f"Total cognitive load is {total_load:.0f} (<= {HEAVY_LOAD_THRESHOLD:.0f}). "
        "Cognitive capacity is intact — you are clear to take on demanding "
        "intellectual work."
    )
    return CognitiveAllowanceResult(
        calculated_load=total_load,
        heavy_cognitive_blocked=False,
        block_duration_hours=0,
        recommended_tasks=[],
        blocked_until=None,
        directive=directive,
    )


@tool("calculate_cognitive_allowance", args_schema=CognitiveAllowanceInput)
def calculate_cognitive_allowance(
    rpe_score: int, duration: float
) -> CognitiveAllowanceResult:
    """Decide whether heavy cognitive work is advisable after a training session.

    Call this after the user logs or describes a physical training session, or
    whenever they ask whether they should tackle demanding intellectual work
    (e.g. writing a physics engine from scratch, hard proofs, dense new theory)
    given how hard they just trained.

    It computes a training-load score (RPE x duration). If the score exceeds the
    heavy-load threshold, it blocks heavy cognitive tasks for the recovery window
    and recommends mechanical, low-effort tasks instead.

    Args:
        rpe_score: Rating of Perceived Exertion for the session, 1-10.
        duration: Session duration in minutes.

    Returns:
        A CognitiveAllowanceResult with the load, whether heavy work is blocked,
        how long, what to do instead, and a directive to relay to the user.
    """
    return evaluate_load(float(rpe_score) * float(duration))


__all__ = [
    "BLOCK_DURATION_HOURS",
    "CognitiveAllowanceInput",
    "CognitiveAllowanceResult",
    "HEAVY_LOAD_THRESHOLD",
    "MECHANICAL_TASKS",
    "calculate_cognitive_allowance",
    "evaluate_load",
]
