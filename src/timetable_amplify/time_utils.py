"""Time and slot conversion helpers."""

from __future__ import annotations

from datetime import datetime

from .errors import ConfigError


def parse_hhmm(value: str) -> int:
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except ValueError as exc:
        raise ConfigError(f"Invalid time format '{value}', expected HH:MM") from exc
    return parsed.hour * 60 + parsed.minute


def minutes_to_hhmm(total_minutes: int) -> str:
    hour = total_minutes // 60
    minute = total_minutes % 60
    return f"{hour:02d}:{minute:02d}"


def duration_to_slots(duration_minutes: int, grid_minutes: int) -> int:
    if grid_minutes <= 0:
        raise ConfigError("grid_minutes must be > 0")
    if duration_minutes < 0:
        raise ConfigError("duration_minutes must be >= 0")
    if duration_minutes % grid_minutes != 0:
        raise ConfigError(
            f"duration {duration_minutes} is not divisible by grid {grid_minutes}. "
            "Use durations aligned to grid."
        )
    return duration_minutes // grid_minutes


def time_to_slot(time_hhmm: str, day_start_hhmm: str, grid_minutes: int) -> int:
    t = parse_hhmm(time_hhmm)
    start = parse_hhmm(day_start_hhmm)
    delta = t - start
    if delta < 0:
        raise ConfigError(f"time {time_hhmm} is earlier than day start {day_start_hhmm}")
    return duration_to_slots(delta, grid_minutes)


def slot_to_time(slot: int, day_start_hhmm: str, grid_minutes: int) -> str:
    if slot < 0:
        raise ConfigError("slot must be >= 0")
    start = parse_hhmm(day_start_hhmm)
    return minutes_to_hhmm(start + slot * grid_minutes)
