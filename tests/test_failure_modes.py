from __future__ import annotations

import json
from pathlib import Path

import pytest

from timetable_amplify.config import load_config
from timetable_amplify.csv_parser import parse_availability_csv
from timetable_amplify.errors import ConfigError, CSVFormatError, OutputWriteError
from timetable_amplify.models import SolveResult, TimeTableEntry
from timetable_amplify.output import write_outputs
from timetable_amplify.pipeline import run_pipeline


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_missing_config_file() -> None:
    with pytest.raises(ConfigError):
        load_config("/no/such/config.json")


def test_config_type_mismatch(tmp_path: Path) -> None:
    cfg = {
        "event_days": "bad",
        "allowed_durations_minutes": [10],
        "reward": {
            "block_base_values": [1, 2, 3],
            "block_step": 0.2,
            "intra_step": 0.05,
            "start_position_weight": 1.0,
            "balance_penalty": 2.0,
            "later_block_bonus": 0.2,
            "min_block_slots_assumption": 20,
        },
        "penalties": {"overlap": 1, "changeover": 1, "out_of_window": 1, "unavailable": 1},
        "solver": {"client": "amplify", "timeout_ms": 1, "num_outputs": 1, "strict_optimal": False},
        "io": {"availability_editable_path": "x", "output_dir": "y", "output_basename": "z"},
        "logging": {"level": "INFO", "json": False},
    }
    p = tmp_path / "cfg.json"
    _write(p, json.dumps(cfg))
    with pytest.raises(ConfigError):
        load_config(str(p))


def test_invalid_editable_json(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    _write(p, "not-json")
    with pytest.raises(CSVFormatError):
        parse_availability_csv(str(p))


def test_invalid_editable_schema(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    _write(p, json.dumps({"schema_version": 1, "bands": []}))
    with pytest.raises(CSVFormatError):
        parse_availability_csv(str(p))


def test_duration_not_divisible_grid(tmp_path: Path) -> None:
    cfg = json.loads(Path("configs/default_config.json").read_text(encoding="utf-8"))
    cfg["allowed_durations_minutes"] = [11]
    p = tmp_path / "cfg.json"
    _write(p, json.dumps(cfg))
    with pytest.raises(ConfigError):
        load_config(str(p))


def test_start_end_conflict_config(tmp_path: Path) -> None:
    cfg = json.loads(Path("configs/default_config.json").read_text(encoding="utf-8"))
    cfg["event_days"][0]["start_time"] = "19:00"
    cfg["event_days"][0]["end_time"] = "11:40"
    p = tmp_path / "cfg.json"
    _write(p, json.dumps(cfg))
    with pytest.raises(ConfigError):
        load_config(str(p))


def test_zero_changeover_or_break_invalid(tmp_path: Path) -> None:
    cfg = json.loads(Path("configs/default_config.json").read_text(encoding="utf-8"))
    cfg["event_days"][0]["changeover_minutes"] = 0
    p = tmp_path / "cfg.json"
    _write(p, json.dumps(cfg))
    with pytest.raises(ConfigError):
        load_config(str(p))


def test_output_dir_creation_failure(tmp_path: Path) -> None:
    fake_dir = tmp_path / "not_a_dir"
    fake_dir.write_text("file", encoding="utf-8")
    result = SolveResult(False, 0.0, [TimeTableEntry("2026-01-10", "12:00", "12:10", "A", "band")], {})
    with pytest.raises(OutputWriteError):
        write_outputs(result, str(fake_dir), "x")


def test_pipeline_runs_without_amplify_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AMPLIFY_TOKEN", raising=False)
    result, _ = run_pipeline("configs/default_config.json")
    assert result.timetable


def test_solver_empty_result_handled() -> None:
    from timetable_amplify.qubo_builder import QUBOModel, solve_qubo
    from timetable_amplify.config import load_config
    from timetable_amplify.errors import NoFeasibleSolutionError
    from timetable_amplify.models import ParsedAvailability

    cfg = load_config("configs/default_config.json")
    with pytest.raises(NoFeasibleSolutionError):
        solve_qubo(cfg, ParsedAvailability([], []), QUBOModel({}, {}, []))
