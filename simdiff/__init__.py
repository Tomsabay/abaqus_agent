"""Simulation diff helpers."""

from .kpi_diff import diff_kpis
from .run_diff import diff_runs, load_run_payload, render_run_markdown

__all__ = ["diff_kpis", "diff_runs", "load_run_payload", "render_run_markdown"]
