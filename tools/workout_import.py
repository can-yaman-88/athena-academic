"""Parse workout files (JSON / CSV / .FIT) into normalized workout dicts.

Each returned dict maps onto :class:`core.schemas.PhysicalLoad` fields; the upload
endpoint marks them ``completed`` (they are recorded actuals and count toward
cognitive load). Parsing is defensive — unknown/missing fields fall back to sane
defaults rather than raising, so a partial file still imports.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import date as date_type
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("athena.workout_import")

_DEFAULT_RPE = 5
_DEFAULT_DURATION = 30


def _to_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _to_int(v: Any) -> Optional[int]:
    f = _to_float(v)
    return int(round(f)) if f is not None else None


def _pace_from_speed(speed_kmh: Optional[float]) -> Optional[str]:
    if not speed_kmh or speed_kmh <= 0:
        return None
    sec_per_km = 3600.0 / speed_kmh
    m, s = divmod(int(round(sec_per_km)), 60)
    return f"{m}:{s:02d}"


def _norm_date(v: Any) -> str:
    if not v:
        return date_type.today().isoformat()
    s = str(v)
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s[:19], fmt).date().isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s).date().isoformat()
    except ValueError:
        return date_type.today().isoformat()


def _normalize(rec: dict) -> dict:
    """Map a loose record (any source) onto PhysicalLoad fields with defaults."""
    g = lambda *ks: next((rec[k] for k in ks if k in rec and rec[k] not in (None, "")), None)  # noqa: E731

    duration = _to_int(g("duration_minutes", "duration", "minutes")) or _DEFAULT_DURATION
    rpe = _to_int(g("rpe_score", "rpe")) or _DEFAULT_RPE
    rpe = max(1, min(10, rpe))
    distance = _to_float(g("distance_km", "distance"))
    speed = _to_float(g("avg_speed_kmh", "avg_speed", "speed"))
    pace = g("pace")
    if not pace and speed:
        pace = _pace_from_speed(speed)
    return {
        "date": _norm_date(g("date", "start_time", "timestamp")),
        "duration_minutes": max(1, duration),
        "rpe_score": rpe,
        "title": g("title", "name", "sport", "type"),
        "distance_km": distance,
        "pace": str(pace) if pace else None,
        "avg_speed_kmh": speed,
        "avg_hr": _to_int(g("avg_hr", "avg_heart_rate", "heart_rate")),
    }


def _parse_json(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    if isinstance(data, dict):
        data = data.get("workouts", [data])
    return [_normalize(r) for r in data if isinstance(r, dict)]


def _parse_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        return [_normalize(row) for row in csv.DictReader(fh)]


def _parse_fit(path: Path) -> list[dict]:
    """Extract session summaries from a Garmin/TrainingPeaks .FIT file."""
    import fitdecode

    out: list[dict] = []
    with fitdecode.FitReader(str(path)) as fit:
        for frame in fit:
            if not isinstance(frame, fitdecode.FitDataMessage) or frame.name != "session":
                continue
            vals: dict[str, Any] = {}
            for f in frame.fields:
                vals[f.name] = f.value
            dist_m = _to_float(vals.get("total_distance"))
            timer_s = _to_float(vals.get("total_timer_time") or vals.get("total_elapsed_time"))
            speed_ms = _to_float(vals.get("enhanced_avg_speed") or vals.get("avg_speed"))
            speed_kmh = speed_ms * 3.6 if speed_ms else None
            out.append(
                _normalize(
                    {
                        "date": vals.get("start_time"),
                        "duration_minutes": round(timer_s / 60) if timer_s else None,
                        "distance_km": dist_m / 1000 if dist_m else None,
                        "avg_speed_kmh": speed_kmh,
                        "avg_hr": vals.get("avg_heart_rate"),
                        "title": vals.get("sport"),
                    }
                )
            )
    return out


def parse_workouts(path: Path) -> list[dict]:
    """Parse a workout file by extension into normalized workout dicts."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _parse_json(path)
    if suffix == ".csv":
        return _parse_csv(path)
    if suffix == ".fit":
        return _parse_fit(path)
    raise ValueError(f"Unsupported workout file type: {suffix or '(none)'}")


__all__ = ["parse_workouts"]
