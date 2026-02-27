"""Domain models for timetable optimization."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BreakSpec:
    """Repeatable break specification."""

    count: int
    duration_minutes: int


@dataclass(frozen=True)
class DaySpec:
    """Schedule settings for a single day."""

    date: str
    start_time: str
    end_time: str
    grid_minutes: int
    breaks: list[BreakSpec]
    changeover_minutes: int
    allow_idle_edges: bool = True


@dataclass(frozen=True)
class RewardConfig:
    block_base_values: list[float]
    block_step: float
    intra_step: float
    start_position_weight: float
    balance_penalty: float
    later_block_bonus: float
    min_block_slots_assumption: int


@dataclass(frozen=True)
class PenaltyConfig:
    overlap: float
    changeover: float
    out_of_window: float
    unavailable: float


@dataclass(frozen=True)
class SolverConfig:
    client: str
    timeout_ms: int
    num_outputs: int
    strict_optimal: bool


@dataclass(frozen=True)
class IOConfig:
    availability_csv_path: str
    output_dir: str
    output_basename: str


@dataclass(frozen=True)
class LoggingConfig:
    level: str
    json: bool


@dataclass(frozen=True)
class AppConfig:
    event_days: list[DaySpec]
    allowed_durations_minutes: list[int]
    reward: RewardConfig
    penalties: PenaltyConfig
    solver: SolverConfig
    io: IOConfig
    logging: LoggingConfig


@dataclass(frozen=True)
class TimeRange:
    start: str
    end: str


@dataclass(frozen=True)
class BandAvailability:
    band_id: str
    band_name: str
    day: str
    available: TimeRange
    duration_minutes: int
    weight: float = 1.0
    note: str = ""
    unavailable_ranges: tuple[TimeRange, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ParsedAvailability:
    rows: list[BandAvailability]
    warnings: list[str]


@dataclass(frozen=True)
class TimeTableEntry:
    day: str
    start: str
    end: str
    label: str
    entry_type: str  # band | break | idle


@dataclass(frozen=True)
class SolveResult:
    is_optimal: bool
    objective: float
    timetable: list[TimeTableEntry]
    diagnostics: dict[str, str]


@dataclass(frozen=True)
class ValidationReport:
    ok: bool
    errors: list[str]
