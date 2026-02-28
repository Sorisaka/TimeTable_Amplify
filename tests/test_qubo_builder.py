from timetable_amplify.config import load_config
from timetable_amplify.csv_parser import parse_availability_csv
from timetable_amplify.qubo_builder import build_qubo


def test_build_qubo_includes_constraints_terms() -> None:
    cfg = load_config("configs/default_config.json")
    parsed = parse_availability_csv(cfg.io.availability_editable_path, cfg.io.priority_json_path)

    qubo = build_qubo(cfg, parsed)

    assert qubo.candidates
    assert len(qubo.linear) == len(qubo.candidates)
    assert qubo.quadratic
    assert qubo.constant >= 0.0
