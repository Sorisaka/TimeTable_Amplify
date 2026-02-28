"""Configuration loading and validation."""

from __future__ import annotations

import json
from pathlib import Path

from .errors import ConfigError
from .models import (
    AppConfig,
    BreakSpec,
    DaySpec,
    IOConfig,
    LoggingConfig,
    PenaltyConfig,
    RewardConfig,
    SolverConfig,
)
from .time_utils import duration_to_slots, parse_hhmm


def load_config(path: str) -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Config JSON parse error at line {exc.lineno}: {exc.msg}") from exc

    return _parse_config(data, config_base_dir=config_path.parent)


def _load_coefficients(data: dict, config_base_dir: Path) -> tuple[dict, dict]:
    coeff_path_raw = data.get("coefficients_file_path")
    if coeff_path_raw is None:
        return data["reward"], data["penalties"]

    coeff_path = Path(str(coeff_path_raw))
    if not coeff_path.is_absolute():
        coeff_path = config_base_dir / coeff_path
    if not coeff_path.exists():
        raise ConfigError(f"coefficients_file_path not found: {coeff_path}")

    try:
        coeff_data = json.loads(coeff_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Coefficient JSON parse error at line {exc.lineno}: {exc.msg}") from exc
    except OSError as exc:
        raise ConfigError(f"Failed to read coefficient file: {exc}") from exc

    try:
        reward_data = coeff_data["reward"]
        penalty_data = coeff_data["penalties"]
    except KeyError as exc:
        raise ConfigError(f"Coefficient file missing required key: {exc}") from exc

    if not isinstance(reward_data, dict) or not isinstance(penalty_data, dict):
        raise ConfigError("Coefficient file keys 'reward' and 'penalties' must be objects")
    return reward_data, penalty_data


def _parse_config(data: dict, config_base_dir: Path) -> AppConfig:
    try:
        event_days = [
            DaySpec(
                date=d["date"],
                start_time=d["start_time"],
                end_time=d["end_time"],
                grid_minutes=int(d["grid_minutes"]),
                breaks=[BreakSpec(count=int(b["count"]), duration_minutes=int(b["duration_minutes"])) for b in d["breaks"]],
                changeover_minutes=int(d["changeover_minutes"]),
                allow_idle_edges=bool(d.get("allow_idle_edges", True)),
            )
            for d in data["event_days"]
        ]
        allowed = [int(v) for v in data["allowed_durations_minutes"]]
        reward_data, penalty_data = _load_coefficients(data, config_base_dir)
        reward = RewardConfig(**reward_data)
        penalties = PenaltyConfig(**penalty_data)
        solver = SolverConfig(**data["solver"])
        io = IOConfig(**data["io"])
        logging = LoggingConfig(**data["logging"])

        cfg = AppConfig(
            event_days=event_days,
            allowed_durations_minutes=allowed,
            reward=reward,
            penalties=penalties,
            solver=solver,
            io=io,
            logging=logging,
        )
    except KeyError as exc:
        raise ConfigError(f"Missing required config key: {exc}") from exc
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"Invalid config value: {exc}") from exc

    _validate_config(cfg)
    return cfg


def _validate_config(config: AppConfig) -> None:
    if not config.event_days:
        raise ConfigError("event_days must not be empty")
    if not config.allowed_durations_minutes:
        raise ConfigError("allowed_durations_minutes must not be empty")

    for day in config.event_days:
        start = parse_hhmm(day.start_time)
        end = parse_hhmm(day.end_time)
        if start >= end:
            raise ConfigError(f"day {day.date}: start_time must be earlier than end_time")
        duration_to_slots(end - start, day.grid_minutes)
        if day.changeover_minutes <= 0:
            raise ConfigError(f"day {day.date}: changeover_minutes must be > 0")
        duration_to_slots(day.changeover_minutes, day.grid_minutes)
        for br in day.breaks:
            if br.count < 0:
                raise ConfigError(f"day {day.date}: break count must be >=0")
            if br.duration_minutes <= 0:
                raise ConfigError(f"day {day.date}: break duration must be > 0")
            duration_to_slots(br.duration_minutes, day.grid_minutes)

    for d in config.allowed_durations_minutes:
        if d <= 0:
            raise ConfigError("allowed_durations_minutes must contain positive integers")
        for day in config.event_days:
            duration_to_slots(d, day.grid_minutes)

    min_block_slots = config.reward.min_block_slots_assumption
    if min_block_slots <= 1:
        raise ConfigError("reward.min_block_slots_assumption must be > 1")
    if config.reward.block_step >= config.reward.intra_step * (min_block_slots - 1):
        raise ConfigError(
            "reward.block_step must satisfy block_step < intra_step * (min_block_slots_assumption - 1)"
        )
