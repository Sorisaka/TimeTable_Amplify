"""CSV parser for band availability."""

from __future__ import annotations

import csv
from pathlib import Path

from .errors import CSVFormatError
from .models import BandAvailability, ParsedAvailability, TimeRange
from .time_utils import parse_hhmm


def _ensure_hhmm(value: str, row_idx: int, col: str) -> None:
    try:
        parse_hhmm(value)
    except Exception as exc:
        raise CSVFormatError(f"Row {row_idx}: invalid {col} time '{value}' (HH:MM expected)") from exc

_REQUIRED_COLUMNS = {"band_id", "band_name", "day", "start", "end", "duration_minutes"}


def _parse_range_token(token: str, row_idx: int) -> TimeRange:
    pair = token.split("-")
    if len(pair) != 2:
        raise CSVFormatError(f"Row {row_idx}: invalid range token '{token}'")
    start = pair[0].strip()
    end = pair[1].strip()
    _ensure_hhmm(start, row_idx, "range_start")
    _ensure_hhmm(end, row_idx, "range_end")
    return TimeRange(start=start, end=end)


def parse_availability_csv(path: str) -> ParsedAvailability:
    file_path = Path(path)
    if not file_path.exists():
        raise CSVFormatError(f"Availability CSV not found: {file_path}")

    rows: list[BandAvailability] = []
    warnings: list[str] = []
    seen_band_ids: set[str] = set()

    try:
        with file_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise CSVFormatError("CSV header is missing")
            missing = _REQUIRED_COLUMNS - set(reader.fieldnames)
            if missing:
                raise CSVFormatError(f"CSV missing columns: {sorted(missing)}")

            for idx, row in enumerate(reader, start=2):
                try:
                    band_id = (row.get("band_id") or "").strip()
                    if not band_id:
                        raise CSVFormatError(f"Row {idx}: band_id is required")
                    if band_id in seen_band_ids:
                        raise CSVFormatError(f"Row {idx}: duplicated band_id '{band_id}'")

                    band_name = (row.get("band_name") or "").strip()
                    if not band_name:
                        raise CSVFormatError(f"Row {idx}: band_name is required")

                    day = (row.get("day") or "").strip()
                    if not day:
                        raise CSVFormatError(f"Row {idx}: day is required")

                    start = (row.get("start") or "").strip()
                    end = (row.get("end") or "").strip()
                    _ensure_hhmm(start, idx, "start")
                    _ensure_hhmm(end, idx, "end")
                    if parse_hhmm(start) >= parse_hhmm(end):
                        raise CSVFormatError(f"Row {idx}: start must be earlier than end")

                    duration_minutes = int((row.get("duration_minutes") or "").strip())
                    if duration_minutes <= 0:
                        raise CSVFormatError(f"Row {idx}: duration_minutes must be > 0")

                    weight_raw = (row.get("weight") or row.get("priority") or "1.0").strip()
                    weight = float(weight_raw)
                    unavailable_raw = (row.get("unavailable") or "").strip()
                    ranges = tuple(
                        _parse_range_token(token.strip(), idx)
                        for token in unavailable_raw.split(";")
                        if token.strip()
                    )
                except ValueError as exc:
                    raise CSVFormatError(f"CSV row {idx} has invalid numeric value: {exc}") from exc

                band = BandAvailability(
                    band_id=band_id,
                    band_name=band_name,
                    day=day,
                    available=TimeRange(start=start, end=end),
                    duration_minutes=duration_minutes,
                    weight=weight,
                    note=(row.get("note") or "").strip(),
                    unavailable_ranges=ranges,
                )
                rows.append(band)
                seen_band_ids.add(band.band_id)
    except OSError as exc:
        raise CSVFormatError(f"Failed to read CSV: {exc}") from exc

    if not rows:
        raise CSVFormatError("No valid band rows found in CSV")

    return ParsedAvailability(rows=rows, warnings=warnings)
