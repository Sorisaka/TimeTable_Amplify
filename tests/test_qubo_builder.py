from dataclasses import replace
from types import SimpleNamespace

import pytest

from timetable_amplify.config import load_config
from timetable_amplify.csv_parser import parse_availability_csv
from timetable_amplify.qubo_builder import _coerce_numeric_value, _decode_solution_values, build_qubo


def test_build_qubo_includes_constraints_terms() -> None:
    cfg = load_config("configs/default_config.json")
    parsed = parse_availability_csv(cfg.io.availability_editable_path, cfg.io.priority_json_path)

    qubo = build_qubo(cfg, parsed)

    assert qubo.candidates
    assert len(qubo.linear) == len(qubo.candidates)
    assert qubo.quadratic
    assert qubo.constant >= 0.0


def test_build_qubo_prioritizes_config_time_window_and_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    cfg = load_config("configs/default_config.json")
    parsed = parse_availability_csv(cfg.io.availability_editable_path, cfg.io.priority_json_path)

    narrowed_day = replace(cfg.event_days[0], start_time="12:30", end_time="15:30")
    narrowed_cfg = replace(cfg, event_days=[narrowed_day])

    with caplog.at_level("WARNING"):
        qubo = build_qubo(narrowed_cfg, parsed)

    assert "was clipped" in caplog.text
    clipped_logs = [r for r in caplog.records if "was clipped" in r.message]
    assert len(clipped_logs) == 1
    total_slots = (15 * 60 + 30 - (12 * 60 + 30)) // narrowed_day.grid_minutes
    for cand in qubo.candidates:
        assert cand.start_slot >= 0
        assert cand.end_slot <= total_slots


class _FakePoly:
    def __init__(self, constant: float, is_constant: bool) -> None:
        self._constant = constant
        self._is_constant = is_constant

    def is_constant(self) -> bool:
        return self._is_constant

    @property
    def constant(self) -> float:
        return self._constant


class _FakeValues:
    def __init__(self, mapping: dict[str, object]) -> None:
        self._mapping = mapping

    def evaluate(self, _array: list[str]) -> list[object]:
        raise ValueError("poly sequence")

    def __getitem__(self, key: str) -> object:
        return self._mapping[key]




def test_build_qubo_applies_balance_penalty_pair_terms() -> None:
    cfg = load_config("configs/default_config.json")
    parsed = parse_availability_csv(cfg.io.availability_editable_path, cfg.io.priority_json_path)

    cfg_zero = replace(cfg, reward=replace(cfg.reward, balance_penalty=0.0))
    cfg_balanced = replace(cfg, reward=replace(cfg.reward, balance_penalty=5.0))

    qubo_zero = build_qubo(cfg_zero, parsed)
    qubo_balanced = build_qubo(cfg_balanced, parsed)

    assert qubo_zero.metadata["balance_pair_terms"] == "0"
    assert qubo_balanced.metadata["balance_pair_terms"] != "0"

    by_pair_expected_delta: dict[tuple[int, int], float] = {}
    for i, left in enumerate(qubo_balanced.candidates):
        for j in range(i + 1, len(qubo_balanced.candidates)):
            right = qubo_balanced.candidates[j]
            if left.band.band_id == right.band.band_id:
                continue
            if left.day.date == right.day.date and left.block_index == right.block_index:
                by_pair_expected_delta[(i, j)] = 10.0

    for pair, expected_delta in by_pair_expected_delta.items():
        before = qubo_zero.quadratic.get(pair, 0.0)
        after = qubo_balanced.quadratic.get(pair, 0.0)
        assert after - before == pytest.approx(expected_delta)


def test_decode_solution_values_handles_poly_assignments() -> None:
    vars_ = ["x0", "x1"]
    values = _FakeValues({"x0": _FakePoly(1.0, True), "x1": _FakePoly(0.0, True)})
    result = SimpleNamespace(best=SimpleNamespace(values=values))

    decoded = _decode_solution_values(result, vars_)
    assert decoded == {0: 1.0, 1: 0.0}


def test_coerce_numeric_value_rejects_non_constant_poly() -> None:
    with pytest.raises(ValueError):
        _coerce_numeric_value(_FakePoly(0.0, False))
