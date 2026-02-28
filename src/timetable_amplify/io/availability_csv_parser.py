"""Parser for Google Form-like availability CSV files."""

from __future__ import annotations

import csv
import re
from itertools import chain
from pathlib import Path

from ..errors import CSVFormatError
from ..models import ParsedAvailabilityRaw, RawBandAvailability

_DAY_HOUR_RE = re.compile(r"\s*(\d+)日目\s*(\d+)時台\s*")
_HOUR_ONLY_RE = re.compile(r"\s*(\d{1,2})(?:時台)?(?:\.\d+)?\s*")
_DAY_RE = re.compile(r"\s*(\d+)日目\s*")


def _normalize_bool(raw: str, row_idx: int, col_idx: int, warnings: list[str]) -> bool:
    value = (raw or "").strip()
    if value == "出演可":
        return True
    if value == "出演不可":
        return False
    if value == "":
        warnings.append(f"Row {row_idx} Col {col_idx}: empty availability treated as 出演不可")
        return False
    warnings.append(f"Row {row_idx} Col {col_idx}: unsupported value '{value}' treated as 出演不可")
    return False


def _extract_minutes(slot_value: str) -> int | None:
    m = re.search(r"(\d+)", slot_value or "")
    return int(m.group(1)) if m else None


def _find_first_col(headers: list[str], keyword: str) -> int | None:
    for i, h in enumerate(headers):
        if keyword in (h or ""):
            return i
    return None


def parse_google_form_csv(path: Path) -> ParsedAvailabilityRaw:
    """Parse Google Form-like CSV and return normalized intermediate model."""
    if not path.exists():
        raise CSVFormatError(f"Availability CSV not found: {path}")

    warnings: list[str] = []
    row_errors: list[str] = []
    bands: list[RawBandAvailability] = []
    day_to_hours: dict[int, set[int]] = {}

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            header1 = next(reader, None)
            if not header1:
                raise CSVFormatError("CSV header is missing")
            header2 = next(reader, None)

            # Google Form exports may use 2 header rows.
            if header2 and _find_first_col(header2, "バンド名") is not None:
                meta_headers = header2
                timeline_headers = header1
                data_start_row = 3
            else:
                meta_headers = header1
                timeline_headers = header1
                data_start_row = 2
                if header2 is not None:
                    reader = chain([header2], reader)

            band_col = _find_first_col(meta_headers, "バンド名")
            slot_col = _find_first_col(meta_headers, "出演枠")
            if band_col is None:
                raise CSVFormatError("CSV parsing failed: 'バンド名' column not found")
            if slot_col is None:
                raise CSVFormatError("CSV parsing failed: '出演枠' column not found")

            note_cols: dict[int | None, int] = {}
            for col_idx, header in enumerate(meta_headers):
                text = (header or "").strip()
                if "備考" in text:
                    day_match = _DAY_RE.search(text)
                    note_cols[int(day_match.group(1)) if day_match else None] = col_idx

            availability_cols: dict[int, tuple[int, int]] = {}
            current_day: int | None = None
            for col_idx, header in enumerate(timeline_headers):
                text = (header or "").strip()
                day_hour_match = _DAY_HOUR_RE.fullmatch(text)
                if day_hour_match:
                    day, hour = int(day_hour_match.group(1)), int(day_hour_match.group(2))
                    current_day = day
                    availability_cols[col_idx] = (day, hour)
                    day_to_hours.setdefault(day, set()).add(hour)
                    continue
                hour_only_match = _HOUR_ONLY_RE.fullmatch(text)
                if hour_only_match and current_day is not None:
                    hour = int(hour_only_match.group(1))
                    availability_cols[col_idx] = (current_day, hour)
                    day_to_hours.setdefault(current_day, set()).add(hour)

            if not availability_cols:
                raise CSVFormatError("CSV parsing failed: no day/hour availability columns detected")

            skipped_empty_band = 0
            for row_idx, row in enumerate(reader, start=data_start_row):
                if not any((c or "").strip() for c in row):
                    continue
                name = (row[band_col] if band_col < len(row) else "").strip()
                if not name:
                    skipped_empty_band += 1
                    continue

                slot_raw = (row[slot_col] if slot_col < len(row) else "").strip()
                slot_minutes = _extract_minutes(slot_raw)
                if slot_minutes is None:
                    row_errors.append(f"Row {row_idx} ({name}): 出演枠 '{slot_raw}' から分数を抽出できません")
                    continue

                availability_by_day_hour: dict[int, dict[int, bool]] = {}
                for col_idx, (day, hour) in availability_cols.items():
                    raw = row[col_idx] if col_idx < len(row) else ""
                    availability_by_day_hour.setdefault(day, {})[hour] = _normalize_bool(raw, row_idx, col_idx + 1, warnings)

                notes_by_day: dict[int, str] = {}
                for day in availability_by_day_hour:
                    note_idx = note_cols.get(day, note_cols.get(None, -1))
                    notes_by_day[day] = (row[note_idx] if 0 <= note_idx < len(row) else "").strip()

                bands.append(RawBandAvailability(name=name, slot_minutes=slot_minutes, availability_by_day_hour=availability_by_day_hour, notes_by_day=notes_by_day, overrides=[]))

            if skipped_empty_band:
                warnings.append(f"Skipped {skipped_empty_band} rows because バンド名 was empty")

    except OSError as exc:
        raise CSVFormatError(f"Failed to read CSV: {exc}") from exc

    if row_errors:
        detail = "\n".join(row_errors[:20])
        more = "" if len(row_errors) <= 20 else f"\n... and {len(row_errors) - 20} more"
        raise CSVFormatError(f"CSV contains invalid rows:\n{detail}{more}")
    if not bands:
        raise CSVFormatError("No valid band rows found in CSV")

    return ParsedAvailabilityRaw(generated_from=path.name, grid_minutes=5, days={d: sorted(h) for d, h in sorted(day_to_hours.items())}, bands=bands, warnings=warnings)
