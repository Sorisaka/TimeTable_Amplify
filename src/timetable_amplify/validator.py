"""Solution validation checks."""

from __future__ import annotations

from .models import AppConfig, ParsedAvailability, TimeTableEntry, ValidationReport
from .qubo_builder import _break_intervals
from .time_utils import time_to_slot


def validate_timetable(config: AppConfig, parsed: ParsedAvailability, entries: list[TimeTableEntry]) -> ValidationReport:
    errors: list[str] = []
    day_map = {d.date: d for d in config.event_days}
    band_map = {b.band_name: b for b in parsed.rows}

    entries_by_day: dict[str, list[TimeTableEntry]] = {}
    for e in entries:
        entries_by_day.setdefault(e.day, []).append(e)

    for day, day_entries in entries_by_day.items():
        spec = day_map.get(day)
        if spec is None:
            errors.append(f"Unknown day in output: {day}")
            continue

        sorted_e = sorted(day_entries, key=lambda x: x.start)
        break_slots = _break_intervals(spec)
        changeover = spec.changeover_minutes // spec.grid_minutes

        for i, e in enumerate(sorted_e):
            s = time_to_slot(e.start, spec.start_time, spec.grid_minutes)
            t = time_to_slot(e.end, spec.start_time, spec.grid_minutes)
            total = time_to_slot(spec.end_time, spec.start_time, spec.grid_minutes)
            if s < 0 or t > total or s >= t:
                errors.append(f"Time out-of-range or invalid interval: {e}")

            if e.entry_type == "band":
                band = band_map.get(e.label)
                if band is None:
                    errors.append(f"Output band not in input CSV: {e.label}")
                else:
                    if not (band.available.start <= e.start and e.end <= band.available.end):
                        errors.append(f"Band scheduled outside availability: {e.label}")
                    for r in band.unavailable_ranges:
                        if not (e.end <= r.start or e.start >= r.end):
                            errors.append(f"Band scheduled in unavailable range: {e.label}")

                for bs, be in break_slots:
                    if not (t <= bs or s >= be):
                        errors.append(f"Band overlaps break: {e.label}")

            if i > 0:
                prev = sorted_e[i - 1]
                ps = time_to_slot(prev.start, spec.start_time, spec.grid_minutes)
                pt = time_to_slot(prev.end, spec.start_time, spec.grid_minutes)
                if s < pt:
                    errors.append(f"Overlap: {prev.label} and {e.label}")
                if prev.entry_type == "band" and e.entry_type == "band" and s - pt < changeover:
                    errors.append(f"Changeover violation between {prev.label} and {e.label}")

    return ValidationReport(ok=not errors, errors=errors)
