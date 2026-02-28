"""QUBO construction + solve adapter.

This module keeps optimization-specific logic isolated.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from itertools import combinations

from .errors import NoFeasibleSolutionError, SolverUnavailableError
from .models import AppConfig, BandAvailability, DaySpec, ParsedAvailability, SolveResult, TimeTableEntry
from .time_utils import duration_to_slots, parse_hhmm, slot_to_time, time_to_slot


@dataclass(frozen=True)
class CandidateStart:
    band: BandAvailability
    day: DaySpec
    start_slot: int
    end_slot: int
    block_index: int
    score: float


@dataclass(frozen=True)
class QUBOModel:
    terms: dict[str, float]
    metadata: dict[str, str]
    candidates: list[CandidateStart]
    linear: list[float]
    quadratic: dict[tuple[int, int], float]
    constant: float


def ideal_block_counts(n_bands: int) -> tuple[int, int, int]:
    q, r = divmod(n_bands, 3)
    if r == 0:
        return (q, q, q)
    if r == 1:
        return (q, q, q + 1)
    return (q, q + 1, q + 1)


def build_qubo(config: AppConfig, availability: ParsedAvailability) -> QUBOModel:
    day_map = {d.date: d for d in config.event_days}
    day_map.update({str(idx): d for idx, d in enumerate(config.event_days, start=1)})
    targets = ideal_block_counts(len(availability.rows))

    candidates: list[CandidateStart] = []
    for band in availability.rows:
        day = day_map.get(band.day)
        if day is None:
            continue
        band_slots = duration_to_slots(band.duration_minutes, day.grid_minutes)
        start = time_to_slot(band.available.start, day.start_time, day.grid_minutes)
        end = time_to_slot(band.available.end, day.start_time, day.grid_minutes)

        for s in range(start, max(start, end - band_slots) + 1):
            bidx, pos = _slot_to_block(day, s)
            score = _block_position_value(config, bidx, pos) * band.weight * config.reward.start_position_weight
            candidates.append(CandidateStart(band=band, day=day, start_slot=s, end_slot=s + band_slots, block_index=bidx, score=score))

    linear = [-c.score for c in candidates]
    quadratic: dict[tuple[int, int], float] = {}
    constant = 0.0

    by_band: dict[str, list[int]] = {}
    for idx, cand in enumerate(candidates):
        by_band.setdefault(cand.band.band_id, []).append(idx)

    # Exactly-one per band: P * (sum x_i - 1)^2
    p_onehot = config.penalties.out_of_window
    for idxs in by_band.values():
        constant += p_onehot
        for i in idxs:
            linear[i] -= p_onehot
        for i, j in combinations(idxs, 2):
            _add_quadratic(quadratic, i, j, 2.0 * p_onehot)

    by_day: dict[str, list[int]] = {}
    for idx, cand in enumerate(candidates):
        by_day.setdefault(cand.day.date, []).append(idx)

    # Overlap and changeover penalties (day-wise sweep).
    for day_indices in by_day.values():
        ordered = sorted(day_indices, key=lambda i: (candidates[i].start_slot, candidates[i].end_slot))
        for pos, i in enumerate(ordered):
            left = candidates[i]
            changeover_slots = duration_to_slots(left.day.changeover_minutes, left.day.grid_minutes)
            for j in ordered[pos + 1 :]:
                right = candidates[j]
                if right.start_slot >= left.end_slot + changeover_slots:
                    break
                if right.start_slot < left.end_slot:
                    _add_quadratic(quadratic, i, j, config.penalties.overlap)
                if right.start_slot - left.end_slot < changeover_slots:
                    _add_quadratic(quadratic, i, j, config.penalties.changeover)

    # Break/unavailable penalties as linear terms.
    for idx, cand in enumerate(candidates):
        if _conflicts_break_or_unavailable(cand):
            linear[idx] += config.penalties.unavailable

    terms = {f"x::{c.band.band_id}::{c.day.date}::{c.start_slot}": linear[idx] for idx, c in enumerate(candidates)}
    metadata = {
        "candidates": str(len(candidates)),
        "target_block_counts": str(targets),
    }
    return QUBOModel(
        terms=terms,
        metadata=metadata,
        candidates=candidates,
        linear=linear,
        quadratic=quadratic,
        constant=constant,
    )


def solve_qubo(config: AppConfig, availability: ParsedAvailability, qubo: QUBOModel) -> SolveResult:
    if not qubo.candidates:
        raise NoFeasibleSolutionError("No candidate starts generated from availability. Check CSV windows and durations.")

    if config.solver.client.lower() == "amplify":
        return _solve_amplify_or_fallback(config, qubo)
    return _greedy_schedule(config, qubo, solver_name=config.solver.client)


def _solve_amplify_or_fallback(config: AppConfig, qubo: QUBOModel) -> SolveResult:
    if importlib.util.find_spec("amplify") is None:
        if config.solver.strict_optimal:
            raise SolverUnavailableError("Amplify SDK is not installed. Install fixstars-amplify.")
        return _greedy_schedule(config, qubo, "fallback(no-amplify-sdk)")

    if not os.environ.get("AMPLIFY_TOKEN"):
        msg = "AMPLIFY_TOKEN is not set. Export it (e.g., `export AMPLIFY_TOKEN=...`)"
        if config.solver.strict_optimal:
            raise SolverUnavailableError(msg)
        result = _greedy_schedule(config, qubo, "fallback(no-token)")
        return SolveResult(
            is_optimal=False,
            objective=result.objective,
            timetable=result.timetable,
            diagnostics={**result.diagnostics, "token": msg},
        )

    try:
        from amplify import AmplifyAEClient, VariableGenerator, solve
    except Exception as exc:  # pragma: no cover - depends on optional SDK installation.
        if config.solver.strict_optimal:
            raise SolverUnavailableError(f"Amplify SDK import failed: {exc}") from exc
        return _greedy_schedule(config, qubo, "fallback(amplify-import-error)")

    gen = VariableGenerator()
    x = gen.array("Binary", len(qubo.candidates))
    objective = qubo.constant
    for i, coeff in enumerate(qubo.linear):
        objective += coeff * x[i]
    for (i, j), coeff in qubo.quadratic.items():
        objective += coeff * x[i] * x[j]

    client = AmplifyAEClient()
    client.token = os.environ["AMPLIFY_TOKEN"]
    client.parameters.time_limit_ms = config.solver.timeout_ms

    try:
        result = solve(objective, client)
    except Exception as exc:  # pragma: no cover - network/remote execution.
        if config.solver.strict_optimal:
            raise SolverUnavailableError(f"Amplify solve failed: {exc}") from exc
        return _greedy_schedule(config, qubo, "fallback(amplify-solve-error)")

    try:
        assignments = _decode_solution_values(result, x)
    except ValueError as exc:
        if config.solver.strict_optimal:
            raise SolverUnavailableError(f"Amplify solution decode failed: {exc}") from exc
        return _greedy_schedule(config, qubo, "fallback(amplify-decode-error)")

    selected = [cand for idx, cand in enumerate(qubo.candidates) if assignments.get(idx, 0.0) >= 0.5]
    if not selected:
        if config.solver.strict_optimal:
            raise NoFeasibleSolutionError("Amplify returned an empty candidate selection")
        return _greedy_schedule(config, qubo, "fallback(amplify-empty)")

    entries = _materialize_entries(config, selected)
    objective_value = sum(s.score for s in selected)
    return SolveResult(
        is_optimal=False,
        objective=objective_value,
        timetable=entries,
        diagnostics={
            "solver": "amplify",
            "selected": str(len(selected)),
            "timeout_ms": str(config.solver.timeout_ms),
        },
    )


def _decode_solution_values(result: object, variable_array: object) -> dict[int, float]:
    """Decode Amplify solve() output into index->value mapping across SDK variants."""
    if isinstance(result, list):
        if not result:
            return {}
        best = result[0]
    else:
        best = getattr(result, "best", result)

    values = getattr(best, "values", None)
    if values is None:
        return {}

    if hasattr(values, "evaluate"):
        try:
            evaluated = values.evaluate(variable_array)
            return {i: _coerce_numeric_value(v) for i, v in enumerate(evaluated)}
        except Exception:
            # Fallback to per-variable extraction for SDK variants that return Poly objects.
            pass

    decoded: dict[int, float] = {}
    for i, var in enumerate(variable_array):
        raw = None
        try:
            raw = values[var]
        except Exception:
            if hasattr(values, "get"):
                try:
                    raw = values.get(var)
                except Exception:
                    raw = None
        if raw is not None:
            decoded[i] = _coerce_numeric_value(raw)
    if decoded:
        return decoded

    if isinstance(values, dict):
        out: dict[int, float] = {}
        for k, v in values.items():
            try:
                idx = int(k)
            except Exception:
                continue
            out[idx] = _coerce_numeric_value(v)
        return out

    return {i: _coerce_numeric_value(v) for i, v in enumerate(values)}


def _coerce_numeric_value(value: object) -> float:
    """Convert Amplify value/Poly-like objects to float when they are constants."""
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)

    try:
        return float(value)
    except Exception:
        pass

    is_constant_attr = getattr(value, "is_constant", None)
    if is_constant_attr is not None:
        try:
            is_constant = bool(is_constant_attr() if callable(is_constant_attr) else is_constant_attr)
        except Exception:
            is_constant = False
        if is_constant:
            const = getattr(value, "constant", None)
            if const is not None:
                try:
                    return float(const() if callable(const) else const)
                except Exception:
                    pass

    raise ValueError(f"Could not decode non-constant assignment value: {value!r}")


def _add_quadratic(quadratic: dict[tuple[int, int], float], i: int, j: int, coeff: float) -> None:
    key = (i, j) if i < j else (j, i)
    quadratic[key] = quadratic.get(key, 0.0) + coeff


def _conflicts_break_or_unavailable(cand: CandidateStart) -> bool:
    breaks = _break_intervals(cand.day)
    for b_start, b_end in breaks:
        if not (cand.end_slot <= b_start or cand.start_slot >= b_end):
            return True

    for r in cand.band.unavailable_ranges:
        u_s = time_to_slot(r.start, cand.day.start_time, cand.day.grid_minutes)
        u_e = time_to_slot(r.end, cand.day.start_time, cand.day.grid_minutes)
        if not (cand.end_slot <= u_s or cand.start_slot >= u_e):
            return True
    return False


def _slot_to_block(day: DaySpec, slot: int) -> tuple[int, int]:
    total_slots = duration_to_slots(parse_hhmm(day.end_time) - parse_hhmm(day.start_time), day.grid_minutes)
    block_size = max(1, total_slots // 3)
    block = min(2, slot // block_size)
    block_start = block * block_size
    pos_in_block = max(0, slot - block_start)
    return block, pos_in_block


def _block_position_value(config: AppConfig, block_idx: int, pos_in_block: int) -> float:
    base = config.reward.block_base_values[min(block_idx, len(config.reward.block_base_values) - 1)]
    # Lower block index => larger step subtraction, ensuring:
    # previous block end value > next block start value
    cross_block_adjust = (2 - block_idx) * config.reward.block_step
    return base + config.reward.intra_step * pos_in_block - cross_block_adjust


def _greedy_schedule(config: AppConfig, qubo: QUBOModel, solver_name: str) -> SolveResult:
    targets = ideal_block_counts(len({c.band.band_id for c in qubo.candidates}))
    selected: list[CandidateStart] = []
    used_bands: set[str] = set()
    block_count = [0, 0, 0]

    for cand in sorted(qubo.candidates, key=lambda c: (-c.score, c.day.date, c.start_slot)):
        if cand.band.band_id in used_bands:
            continue
        if _conflicts(selected, cand):
            continue
        # favor later blocks when tie / overflow target
        if block_count[cand.block_index] > targets[cand.block_index] and cand.block_index < 2:
            continue
        selected.append(cand)
        used_bands.add(cand.band.band_id)
        block_count[cand.block_index] += 1

    if not selected:
        raise NoFeasibleSolutionError("No feasible schedule found by heuristic solver")

    entries = _materialize_entries(config, selected)
    objective = sum(c.score for c in selected)
    return SolveResult(
        is_optimal=False,
        objective=objective,
        timetable=entries,
        diagnostics={
            "solver": solver_name,
            "selected": str(len(selected)),
            "target_block_counts": str(targets),
            "actual_block_counts": str(tuple(block_count)),
        },
    )


def _materialize_entries(config: AppConfig, selected: list[CandidateStart]) -> list[TimeTableEntry]:
    out: list[TimeTableEntry] = []
    by_day: dict[str, list[CandidateStart]] = {}
    for s in selected:
        by_day.setdefault(s.day.date, []).append(s)

    for day in config.event_days:
        day_selected = sorted(by_day.get(day.date, []), key=lambda x: x.start_slot)
        break_slots = _break_intervals(day)

        for b_start, b_end in break_slots:
            out.append(
                TimeTableEntry(
                    day=day.date,
                    start=slot_to_time(b_start, day.start_time, day.grid_minutes),
                    end=slot_to_time(b_end, day.start_time, day.grid_minutes),
                    label="BREAK",
                    entry_type="break",
                )
            )

        for s in day_selected:
            out.append(
                TimeTableEntry(
                    day=day.date,
                    start=slot_to_time(s.start_slot, day.start_time, day.grid_minutes),
                    end=slot_to_time(s.end_slot, day.start_time, day.grid_minutes),
                    label=s.band.band_name,
                    entry_type="band",
                )
            )

    return sorted(out, key=lambda e: (e.day, e.start, e.entry_type))


def _break_intervals(day: DaySpec) -> list[tuple[int, int]]:
    slots = duration_to_slots(parse_hhmm(day.end_time) - parse_hhmm(day.start_time), day.grid_minutes)
    durations: list[int] = []
    for br in day.breaks:
        br_slots = duration_to_slots(br.duration_minutes, day.grid_minutes)
        durations.extend([br_slots] * br.count)

    if not durations:
        return []

    n = len(durations)
    base_positions = [int((i + 1) * slots / (n + 1)) for i in range(n)]
    return [(max(0, pos - dur // 2), min(slots, max(0, pos - dur // 2) + dur)) for pos, dur in zip(base_positions, durations)]


def _conflicts(selected: list[CandidateStart], cand: CandidateStart) -> bool:
    # Break overlap and band overlap/changeover constraints.
    breaks = _break_intervals(cand.day)
    changeover_slots = duration_to_slots(cand.day.changeover_minutes, cand.day.grid_minutes)

    for b_start, b_end in breaks:
        if not (cand.end_slot <= b_start or cand.start_slot >= b_end):
            return True

    for other in selected:
        if other.day.date != cand.day.date:
            continue
        if not (cand.end_slot <= other.start_slot or cand.start_slot >= other.end_slot):
            return True

        # Changeover only between bands; breaks are handled separately.
        left, right = (cand, other) if cand.start_slot <= other.start_slot else (other, cand)
        if right.start_slot - left.end_slot < changeover_slots:
            return True

    # Unavailable windows
    for r in cand.band.unavailable_ranges:
        u_s = time_to_slot(r.start, cand.day.start_time, cand.day.grid_minutes)
        u_e = time_to_slot(r.end, cand.day.start_time, cand.day.grid_minutes)
        if not (cand.end_slot <= u_s or cand.start_slot >= u_e):
            return True

    return False
