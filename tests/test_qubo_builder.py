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


def test_decode_solution_values_handles_poly_assignments() -> None:
    vars_ = ["x0", "x1"]
    values = _FakeValues({"x0": _FakePoly(1.0, True), "x1": _FakePoly(0.0, True)})
    result = SimpleNamespace(best=SimpleNamespace(values=values))

    decoded = _decode_solution_values(result, vars_)
    assert decoded == {0: 1.0, 1: 0.0}


def test_coerce_numeric_value_rejects_non_constant_poly() -> None:
    with pytest.raises(ValueError):
        _coerce_numeric_value(_FakePoly(0.0, False))
