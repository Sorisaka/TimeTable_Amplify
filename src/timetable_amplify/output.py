"""Timetable output utilities."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .errors import OutputWriteError
from .models import SolveResult


def format_timetable_for_stdout(result: SolveResult) -> str:
    lines = ["=== Timetable ==="]
    for e in sorted(result.timetable, key=lambda x: (x.day, x.start, x.entry_type)):
        lines.append(f"[{e.day}] {e.start}-{e.end}  ({e.entry_type}) {e.label}")
    lines.append(f"objective={result.objective:.3f} is_optimal={result.is_optimal}")
    return "\n".join(lines)


def write_outputs(result: SolveResult, output_dir: str, basename: str) -> dict[str, str]:
    target_dir = Path(output_dir)
    csv_path = target_dir / f"{basename}.csv"
    json_path = target_dir / f"{basename}.json"
    md_path = target_dir / f"{basename}.md"

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", encoding="utf-8", newline="") as f_csv:
            writer = csv.DictWriter(f_csv, fieldnames=["day", "start", "end", "label", "entry_type"])
            writer.writeheader()
            for e in result.timetable:
                writer.writerow({"day": e.day, "start": e.start, "end": e.end, "label": e.label, "entry_type": e.entry_type})

        payload = {
            "is_optimal": result.is_optimal,
            "objective": result.objective,
            "diagnostics": result.diagnostics,
            "entries": [e.__dict__ for e in result.timetable],
        }
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        md_lines = ["# Timetable", "", "| day | start | end | type | label |", "|---|---|---|---|---|"]
        for e in result.timetable:
            md_lines.append(f"| {e.day} | {e.start} | {e.end} | {e.entry_type} | {e.label} |")
        md_path.write_text("\n".join(md_lines), encoding="utf-8")
    except OSError as exc:
        raise OutputWriteError(f"Failed to write output artifacts: {exc}") from exc

    return {"csv": str(csv_path), "json": str(json_path), "md": str(md_path)}
