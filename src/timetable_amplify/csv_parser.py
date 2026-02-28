"""Availability loader from editable intermediate file."""

from __future__ import annotations

import re
from pathlib import Path

from .errors import CSVFormatError
from .io.availability_editable import read_editable_availability
from .io.priority_editable import read_priority_json
from .models import BandAvailability, ParsedAvailability, TimeRange


def _to_hhmm(hour: int, minute: int = 0) -> str:
    return f"{hour:02d}:{minute:02d}"


def _apply_overrides(
    day_hours: dict[int, bool],
    overrides: list[dict[str, object]],
    day: int,
    row_label: str,
    warnings: list[str],
) -> tuple[dict[int, bool], list[TimeRange]]:
    adjusted = dict(day_hours)
    extra_unavailable: list[TimeRange] = []
    for override in overrides:
        if not isinstance(override, dict):
            warnings.append(f"{row_label}: override must be object but got {type(override).__name__}")
            continue
        if int(override.get("day", -1)) != day:
            continue

        allow_until = override.get("allow_until")
        if allow_until is not None:
            m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(allow_until))
            if not m:
                warnings.append(f"{row_label}: invalid allow_until '{allow_until}', expected HH:MM")
                continue
            cutoff_h = int(m.group(1))
            cutoff_m = int(m.group(2))
            for hour in list(adjusted):
                if hour > cutoff_h:
                    adjusted[hour] = False
            if 0 < cutoff_m < 60 and adjusted.get(cutoff_h, False):
                extra_unavailable.append(TimeRange(start=_to_hhmm(cutoff_h, cutoff_m), end=_to_hhmm(cutoff_h + 1, 0)))
    return adjusted, extra_unavailable


def _resolve_priority_path(editable_path: Path, priority_json_path: str | Path | None) -> Path | None:
    if priority_json_path is None:
        candidate = editable_path.parent / "priority.json"
        return candidate if candidate.exists() else None
    return Path(priority_json_path)


def parse_availability_csv(path: str, priority_json_path: str | Path | None = None) -> ParsedAvailability:
    """Load editable availability file and convert to solver input rows."""
    editable_path = Path(path)
    raw = read_editable_availability(editable_path)
    resolved_priority_path = _resolve_priority_path(editable_path, priority_json_path)
    priority_map = read_priority_json(resolved_priority_path) if resolved_priority_path is not None else {}

    rows: list[BandAvailability] = []
    warnings = list(raw.warnings)

    for b_idx, band in enumerate(raw.bands, start=1):
        normalized_band_name = band.name.strip()
        band_weight = float(priority_map.get(normalized_band_name, 1.0))
        band_id_base = re.sub(r"[^a-zA-Z0-9]+", "_", normalized_band_name).strip("_").lower() or f"band{b_idx}"
        for day, hours_map in sorted(band.availability_by_day_hour.items()):
            adjusted_hours, extra_unavailable = _apply_overrides(
                hours_map,
                band.overrides,
                day,
                f"band '{normalized_band_name}' day {day}",
                warnings,
            )
            allowed_hours = sorted([hour for hour, ok in adjusted_hours.items() if ok])
            if not allowed_hours:
                warnings.append(f"band '{normalized_band_name}' day {day}: no available hours, skipped")
                continue

            start_h = min(allowed_hours)
            end_h = max(allowed_hours) + 1
            unavailable_ranges = list(extra_unavailable)
            for hour, ok in sorted(adjusted_hours.items()):
                if not ok and start_h <= hour < end_h:
                    unavailable_ranges.append(TimeRange(start=_to_hhmm(hour), end=_to_hhmm(hour + 1)))

            rows.append(
                BandAvailability(
                    band_id=f"{band_id_base}_d{day}",
                    band_name=normalized_band_name,
                    day=str(day),
                    available=TimeRange(start=_to_hhmm(start_h), end=_to_hhmm(end_h)),
                    duration_minutes=band.slot_minutes,
                    weight=band_weight,
                    note=band.notes_by_day.get(day, ""),
                    unavailable_ranges=tuple(unavailable_ranges),
                )
            )

    if not rows:
        raise CSVFormatError("No valid availability rows after reading editable file")
    return ParsedAvailability(rows=rows, warnings=warnings)
