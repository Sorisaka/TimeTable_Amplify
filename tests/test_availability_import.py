from __future__ import annotations

from pathlib import Path

from timetable_amplify.csv_parser import parse_availability_csv
from timetable_amplify.io.availability_csv_parser import parse_google_form_csv
from timetable_amplify.io.availability_editable import read_editable_availability, write_editable_availability
from timetable_amplify.io.priority_editable import read_priority_json, write_priority_json


def test_google_form_csv_to_editable_roundtrip(tmp_path: Path) -> None:
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(
        "タイムスタンプ,バンド名,出演枠,1日目 10時台,11,備考(1日目)\n"
        "2026/1/1 10:00,Alice,15分枠,出演可,出演不可,14:30まで可能\n",
        encoding="utf-8",
    )

    parsed = parse_google_form_csv(csv_path)
    out = tmp_path / "editable.json"
    write_editable_availability(parsed, out)
    loaded = read_editable_availability(out)

    assert loaded.bands[0].name == "Alice"
    assert loaded.bands[0].slot_minutes == 15
    assert loaded.bands[0].availability_by_day_hour[1][10] is True
    assert loaded.bands[0].availability_by_day_hour[1][11] is False


def test_editable_override_applied_in_solver_parser(tmp_path: Path) -> None:
    p = tmp_path / "editable.json"
    p.write_text(
        """
{
  "schema_version": 1,
  "generated_from": "x.csv",
  "grid_minutes": 5,
  "days": [{"day": 1, "label": "1日目", "hours": [13, 14, 15]}],
  "bands": [{
    "name": "Band",
    "slot_minutes": 15,
    "availability_by_day_hour": {"1": {"13": true, "14": true, "15": true}},
    "notes_by_day": {"1": ""},
    "overrides": [{"day": 1, "allow_until": "14:30"}]
  }]
}
""".strip(),
        encoding="utf-8",
    )

    parsed = parse_availability_csv(str(p))
    assert len(parsed.rows) == 1
    row = parsed.rows[0]
    assert row.available.start == "13:00"
    assert row.available.end == "15:00"
    assert any(r.start == "14:30" and r.end == "15:00" for r in row.unavailable_ranges)


def test_priority_json_weight_resolution(tmp_path: Path) -> None:
    p = tmp_path / "priority.json"
    p.write_text(
        """
{
  "version": 1,
  "bands": [
    {"band": "BandA", "priority": 5},
    {"band": "BandB", "weight": 2.1},
    {"band": "BandC", "priority": 10}
  ]
}
""".strip(),
        encoding="utf-8",
    )

    resolved = read_priority_json(p)
    assert resolved["BandA"] == 1.5
    assert resolved["BandB"] == 2.1
    assert resolved["BandC"] == 1.0


def test_solver_parser_uses_priority_json(tmp_path: Path) -> None:
    editable = tmp_path / "editable.json"
    editable.write_text(
        """
{
  "schema_version": 1,
  "generated_from": "x.csv",
  "grid_minutes": 5,
  "days": [{"day": 1, "label": "1日目", "hours": [12, 13]}],
  "bands": [{
    "name": "Band A",
    "slot_minutes": 15,
    "availability_by_day_hour": {"1": {"12": true, "13": true}},
    "notes_by_day": {"1": ""},
    "overrides": []
  }]
}
""".strip(),
        encoding="utf-8",
    )
    write_priority_json(tmp_path / "priority.json", ["Band A"])
    (tmp_path / "priority.json").write_text(
        '{"version":1,"bands":[{"band":"Band A","priority":4}]}', encoding="utf-8"
    )

    parsed = parse_availability_csv(str(editable))
    assert parsed.rows[0].weight == 1.2


def test_solver_parser_priority_missing_band_falls_back(tmp_path: Path) -> None:
    editable = tmp_path / "editable.json"
    editable.write_text(
        """
{
  "schema_version": 1,
  "generated_from": "x.csv",
  "grid_minutes": 5,
  "days": [{"day": 1, "label": "1日目", "hours": [12]}],
  "bands": [{
    "name": "Band Missing",
    "slot_minutes": 15,
    "availability_by_day_hour": {"1": {"12": true}},
    "notes_by_day": {"1": ""},
    "overrides": []
  }]
}
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "priority.json").write_text('{"version":1,"bands":[{"band":"Other","priority":5}]}', encoding="utf-8")

    parsed = parse_availability_csv(str(editable))
    assert parsed.rows[0].weight == 1.0
