"""
doe.py
------
Design of Experiments (DOE) sampling strategies.

Generates parameter sample sets for parametric sweeps.
All strategies work without scipy (pure Python fallback).
"""

from __future__ import annotations

import itertools
import math
import random
from typing import Sequence


def generate_samples(
    parameters: list[dict],
    strategy: str = "full_factorial",
    n_samples: int | None = None,
    seed: int = 42,
) -> list[dict]:
    """
    Generate parameter sample points based on DOE strategy.

    Parameters
    ----------
    parameters : list of parameter definitions, each with:
        path   : str  - dot-notation path (e.g., "geometry.L")
        values : list - explicit values (for full_factorial/one_at_a_time)
        min    : float - minimum (for LHS/Sobol)
        max    : float - maximum (for LHS/Sobol)
        steps  : int  - number of levels (auto-generates values from min/max)
    strategy : "full_factorial" | "latin_hypercube" | "sobol" | "one_at_a_time"
    n_samples : number of samples (required for LHS/Sobol)
    seed : random seed for reproducibility

    Returns
    -------
    list of dicts, each mapping parameter path -> value
    """
    rng = random.Random(seed)

    # Resolve parameter values
    resolved = []
    for p in parameters:
        path = p["path"]
        if "values" in p and p["values"]:
            vals = p["values"]
        elif "min" in p and "max" in p:
            steps = p.get("steps", n_samples or 5)
            vals = _linspace(p["min"], p["max"], steps)
        else:
            raise ValueError(f"Parameter '{path}' needs 'values' or 'min'/'max'")
        resolved.append({"path": path, "values": vals})

    if strategy == "full_factorial":
        return _full_factorial(resolved)
    elif strategy == "latin_hypercube":
        n = n_samples or _default_n_samples(resolved)
        return _latin_hypercube(resolved, n, rng)
    elif strategy == "sobol":
        n = n_samples or _default_n_samples(resolved)
        return _sobol_sequence(resolved, n, rng)
    elif strategy == "one_at_a_time":
        return _one_at_a_time(resolved)
    else:
        raise ValueError(f"Unknown DOE strategy: {strategy}")


def _linspace(start: float, stop: float, n: int) -> list[float]:
    """Generate n evenly spaced values from start to stop."""
    if n <= 1:
        return [start]
    step = (stop - start) / (n - 1)
    return [round(start + i * step, 10) for i in range(n)]


def _default_n_samples(params: list[dict]) -> int:
    """Default sample count based on parameter count."""
    k = len(params)
    return max(10, k * 5)


# -----------------------------------------------------------------
# DOE strategies
# -----------------------------------------------------------------

def _full_factorial(params: list[dict]) -> list[dict]:
    """Full factorial: all combinations of parameter values."""
    paths = [p["path"] for p in params]
    value_lists = [p["values"] for p in params]

    samples = []
    for combo in itertools.product(*value_lists):
        samples.append(dict(zip(paths, combo)))
    return samples


def _latin_hypercube(params: list[dict], n: int, rng: random.Random) -> list[dict]:
    """
    Latin Hypercube Sampling: ensures good coverage of each parameter range.

    Each parameter range is divided into n equal intervals, and exactly
    one sample is placed in each interval.
    """
    k = len(params)
    samples = []

    # For each parameter, create n intervals and shuffle
    intervals = []
    for p in params:
        vals = p["values"]
        v_min, v_max = min(vals), max(vals)
        # Create n evenly spaced intervals
        edges = _linspace(v_min, v_max, n + 1)
        midpoints = [(edges[i] + edges[i+1]) / 2 for i in range(n)]
        rng.shuffle(midpoints)
        intervals.append(midpoints)

    # Combine into samples
    for i in range(n):
        sample = {}
        for j, p in enumerate(params):
            sample[p["path"]] = round(intervals[j][i], 10)
        samples.append(sample)

    return samples


def _sobol_sequence(params: list[dict], n: int, rng: random.Random) -> list[dict]:
    """
    Sobol-like quasi-random sequence (simplified).

    Uses Van der Corput sequences as a pure-Python approximation
    of Sobol sequences for low-discrepancy sampling.
    """
    k = len(params)
    samples = []

    # Generate Van der Corput sequences for each dimension
    primes = _first_primes(k)

    for i in range(1, n + 1):
        sample = {}
        for j, p in enumerate(params):
            vals = p["values"]
            v_min, v_max = min(vals), max(vals)
            # Van der Corput value in [0, 1]
            vdc = _van_der_corput(i, primes[j])
            value = v_min + vdc * (v_max - v_min)
            sample[p["path"]] = round(value, 10)
        samples.append(sample)

    return samples


def _one_at_a_time(params: list[dict]) -> list[dict]:
    """
    One-at-a-time: vary one parameter while keeping others at baseline.

    Baseline = first value of each parameter.
    """
    samples = []
    baseline = {p["path"]: p["values"][0] for p in params}
    samples.append(baseline.copy())

    for p in params:
        for val in p["values"][1:]:
            sample = baseline.copy()
            sample[p["path"]] = val
            samples.append(sample)

    return samples


# -----------------------------------------------------------------
# Math helpers
# -----------------------------------------------------------------

def _van_der_corput(n: int, base: int) -> float:
    """Van der Corput sequence value for index n in given base."""
    result = 0.0
    denominator = 1.0
    while n > 0:
        denominator *= base
        n, remainder = divmod(n, base)
        result += remainder / denominator
    return result


def _first_primes(n: int) -> list[int]:
    """Return first n prime numbers."""
    primes = []
    candidate = 2
    while len(primes) < n:
        if all(candidate % p != 0 for p in primes):
            primes.append(candidate)
        candidate += 1
    return primes
