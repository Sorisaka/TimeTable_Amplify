"""Backward-compatible exports for QUBO module."""

from .qubo_builder import QUBOModel, build_qubo, ideal_block_counts, solve_qubo

__all__ = ["QUBOModel", "build_qubo", "solve_qubo", "ideal_block_counts"]
