"""Error hierarchy for recoverable failures with user-friendly messages."""

from __future__ import annotations


class UserVisibleError(Exception):
    """Recoverable error that can be shown to end users safely."""


class ConfigError(UserVisibleError):
    """Invalid or inconsistent runtime configuration."""


class CSVFormatError(UserVisibleError):
    """Invalid input CSV schema or data."""


class OutputWriteError(UserVisibleError):
    """Output directory/file write failure."""


class SolverUnavailableError(UserVisibleError):
    """Solver dependency or credential is unavailable."""


class NoFeasibleSolutionError(UserVisibleError):
    """No feasible/optimal solution was found."""


class ValidationError(UserVisibleError):
    """Solver output validation failed."""
