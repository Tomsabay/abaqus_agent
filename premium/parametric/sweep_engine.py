"""
sweep_engine.py
---------------
Parametric sweep orchestration engine.

Generates N spec variants from parameter definitions,
dispatches them through the pipeline, and collects results.
"""

from __future__ import annotations

import copy
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import yaml

from premium.parametric.doe import generate_samples


def parametric_pre_build_hook(context: dict) -> dict:
    """
    Pipeline hook: intercept specs with parametric configuration.

    If the spec has a 'parametric' section, this hook signals
    the orchestrator to run a sweep instead of a single analysis.
    """
    spec = context.get("spec", {})
    parametric = spec.get("parametric")

    if parametric and parametric.get("parameters"):
        context["is_parametric"] = True
        context["parametric_config"] = parametric
    return context


def generate_sweep_specs(base_spec: dict) -> list[dict]:
    """
    Generate all spec variants for a parametric sweep.

    Parameters
    ----------
    base_spec : dict with 'parametric' section

    Returns
    -------
    list of (sample_dict, modified_spec) tuples
    """
    parametric = base_spec.get("parametric", {})
    parameters = parametric.get("parameters", [])
    strategy = parametric.get("strategy", "full_factorial")
    n_samples = parametric.get("n_samples")

    samples = generate_samples(parameters, strategy=strategy, n_samples=n_samples)

    specs = []
    for i, sample in enumerate(samples):
        variant = _apply_sample(base_spec, sample, i)
        specs.append({"sample": sample, "spec": variant, "index": i})

    return specs


def run_sweep(
    base_spec: dict,
    workdir: str | Path,
    max_parallel: int = 4,
    on_progress=None,
) -> dict:
    """
    Run a full parametric sweep.

    Parameters
    ----------
    base_spec    : dict with 'parametric' section
    workdir      : base working directory
    max_parallel : max concurrent jobs
    on_progress  : callback(index, total, status, result)

    Returns
    -------
    dict with:
        samples  : list of sample dicts
        results  : list of per-sample results
        summary  : aggregated statistics
    """
    workdir = Path(workdir)
    sweep_dir = workdir / "parametric_sweep"
    sweep_dir.mkdir(parents=True, exist_ok=True)

    variants = generate_sweep_specs(base_spec)
    total = len(variants)
    results = [None] * total

    if on_progress:
        on_progress(0, total, "starting", {})

    # Save all variant specs
    for v in variants:
        spec_dir = sweep_dir / f"variant_{v['index']:04d}"
        spec_dir.mkdir(parents=True, exist_ok=True)
        spec_path = spec_dir / "spec.yaml"
        spec_path.write_text(
            yaml.dump(v["spec"], allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

    # Run variants (sequentially for safety; parallel with ProcessPoolExecutor)
    for v in variants:
        idx = v["index"]
        spec_dir = sweep_dir / f"variant_{idx:04d}"

        try:
            result = _run_single_variant(v["spec"], spec_dir)
            results[idx] = {
                "index": idx,
                "sample": v["sample"],
                "status": result.get("status", "UNKNOWN"),
                "kpis": result.get("kpis", {}),
            }
        except Exception as e:
            results[idx] = {
                "index": idx,
                "sample": v["sample"],
                "status": "ERROR",
                "error": str(e),
            }

        if on_progress:
            on_progress(idx + 1, total, "running", results[idx])

    # Generate summary
    summary = _generate_summary(variants, results)

    # Save sweep results
    sweep_result = {
        "total_variants": total,
        "strategy": base_spec.get("parametric", {}).get("strategy", "full_factorial"),
        "parameters": base_spec.get("parametric", {}).get("parameters", []),
        "results": results,
        "summary": summary,
    }

    result_path = sweep_dir / "sweep_results.json"
    result_path.write_text(
        json.dumps(sweep_result, indent=2, default=str),
        encoding="utf-8",
    )

    if on_progress:
        on_progress(total, total, "completed", summary)

    return sweep_result


def _run_single_variant(spec: dict, workdir: Path) -> dict:
    """Run a single parametric variant through the pipeline."""
    # Import here to avoid circular imports
    from agent.orchestrator import AbaqusOrchestrator

    spec_path = workdir / "spec.yaml"
    if not spec_path.exists():
        spec_path.write_text(
            yaml.dump(spec, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

    orch = AbaqusOrchestrator(
        spec_path=str(spec_path),
        workdir=str(workdir),
    )
    return orch.run()


def _apply_sample(base_spec: dict, sample: dict, index: int) -> dict:
    """Apply a parameter sample to create a spec variant."""
    variant = copy.deepcopy(base_spec)

    # Remove parametric section from variant (it's a single run)
    variant.pop("parametric", None)

    # Apply each parameter value
    for path, value in sample.items():
        _set_nested(variant, path, value)

    # Update model name for uniqueness
    meta = variant.setdefault("meta", {})
    base_name = meta.get("model_name", "Model")
    meta["model_name"] = f"{base_name}_v{index:04d}"
    meta["description"] = (
        meta.get("description", "") + f" [Parametric variant {index}]"
    ).strip()

    return variant


def _set_nested(d: dict, path: str, value) -> None:
    """Set a nested dict value using dot-notation path."""
    keys = path.split(".")
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value


def _get_nested(d: dict, path: str, default=None):
    """Get a nested dict value using dot-notation path."""
    keys = path.split(".")
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key, default)
        else:
            return default
    return d


def _generate_summary(variants: list[dict], results: list) -> dict:
    """Generate summary statistics from sweep results."""
    completed = [r for r in results if r and r.get("status") == "COMPLETED"]
    failed = [r for r in results if r and r.get("status") != "COMPLETED"]

    summary = {
        "total": len(variants),
        "completed": len(completed),
        "failed": len(failed),
        "completion_rate": len(completed) / max(len(variants), 1),
    }

    # Aggregate KPIs across all completed variants
    if completed:
        all_kpi_names = set()
        for r in completed:
            all_kpi_names.update(r.get("kpis", {}).keys())

        kpi_stats = {}
        for name in all_kpi_names:
            values = []
            for r in completed:
                kpi = r.get("kpis", {}).get(name)
                if kpi is not None:
                    val = kpi.get("value", kpi) if isinstance(kpi, dict) else kpi
                    if isinstance(val, (int, float)):
                        values.append(val)

            if values:
                kpi_stats[name] = {
                    "min": min(values),
                    "max": max(values),
                    "mean": sum(values) / len(values),
                    "range": max(values) - min(values),
                    "n_samples": len(values),
                }

        summary["kpi_statistics"] = kpi_stats

    return summary
