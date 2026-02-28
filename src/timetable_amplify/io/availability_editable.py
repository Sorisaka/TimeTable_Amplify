"""Read/write editable intermediate availability file."""

from __future__ import annotations

import json
from pathlib import Path

from ..errors import CSVFormatError
from ..models import ParsedAvailabilityRaw, RawBandAvailability


def write_editable_availability(parsed: ParsedAvailabilityRaw, out_path: Path) -> None:
    """Write editable intermediate availability JSON file."""
    payload = {
        "schema_version": 1,
        "generated_from": parsed.generated_from,
        "grid_minutes": parsed.grid_minutes,
        "days": [
            {"day": day, "label": f"{day}日目", "hours": hours}
            for day, hours in sorted(parsed.days.items())
        ],
        "bands": [
            {
                "name": band.name,
                "slot_minutes": band.slot_minutes,
                "availability_by_day_hour": {
                    str(day): {str(hour): value for hour, value in sorted(hours.items())}
                    for day, hours in sorted(band.availability_by_day_hour.items())
                },
                "notes_by_day": {str(day): note for day, note in sorted(band.notes_by_day.items())},
                "overrides": band.overrides,
            }
            for band in parsed.bands
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_editable_availability(path: Path) -> ParsedAvailabilityRaw:
    """Read editable intermediate availability JSON file."""
    if not path.exists():
        raise CSVFormatError(f"Editable availability file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CSVFormatError(f"Failed to read editable availability file: {exc}") from exc

    try:
        if int(data.get("schema_version", 0)) != 1:
            raise CSVFormatError("Editable availability schema_version must be 1")

        days = {
            int(item["day"]): sorted(int(h) for h in item.get("hours", []))
            for item in data.get("days", [])
        }
        bands: list[RawBandAvailability] = []
        for idx, band in enumerate(data.get("bands", []), start=1):
            name = str(band.get("name", "")).strip()
            slot_minutes = int(band.get("slot_minutes", 0))
            if not name:
                raise CSVFormatError(f"Editable file band #{idx}: name is required")
            if slot_minutes <= 0:
                raise CSVFormatError(f"Editable file band '{name}': slot_minutes must be > 0")

            availability = {
                int(day): {int(hour): bool(v) for hour, v in hours.items()}
                for day, hours in (band.get("availability_by_day_hour") or {}).items()
            }
            notes = {int(day): str(note) for day, note in (band.get("notes_by_day") or {}).items()}
            overrides = band.get("overrides") or []
            if not isinstance(overrides, list):
                raise CSVFormatError(f"Editable file band '{name}': overrides must be an array")

            bands.append(
                RawBandAvailability(
                    name=name,
                    slot_minutes=slot_minutes,
                    availability_by_day_hour=availability,
                    notes_by_day=notes,
                    overrides=overrides,
                )
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise CSVFormatError(f"Editable availability schema is invalid: {exc}") from exc

    if not bands:
        raise CSVFormatError("Editable availability has no bands")

    return ParsedAvailabilityRaw(
        generated_from=str(data.get("generated_from", path.name)),
        grid_minutes=int(data.get("grid_minutes", 5)),
        days=days,
        bands=bands,
        warnings=[],
    )
