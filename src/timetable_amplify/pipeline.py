"""Application orchestration pipeline."""

from __future__ import annotations

import logging

from .config import load_config
from .csv_parser import parse_availability_csv
from .errors import ValidationError
from .models import SolveResult
from .output import write_outputs
from .qubo_builder import build_qubo, solve_qubo
from .validator import validate_timetable

logger = logging.getLogger(__name__)


def run_pipeline(config_path: str, priority_json_path: str | None = None) -> tuple[SolveResult, dict[str, str]]:
    config = load_config(config_path)
    logger.info("Loaded config from %s", config_path)

    resolved_priority_path = priority_json_path if priority_json_path is not None else config.io.priority_json_path
    parsed = parse_availability_csv(config.io.availability_editable_path, priority_json_path=resolved_priority_path)
    for warning in parsed.warnings:
        logger.warning("CSV warning: %s", warning)

    qubo = build_qubo(config, parsed)
    result = solve_qubo(config, parsed, qubo)

    report = validate_timetable(config, parsed, result.timetable)
    if not report.ok:
        raise ValidationError("Validation failed: " + " | ".join(report.errors))

    artifact_paths = write_outputs(result, config.io.output_dir, config.io.output_basename)
    logger.info("Wrote output: %s", artifact_paths)
    return result, artifact_paths
