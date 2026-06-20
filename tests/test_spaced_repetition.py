"""SM-2 spaced-repetition interval math (pure, no LLM)."""

from __future__ import annotations

from core.spaced_repetition import calculate_next_interval


def test_failed_recall_resets():
    interval, recalls, ef = calculate_next_interval(
        score=1, consecutive_recalls=4, current_interval_days=30, ease_factor=2.5
    )
    assert interval == 1
    assert recalls == 0


def test_first_success_short_interval():
    interval, recalls, ef = calculate_next_interval(
        score=5, consecutive_recalls=0, current_interval_days=0, ease_factor=2.5
    )
    assert recalls == 1
    assert interval >= 1


def test_ease_factor_floor():
    # Repeated low (but passing) scores must never drop EF below 1.3.
    _, _, ef = calculate_next_interval(
        score=3, consecutive_recalls=0, current_interval_days=1, ease_factor=1.3
    )
    assert ef >= 1.3


def test_interval_grows_with_streak():
    i1, r1, ef1 = calculate_next_interval(
        score=5, consecutive_recalls=1, current_interval_days=1, ease_factor=2.5
    )
    i2, r2, ef2 = calculate_next_interval(
        score=5, consecutive_recalls=2, current_interval_days=i1, ease_factor=ef1
    )
    assert i2 > i1
    assert r2 == 3
