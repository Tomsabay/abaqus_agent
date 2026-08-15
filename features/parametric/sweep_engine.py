"""
sweep_engine.py
---------------
Parametric sweep orchestration engine.

Generates N spec variants from parameter definitions, dispatches them through
the ordinary single-run pipeline, and collects results.

Concurrency model — two INDEPENDENT knobs:

  max_parallel : how many variants may be in flight at once. Governs the
                 modelling side (CAE noGUI build + syntaxcheck), which is CPU
                 bound and, per the Abaqus docs, consumes no solver token.
  solve_slots  : how many variants may be inside the solver at once. This is
                 the license / RAM gate and defaults to 1, because one Abaqus
                 seat runs one analysis at a time. Building wide while solving
                 narrow is the point: the next variants get built while the
                 current one is still solving.

Resolution order for both knobs and for the working directory:

    environment variable  >  explicit argument  >  spec `parametric` block

    ABAQUS_AGENT_SWEEP_MAX_PARALLEL
    ABAQUS_AGENT_SWEEP_SOLVE_SLOTS
    ABAQUS_AGENT_SWEEP_WORKDIR

Resume: every finished variant drops `variant_result.json` into its own
directory, tagged with the sha256 of the variant spec. Re-running the same
sweep reports SKIPPED_CACHED for those variants and never launches Abaqus.
A changed spec changes the hash, so the variant is rebuilt.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import yaml

from features.parametric.doe import generate_samples

# Statuses whose KPIs are real solver output and may be aggregated.
SUCCESS_STATUSES = ("COMPLETED", "SKIPPED_CACHED")

ENV_MAX_PARALLEL = "ABAQUS_AGENT_SWEEP_MAX_PARALLEL"
ENV_SOLVE_SLOTS = "ABAQUS_AGENT_SWEEP_SOLVE_SLOTS"
ENV_WORKDIR = "ABAQUS_AGENT_SWEEP_WORKDIR"

CACHE_FILE = "variant_result.json"
# queue_seconds is the wait for a solver slot — kept OUT of solve_seconds so a
# serialized sweep does not report inflated solve times.
_STAGE_SECONDS = ("build_seconds", "queue_seconds", "solve_seconds", "post_seconds")


class SolveGate:
    """Solver-slot semaphore that records how many solves really overlapped.

    Wraps a BoundedSemaphore so the sweep can prove, from the archived
    sweep_results.json alone, that `solve_slots` was the thing serializing the
    solver — not an unused argument.
    """

    def __init__(self, slots: int):
        self.slots = max(1, int(slots))
        self._sem = threading.BoundedSemaphore(self.slots)
        self._lock = threading.Lock()
        self.current = 0
        self.peak = 0
        self.total_wait_seconds = 0.0

    def acquire(self, *args, **kwargs) -> bool:
        t0 = time.perf_counter()
        self._sem.acquire(*args, **kwargs)
        waited = time.perf_counter() - t0
        with self._lock:
            self.current += 1
            self.peak = max(self.peak, self.current)
            self.total_wait_seconds += waited
        return True

    def release(self) -> None:
        with self._lock:
            self.current -= 1
        self._sem.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
        return False


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
    list of {"sample": dict, "spec": dict, "index": int}
    """
    parametric = base_spec.get("parametric", {}) or {}
    parameters = parametric.get("parameters", [])
    strategy = parametric.get("strategy", "full_factorial")
    n_samples = parametric.get("n_samples")

    samples = generate_samples(parameters, strategy=strategy, n_samples=n_samples)

    specs = []
    for i, sample in enumerate(samples):
        variant = _apply_sample(base_spec, sample, i)
        specs.append({"sample": sample, "spec": variant, "index": i})

    return specs


# ---------------------------------------------------------------------------
# Knob / workdir resolution
# ---------------------------------------------------------------------------

def _env_int(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return None
    try:
        value = int(str(raw).strip())
    except ValueError:
        return None
    return value if value >= 1 else None


def _positive_int(value, default: int) -> int:
    try:
        ivalue = int(value)
    except (TypeError, ValueError):
        return default
    return ivalue if ivalue >= 1 else default


def resolve_concurrency(
    parametric: dict | None,
    max_parallel=None,
    solve_slots=None,
    default_max_parallel: int = 1,
    default_solve_slots: int = 1,
) -> tuple[int, int]:
    """
    Resolve (max_parallel, solve_slots) — env > argument > spec > default.

    solve_slots defaults to 1 and is never derived from max_parallel: a single
    license seat must gate the solves even when the builds run wide.
    """
    parametric = parametric or {}

    mp = _env_int(ENV_MAX_PARALLEL)
    if mp is None and max_parallel is not None:
        mp = _positive_int(max_parallel, 0) or None
    if mp is None and parametric.get("max_parallel") is not None:
        mp = _positive_int(parametric.get("max_parallel"), 0) or None
    if mp is None:
        mp = default_max_parallel

    ss = _env_int(ENV_SOLVE_SLOTS)
    if ss is None and solve_slots is not None:
        ss = _positive_int(solve_slots, 0) or None
    if ss is None and parametric.get("solve_slots") is not None:
        ss = _positive_int(parametric.get("solve_slots"), 0) or None
    if ss is None:
        ss = default_solve_slots

    return mp, ss


def resolve_workdir(base_spec: dict, workdir: str | Path | None) -> Path:
    """Resolve the sweep working directory — env > spec > argument."""
    parametric = base_spec.get("parametric", {}) or {}
    env_dir = os.environ.get(ENV_WORKDIR, "").strip()
    if env_dir:
        return Path(env_dir)
    spec_dir = str(parametric.get("workdir", "") or "").strip()
    if spec_dir:
        return Path(spec_dir)
    if workdir:
        return Path(workdir)
    raise ValueError(
        "No sweep workdir: pass workdir=, set parametric.workdir, "
        f"or set {ENV_WORKDIR}"
    )


def spec_fingerprint(spec: dict) -> str:
    """Stable sha256 of a variant spec — the resume cache key."""
    payload = json.dumps(spec, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Sweep driver
# ---------------------------------------------------------------------------

def run_sweep(
    base_spec: dict,
    workdir: str | Path | None = None,
    max_parallel=None,
    solve_slots=None,
    on_progress=None,
    variant_runner=None,
    resume: bool = True,
    runner_cfg: dict | None = None,
    export_visuals: bool | None = None,
    verbose: bool = True,
) -> dict:
    """
    Run a full parametric sweep.

    Parameters
    ----------
    base_spec      : dict with 'parametric' section
    workdir        : base working directory (see resolve_workdir precedence)
    max_parallel   : max variants in flight (build side)
    solve_slots    : max variants inside the solver at once (license gate)
    on_progress    : callback(done, total, status, result)
    variant_runner : callable(spec, variant_dir, solve_gate, options) -> dict,
                     defaults to `_execute_variant` (the real pipeline)
    resume         : honour per-variant caches (SKIPPED_CACHED)

    Returns
    -------
    dict with samples/results/summary plus max_parallel, solve_slots and
    wall_clock_seconds at the top level.
    """
    started = time.perf_counter()
    started_at = datetime.now().isoformat()

    parametric = base_spec.get("parametric", {}) or {}
    workdir = resolve_workdir(base_spec, workdir)
    sweep_dir = workdir / "parametric_sweep"
    sweep_dir.mkdir(parents=True, exist_ok=True)

    max_parallel, solve_slots = resolve_concurrency(
        parametric, max_parallel, solve_slots
    )
    if export_visuals is None:
        export_visuals = bool(parametric.get("export_visuals", False))

    variants = generate_sweep_specs(base_spec)
    total = len(variants)
    results: list[dict | None] = [None] * total

    if on_progress:
        on_progress(0, total, "starting", {})
    if verbose:
        print(
            "[sweep] %d variants | max_parallel=%d solve_slots=%d | %s"
            % (total, max_parallel, solve_slots, sweep_dir),
            flush=True,
        )

    # Save all variant specs up front (a sweep is inspectable before it runs)
    for v in variants:
        spec_dir = sweep_dir / f"variant_{v['index']:04d}"
        spec_dir.mkdir(parents=True, exist_ok=True)
        (spec_dir / "spec.yaml").write_text(
            yaml.dump(v["spec"], allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

    runner = variant_runner or _execute_variant
    solve_gate = SolveGate(solve_slots)
    options = {
        "runner_cfg": runner_cfg,
        "export_visuals": export_visuals,
    }
    lock = threading.Lock()
    done = [0]
    in_flight = [0]
    peak_in_flight = [0]

    def worker(v: dict) -> dict:
        idx = v["index"]
        variant_dir = sweep_dir / f"variant_{idx:04d}"
        fingerprint = spec_fingerprint(v["spec"])

        record = _load_cached_variant(variant_dir, fingerprint) if resume else None
        if record is None:
            t_variant = time.perf_counter()
            started_variant = datetime.now().isoformat()
            with lock:
                in_flight[0] += 1
                peak_in_flight[0] = max(peak_in_flight[0], in_flight[0])
            try:
                outcome = runner(v["spec"], variant_dir, solve_gate, options)
            except Exception as e:  # never let one variant kill the sweep
                outcome = {"status": "ERROR", "error": f"{type(e).__name__}: {e}"}
            finally:
                with lock:
                    in_flight[0] -= 1
            record = {
                "index": idx,
                "sample": v["sample"],
                "spec_sha256": fingerprint,
                "status": outcome.get("status", "UNKNOWN"),
                "kpis": outcome.get("kpis", {}),
                "variant_dir": str(variant_dir),
                "cached": False,
                "started_at": started_variant,
                "finished_at": datetime.now().isoformat(),
                "elapsed_seconds": round(time.perf_counter() - t_variant, 3),
            }
            for key in _STAGE_SECONDS:
                record[key] = outcome.get(key, 0.0)
            if outcome.get("error"):
                record["error"] = outcome["error"]
            _save_variant_cache(variant_dir, record)
        else:
            record["index"] = idx
            record["sample"] = v["sample"]

        results[idx] = record
        with lock:
            done[0] += 1
            position = done[0]
        if verbose:
            print(_format_line(record, position, total), flush=True)
        if on_progress:
            on_progress(position, total, record["status"], record)
        return record

    with ThreadPoolExecutor(max_workers=max(1, max_parallel)) as pool:
        list(pool.map(worker, variants))

    wall_clock = round(time.perf_counter() - started, 3)
    summary = _generate_summary(variants, results)

    sweep_result = {
        "total_variants": total,
        "strategy": parametric.get("strategy", "full_factorial"),
        "parameters": parametric.get("parameters", []),
        "max_parallel": max_parallel,
        "solve_slots": solve_slots,
        "wall_clock_seconds": wall_clock,
        "peak_variants_in_flight": peak_in_flight[0],
        "peak_concurrent_solves": solve_gate.peak,
        "solve_queue_seconds_total": round(solve_gate.total_wait_seconds, 3),
        "workdir": str(workdir),
        "sweep_dir": str(sweep_dir),
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(),
        "samples": [v["sample"] for v in variants],
        "results": results,
        "summary": summary,
    }

    (sweep_dir / "sweep_results.json").write_text(
        json.dumps(sweep_result, indent=2, default=str),
        encoding="utf-8",
    )
    write_results_csv(sweep_result, sweep_dir / "results.csv")

    if verbose:
        print(
            "[sweep] done: %d/%d usable, wall_clock=%.1fs, "
            "peak_in_flight=%d, peak_concurrent_solves=%d, queue_wait=%.1fs"
            % (
                summary["completed"],
                total,
                wall_clock,
                peak_in_flight[0],
                solve_gate.peak,
                solve_gate.total_wait_seconds,
            ),
            flush=True,
        )
    if on_progress:
        on_progress(total, total, "completed", summary)

    return sweep_result


def _format_line(record: dict, position: int, total: int) -> str:
    sample = " ".join(
        "%s=%s" % (k.split(".")[-1], v) for k, v in sorted(record["sample"].items())
    )
    return (
        "[sweep] %2d/%-2d %-14s variant_%04d %-18s "
        "build %6.1fs queue %6.1fs solve %6.1fs post %6.1fs"
    ) % (
        position,
        total,
        record["status"],
        record["index"],
        sample,
        record.get("build_seconds") or 0.0,
        record.get("queue_seconds") or 0.0,
        record.get("solve_seconds") or 0.0,
        record.get("post_seconds") or 0.0,
    )


# ---------------------------------------------------------------------------
# Resume cache
# ---------------------------------------------------------------------------

def _load_cached_variant(variant_dir: Path, fingerprint: str) -> dict | None:
    """Return a SKIPPED_CACHED record if this variant already solved."""
    cache_path = variant_dir / CACHE_FILE
    if not cache_path.exists():
        return None
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if cached.get("status") not in SUCCESS_STATUSES:
        return None
    if cached.get("spec_sha256") != fingerprint:
        return None
    if not cached.get("kpis"):
        return None

    record = dict(cached)
    record["status"] = "SKIPPED_CACHED"
    record["cached"] = True
    record["cached_from"] = str(cache_path)
    record["elapsed_seconds"] = 0.0
    return record


def _save_variant_cache(variant_dir: Path, record: dict) -> None:
    try:
        variant_dir.mkdir(parents=True, exist_ok=True)
        (variant_dir / CACHE_FILE).write_text(
            json.dumps(record, indent=2, default=str), encoding="utf-8"
        )
    except OSError:
        pass


# ---------------------------------------------------------------------------
# One variant through the real pipeline
# ---------------------------------------------------------------------------

def _execute_variant(
    spec: dict,
    variant_dir: Path,
    solve_gate=None,
    options: dict | None = None,
) -> dict:
    """
    Run a single variant: build (+syntaxcheck) → solve (gated) → post.

    Only the solver stage takes a slot from `solve_gate`; syntaxcheck consumes
    no license token (Abaqus analysis-execution docs) and stays on the build
    side so builds can overlap a running solve.
    """
    from tools.errors import AbaqusAgentError

    options = options or {}
    variant_dir = Path(variant_dir)
    variant_dir.mkdir(parents=True, exist_ok=True)

    spec_path = variant_dir / "spec.yaml"
    if not spec_path.exists():
        spec_path.write_text(
            yaml.dump(spec, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

    from agent.orchestrator import AbaqusOrchestrator

    orch = AbaqusOrchestrator(
        spec_path=str(spec_path),
        workdir=str(variant_dir),
        runner_cfg=options.get("runner_cfg"),
    )

    timings = {key: 0.0 for key in _STAGE_SECONDS}
    gate = solve_gate if solve_gate is not None else SolveGate(1)

    try:
        orch._stage_validate()

        t0 = time.perf_counter()
        build = orch._stage_build()
        inp_path = build["inp_path"]
        run_dir = Path(build["workdir"])
        if orch.runner_cfg.get("syntaxcheck_first", True):
            orch._stage_syntaxcheck(inp_path, run_dir)
        timings["build_seconds"] = round(time.perf_counter() - t0, 3)

        # Queue wait is measured separately: with one solver slot the 5th
        # variant waits minutes for the gate, and folding that into
        # solve_seconds would misreport the solver's own cost.
        t0 = time.perf_counter()
        gate.acquire()
        timings["queue_seconds"] = round(time.perf_counter() - t0, 3)
        try:
            t0 = time.perf_counter()
            submit = orch._stage_submit(inp_path, run_dir)
            orch._stage_monitor(submit)
            timings["solve_seconds"] = round(time.perf_counter() - t0, 3)
        finally:
            gate.release()

        t0 = time.perf_counter()
        odb_path = run_dir / f"{spec['meta']['model_name']}.odb"
        kpi_result = orch._stage_extract(odb_path)
        if options.get("export_visuals"):
            orch._stage_export_visuals(odb_path)
        orch._stage_contracts(kpi_result.get("kpis", {}))
        timings["post_seconds"] = round(time.perf_counter() - t0, 3)

        kpis = kpi_result.get("kpis", {}) or {}
        if not kpis:
            orch.result["status"] = "FAILED"
            orch._save_result()
            return {
                "status": "FAILED",
                "kpis": {},
                "error": "no KPIs extracted from %s" % odb_path.name,
                **timings,
            }

        orch.result["status"] = "COMPLETED"
        orch.result["finished_at"] = datetime.now().isoformat()
        orch.result["stage_seconds"] = dict(timings)
        try:
            orch._save_capsule()
        except Exception:
            pass
        orch._save_result()

        return {"status": "COMPLETED", "kpis": kpis, "workdir": str(run_dir), **timings}

    except AbaqusAgentError as e:
        orch.result["status"] = "FAILED"
        orch.result["error"] = e.to_dict()
        orch._save_result()
        return {"status": "FAILED", "kpis": {}, "error": str(e), **timings}
    except Exception as e:
        orch.result["status"] = "ERROR"
        orch.result["error"] = {"error_code": "UNKNOWN", "message": str(e)}
        orch._save_result()
        return {
            "status": "ERROR",
            "kpis": {},
            "error": f"{type(e).__name__}: {e}",
            **timings,
        }


# ---------------------------------------------------------------------------
# Spec variant helpers
# ---------------------------------------------------------------------------

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


class SweepPathError(ValueError):
    """A parametric path that does not name a value the base spec already has."""


def _names_in(node) -> str:
    """Labels for a list's entries, so a user need not count to write an index.

    Reads whatever the entries call themselves; a list of plain numbers yields
    nothing and the message falls back to the index range.
    """
    labels = []
    for i, item in enumerate(node):
        name = item.get("name") if isinstance(item, dict) else None
        if name is not None:
            labels.append("%d=%s" % (i, name))
    return ", ".join(labels)


def _slot(node, key, path, walked):
    """Normalise one path segment against the container it addresses.

    Returns a dict key or a list index. Refuses rather than creating anything:
    a sweep moves a value the spec already carries, and a segment that names
    nothing is a typo, not a request.
    """
    where = ".".join(walked) or "the spec root"
    if isinstance(node, dict):
        if key in node:
            return key
        raise SweepPathError(
            "parametric path %r: %s has no key %r. Keys there: %s. A sweep "
            "moves a value the spec already carries -- add %s to the base "
            "spec with its baseline value, then sweep it."
            % (path, where, key,
               ", ".join(sorted(map(str, node))) or "(none)", path))
    if isinstance(node, list):
        entries = _names_in(node)
        entries = (". Entries: " + entries) if entries else ""
        try:
            index = int(str(key).strip())
        except ValueError:
            raise SweepPathError(
                "parametric path %r: %s is a list of %d, so %r must be a list "
                "index (0..%d)%s."
                % (path, where, len(node), key, len(node) - 1, entries))
        if not -len(node) <= index < len(node):
            raise SweepPathError(
                "parametric path %r: %s is a list of %d, so index %d is out "
                "of range (0..%d)%s."
                % (path, where, len(node), index, len(node) - 1, entries))
        return index
    raise SweepPathError(
        "parametric path %r: %s is %s (%r), so %r cannot be looked up under "
        "it. A sweep path ends at the number it changes."
        % (path, where, type(node).__name__, node, key))


def _set_nested(d: dict, path: str, value) -> None:
    """Set a value the spec already has, addressed by dots and list indices.

    Refuses a path that names nothing. `setdefault` used to create the key,
    which turned one typo into N identical models: every variant solved,
    reported COMPLETED, cost a full solve each because the invented key made
    each resume fingerprint unique, and the sensitivity report read 0.0000.
    """
    if not str(path).strip():
        raise SweepPathError(
            "parametric path is empty; write the dotted path of the value to "
            "sweep, e.g. geometry.H or parts.0.mesh.seed")
    keys = str(path).split(".")
    node = d
    for i, key in enumerate(keys[:-1]):
        node = node[_slot(node, key, path, keys[:i])]
    node[_slot(node, keys[-1], path, keys[:-1])] = value


def _get_nested(d: dict, path: str, default=None):
    """Get a value by the same dotted path `_set_nested` writes.

    List-aware for the same reason the setter is: every v2 sweepable number
    (`parts.0.mesh.seed`) sits behind a list index, and a getter that stops at
    the first list would answer `default` for a path that resolves.
    """
    node = d
    for key in str(path).split("."):
        if isinstance(node, dict):
            if key not in node:
                return default
            node = node[key]
        elif isinstance(node, list):
            try:
                index = int(str(key).strip())
            except ValueError:
                return default
            if not -len(node) <= index < len(node):
                return default
            node = node[index]
        else:
            return default
    return node


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def write_results_csv(sweep_result: dict, csv_path: str | Path) -> Path:
    """Flat one-row-per-variant CSV (the table the course reads on camera)."""
    csv_path = Path(csv_path)
    results = [r for r in sweep_result.get("results", []) if r]

    param_paths: list[str] = []
    for p in sweep_result.get("parameters", []):
        if p.get("path") and p["path"] not in param_paths:
            param_paths.append(p["path"])
    for r in results:
        for path in r.get("sample", {}):
            if path not in param_paths:
                param_paths.append(path)

    kpi_names: list[str] = []
    for r in results:
        for name in r.get("kpis", {}):
            if name not in kpi_names:
                kpi_names.append(name)
    kpi_names.sort()

    header = (
        ["index"]
        + param_paths
        + ["status"]
        + list(_STAGE_SECONDS)
        + kpi_names
        + ["variant_dir"]
    )

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for r in sorted(results, key=lambda x: x.get("index", 0)):
            row = [r.get("index")]
            row += [r.get("sample", {}).get(path, "") for path in param_paths]
            row += [r.get("status", "")]
            row += [r.get(key, "") for key in _STAGE_SECONDS]
            for name in kpi_names:
                value = r.get("kpis", {}).get(name, "")
                if isinstance(value, dict):
                    value = value.get("value", "")
                row.append(value)
            row.append(r.get("variant_dir", ""))
            writer.writerow(row)
    return csv_path


def _generate_summary(variants: list[dict], results: list) -> dict:
    """Generate summary statistics from sweep results."""
    usable = [r for r in results if r and r.get("status") in SUCCESS_STATUSES]
    cached = [r for r in usable if r.get("status") == "SKIPPED_CACHED"]
    failed = [r for r in results if r and r.get("status") not in SUCCESS_STATUSES]

    summary = {
        "total": len(variants),
        "completed": len(usable),
        "cached": len(cached),
        "failed": len(failed),
        "completion_rate": len(usable) / max(len(variants), 1),
    }

    # Aggregate KPIs across all usable variants
    if usable:
        all_kpi_names = set()
        for r in usable:
            all_kpi_names.update(r.get("kpis", {}).keys())

        kpi_stats = {}
        for name in all_kpi_names:
            values = []
            for r in usable:
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
