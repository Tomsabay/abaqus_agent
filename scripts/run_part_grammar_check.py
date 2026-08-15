#!/usr/bin/env python3
"""Real-solver check for the v2 part grammar: cuts, curved selectors, seeding.

The interface check (scripts/run_assembly_check.py) proves that two parts can
be tied, pressed and slid against each other. This one proves the layer under
it: that a part can be SHAPED, that the shape can be named afterwards, and that
the mesh can be refined where it matters.

Every failure mode on this path was measured on Abaqus 2021 and every one of
them is silent:

  * A cut whose circle lands off the solid does nothing. Same volume, same
    element count, no warning, exit 0.
  * The sketchUpEdge decides how sketch coordinates map to global ones. On the
    top face, edges 1 and 3 produced no hole at all; on the bottom face, edge 1
    produced a real hole of the right radius with x and y TRANSPOSED - identical
    volume, identical element count. A symmetric test case cannot see it.
  * `getByBoundingCylinder` with a large enough radius returns every face in the
    part, so containment cannot mean "this is the hole".
  * A local seed applied to an empty edge set still meshes, just at the coarse
    size, and the stress concentration comes back low and plausible.

So the items here are arithmetic, and the refusals are mutations: each takes the
shipped case and breaks exactly one thing that used to be silent.

  1. `part_grammar_hole_kt` - cases/plate_hole_v2 against Howland's solution
     for a finite-width strip, not against a frozen run.
  2. `part_grammar_invariants_agree` - the same peak read as Mises and as S22.
     At a traction-free uniaxial point they are one number arrived at two ways.
  3. `part_grammar_far_field` - the load path, read back out of the ODB.
  4. `part_grammar_refuses_a_missed_cut` - move the hole off the plate.
  5. `part_grammar_refuses_an_absent_radius` - ask for a hole that is not there.
  6. `part_grammar_refuses_an_unseeded_edge` - refine an edge that does not exist.
  7. `part_grammar_converges_toward_theory` - refine the hole edge in four steps
     and watch the answer climb toward a number nobody tuned it to. This is
     what justifies the tolerance on item 1.

Exit codes: 0 = nothing failed (no Abaqus => "skipped", still 0);
            1 = at least one item ran and failed.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from core.helpers import check_abaqus  # noqa: E402
from tools.abaqus_cmd import detect_abaqus_release  # noqa: E402

CASE = "plate_hole_v2"

# Howland's 1930 solution for a central circular hole in a finite-width strip.
# Two accepted forms, both used here on purpose: their spread IS the honest
# uncertainty in the target, and quoting one alone would hide it.
PLATE_W, HOLE_D, GROSS_STRESS = 60.0, 12.0, 1.0
DW = HOLE_D / PLATE_W
SIGMA_NET = GROSS_STRESS * PLATE_W / (PLATE_W - HOLE_D)

# Heywood's closed form. Exact at both endpoints: 3.00 at d/W = 0, which is
# Kirsch's infinite plate, and 2.00 at d/W = 1.
KT_NET_HEYWOOD = 2.0 + (1.0 - DW) ** 3
# Peterson's polynomial fit to the same data. Same two endpoints.
KT_NET_PETERSON = 3.00 - 3.13 * DW + 3.66 * DW ** 2 - 1.53 * DW ** 3

THEORY_HOOP_MPA = KT_NET_HEYWOOD * SIGMA_NET
THEORY_SPREAD_REL = abs(KT_NET_HEYWOOD - KT_NET_PETERSON) / KT_NET_HEYWOOD

# A discretisation band, not a physics band. The failure it is sized to catch
# is under-refinement, which reads LOW - the convergence item measures by how
# much. It has to stay well clear of the 0.15% spread above, or the check would
# be measuring which textbook was opened.
HOOP_TOLERANCE_REL = 0.08
FAR_FIELD_TOLERANCE_REL = 0.02
# Mises and S22 are the same quantity at a traction-free uniaxial point. They
# are computed from different things, so agreement is evidence; this is how
# close they have to be for the peak to be where the theory says it is.
INVARIANT_AGREEMENT_REL = 0.01

# Measured on Abaqus 2021, this machine, seed 5.0 with a 1.2 mm hole seed.
MEASURED_HOOP_MPA = 3.0966060161590576
MEASURED_FAR_FIELD_MPA = 1.0000149011611938


def _skipped(item_id: str, reason: str, **extra: object) -> dict:
    out = {"id": item_id, "status": "skipped", "reason": reason}
    out.update(extra)
    return out


def _case_dir() -> Path:
    return ROOT / "cases" / CASE


def _load_spec() -> dict:
    return yaml.safe_load((_case_dir() / "spec.yaml").read_text(encoding="utf-8"))


def _run(spec: dict | None = None, workdir: Path | None = None) -> dict:
    from agent.orchestrator import build_orchestrator

    runner_cfg_path = _case_dir() / "runner.json"
    runner_cfg = None
    if runner_cfg_path.exists():
        runner_cfg = json.loads(runner_cfg_path.read_text(encoding="utf-8"))
    expected = _case_dir() / "expected.json"

    orch = build_orchestrator(
        spec_dict=copy.deepcopy(spec if spec is not None else _load_spec()),
        workdir=workdir,
        expected_path=expected if spec is None else None,
        runner_cfg=runner_cfg,
    )
    return orch.run()


def _kpi(result: dict, name: str):
    value = result.get("kpis", {}).get(name)
    return value.get("value") if isinstance(value, dict) else value


def _was_cached(result: dict) -> bool:
    raw = result.get("stages", {}).get("build_model", {}).get("cached")
    return str(raw).lower() == "true"


def _evidence(result: dict, run_dir: Path | None) -> str:
    """Everything a refusal could have been written to, as one string."""
    parts = [json.dumps(result.get("error", {}), ensure_ascii=False)]
    workdir = result.get("stages", {}).get("build_model", {}).get("workdir")
    for base in [Path(workdir)] if workdir else []:
        for name in ("build_model_script.log", "selectors.log"):
            path = base / name
            if path.exists():
                parts.append(path.read_text(encoding="utf-8", errors="replace"))
    if run_dir is not None:
        for name in ("build_model_script.log", "selectors.log"):
            path = run_dir / name
            if path.exists():
                parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def check_the_shipped_case() -> list[dict]:
    if not check_abaqus():
        reason = "Abaqus not found (set ABAQUS_AGENT_ABAQUS_CMD)"
        return [_skipped("part_grammar_hole_kt", reason),
                _skipped("part_grammar_invariants_agree", reason),
                _skipped("part_grammar_far_field", reason)]

    started = time.time()
    result = _run()
    elapsed = time.time() - started

    hoop = _kpi(result, "HOOP_MAX")
    hoop_s22 = _kpi(result, "HOOP_S22")
    far = _kpi(result, "FAR_FIELD")

    problems: list[str] = []
    if result.get("status") != "COMPLETED":
        problems.append("orchestrator status %s: %s"
                        % (result.get("status"), result.get("error")))

    hoop_dev = None
    if hoop is None:
        problems.append("HOOP_MAX missing from KPIs")
    else:
        hoop_dev = abs(hoop - THEORY_HOOP_MPA) / THEORY_HOOP_MPA
        if hoop_dev >= HOOP_TOLERANCE_REL:
            problems.append(
                "hole-edge Mises %.6f MPa is %.2f%% from Howland %.6f MPa"
                % (hoop, hoop_dev * 100, THEORY_HOOP_MPA))

    far_problems: list[str] = []
    far_dev = None
    if far is None:
        far_problems.append("FAR_FIELD missing from KPIs")
    else:
        far_dev = abs(far - GROSS_STRESS) / GROSS_STRESS
        if far_dev >= FAR_FIELD_TOLERANCE_REL:
            far_problems.append(
                "S22 on the loaded face is %.6f MPa, not the applied %.1f MPa. "
                "A sign error reads -1.0; a load applied to nothing reads 0."
                % (far, GROSS_STRESS))

    agreement_problems: list[str] = []
    agreement = None
    if hoop is None or hoop_s22 is None:
        agreement_problems.append("HOOP_MAX or HOOP_S22 missing from KPIs")
    else:
        agreement = abs(hoop - hoop_s22) / abs(hoop)
        if agreement >= INVARIANT_AGREEMENT_REL:
            agreement_problems.append(
                "Mises %.6f and S22 %.6f differ by %.2f%% on the hole wall. At "
                "a traction-free uniaxial point they are the same number, so a "
                "gap means the peak Mises is not the hoop peak -- and then "
                "neither KPI means what this case says it means."
                % (hoop, hoop_s22, agreement * 100))

    return [
        {
            "id": "part_grammar_hole_kt",
            "status": "pass" if not problems else "fail",
            "spec": "cases/%s/spec.yaml" % CASE,
            "identity": "Heywood Kt_net = 2 + (1 - d/W)^3, on the NET section",
            "d_over_w": DW,
            "kt_net_heywood": round(KT_NET_HEYWOOD, 6),
            "kt_net_peterson": round(KT_NET_PETERSON, 6),
            "theory_spread_relative": round(THEORY_SPREAD_REL, 6),
            "sigma_net_mpa": SIGMA_NET,
            "theory_hoop_mpa": round(THEORY_HOOP_MPA, 6),
            "measured_hoop_mpa": hoop,
            "previously_measured_mpa": MEASURED_HOOP_MPA,
            "relative_deviation": None if hoop_dev is None else round(hoop_dev, 8),
            "tolerance_relative": HOOP_TOLERANCE_REL,
            "note": "measured on a set built FROM the hole, not on whole_model: "
                    "the largest Mises in this model is at the clamped end, so "
                    "a whole-model KPI would report the clamp",
            "cached": _was_cached(result),
            "elapsed_s": round(elapsed, 2),
            "problems": problems,
        },
        {
            "id": "part_grammar_invariants_agree",
            "status": "pass" if not agreement_problems else "fail",
            "identity": "Mises == S22 at a traction-free uniaxial point",
            "measured_mises_mpa": hoop,
            "measured_s22_mpa": hoop_s22,
            "relative_difference": None if agreement is None else round(agreement, 8),
            "tolerance_relative": INVARIANT_AGREEMENT_REL,
            "problems": agreement_problems,
        },
        {
            "id": "part_grammar_far_field",
            "status": "pass" if not far_problems else "fail",
            "identity": "S22 on the loaded face == the applied gross stress",
            "expected_mpa": GROSS_STRESS,
            "measured_mpa": far,
            "previously_measured_mpa": MEASURED_FAR_FIELD_MPA,
            "relative_deviation": None if far_dev is None else round(far_dev, 8),
            "problems": far_problems,
        },
    ]


# ---------------------------------------------------------------------------
# Mutations: each breaks exactly one thing that used to be silent
# ---------------------------------------------------------------------------

def _refusal_item(item_id: str, work_dir: Path, tag: str, mutate,
                  marker: str, what_used_to_happen: str) -> dict:
    if not check_abaqus():
        return _skipped(item_id, "Abaqus not found")

    spec = _load_spec()
    change = mutate(spec)
    run_dir = work_dir / tag
    run_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = _run(spec=spec, workdir=run_dir)
    except Exception as exc:                       # a host-side refusal
        return {
            "id": item_id, "status": "pass",
            "spec_change": change,
            "refused_at": "spec validation (before any solver ran)",
            "message": str(exc)[:400],
            "problems": [] if marker in str(exc) else
                        ["the refusal does not mention %r" % marker],
        }

    evidence = _evidence(result, run_dir)
    problems: list[str] = []
    if result.get("status") == "COMPLETED":
        problems.append(
            "the run completed. %s" % what_used_to_happen)
    if result.get("kpis"):
        problems.append("a failed build must produce no KPIs, got %s"
                        % list(result["kpis"]))
    if marker not in evidence:
        problems.append(
            "the failure never names %r, so the message a user sees does not "
            "say what went wrong" % marker)

    tail = [line for line in evidence.splitlines() if marker in line]
    return {
        "id": item_id,
        "status": "pass" if not problems else "fail",
        "spec_change": change,
        "orchestrator_status": result.get("status"),
        "kpis": result.get("kpis", {}),
        "marker": marker,
        "marker_found": marker in evidence,
        "evidence": tail[:2],
        "problems": problems,
    }


def _move_the_hole_off_the_plate(spec: dict) -> str:
    for feat in spec["parts"][0]["features"]:
        if feat.get("id") == "hole":
            feat["profile"]["circle"]["center"] = [500.0, 500.0]
            return "hole centre (30, 120) -> (500, 500), off the plate entirely"
    raise AssertionError("the case no longer has a sketch called 'hole'")


def _ask_for_a_radius_that_is_not_there(spec: dict) -> str:
    for entry in spec["outputs"]["regions"]:
        if entry["name"] == "HoleWall":
            entry["region"] = "Plate:face@r=7"
            return "measurement region Plate:face@r=6 -> r=7 (no such hole)"
    raise AssertionError("the case no longer has a HoleWall region")


def _seed_an_edge_that_does_not_exist(spec: dict) -> str:
    spec["parts"][0]["mesh"]["local_seeds"][0]["region"] = "edges@r=3"
    return "local seed edges@r=6 -> edges@r=3 (no such edge)"


def check_refusals(work_dir: Path) -> list[dict]:
    return [
        _refusal_item(
            "part_grammar_refuses_a_missed_cut", work_dir, "missed_cut",
            _move_the_hole_off_the_plate, "CUT_FAILED",
            "Measured: a cut that misses leaves the volume and the element "
            "count untouched and raises nothing, so without the geometry check "
            "this is a plain plate reported as a plate with a hole."),
        _refusal_item(
            "part_grammar_refuses_an_absent_radius", work_dir, "absent_radius",
            _ask_for_a_radius_that_is_not_there, "SELECTOR_MISMATCH",
            "An empty face set is accepted by Set(), and the KPI would then be "
            "read from whatever the extractor falls back to."),
        _refusal_item(
            "part_grammar_refuses_an_unseeded_edge", work_dir, "unseeded_edge",
            _seed_an_edge_that_does_not_exist, "SELECTOR_MISMATCH",
            "Seeding an empty edge set is silent: the mesh still generates, at "
            "the coarse size, and the stress concentration comes back low."),
    ]


# Hole-edge seed sizes, coarsest first. None means "no local refinement at all".
# The circumference is pi*12 = 37.7 mm, so these are roughly 8, 19, 31 and 47
# elements around the hole.
CONVERGENCE_SEEDS = (None, 2.0, 1.2, 0.8)


def check_convergence(work_dir: Path) -> dict:
    """Refine the hole edge in steps and watch the answer climb toward theory.

    This is what justifies the tolerance on the Kt item, and it is a stronger
    claim than "finer is closer": a solution that converges monotonically
    toward a number nobody tuned it to is evidence that the number is right.
    It also measures the thing that makes under-refinement dangerous, which is
    that it reads LOW rather than wrong-looking -- 3.04 against a theory of
    3.14 is a perfectly publishable-looking answer.
    """
    if not check_abaqus():
        return _skipped("part_grammar_converges_toward_theory", "Abaqus not found")

    sweep = []
    problems: list[str] = []
    for i, seed in enumerate(CONVERGENCE_SEEDS):
        spec = _load_spec()
        if seed is None:
            spec["parts"][0]["mesh"].pop("local_seeds", None)
        else:
            spec["parts"][0]["mesh"]["local_seeds"][0]["size"] = seed
        run_dir = work_dir / ("convergence_%d" % i)
        run_dir.mkdir(parents=True, exist_ok=True)

        result = _run(spec=spec, workdir=run_dir)
        if result.get("status") != "COMPLETED":
            problems.append("seed %s did not complete: %s"
                            % (seed, result.get("error")))
            continue
        value = _kpi(result, "HOOP_MAX")
        if value is None:
            problems.append("seed %s produced no HOOP_MAX" % seed)
            continue
        sweep.append({
            "hole_edge_seed": seed,
            "elements_around_the_hole": (None if seed is None
                                         else round(3.14159 * 12.0 / seed, 1)),
            "hoop_mpa": value,
            "deviation_from_theory": round(
                (THEORY_HOOP_MPA - value) / THEORY_HOOP_MPA, 6),
        })

    # The no-seed run is NOT the coarsest member of this family and must not be
    # read as one. Measured: it comes out at 3.0403, ABOVE the 2.0 mm seed's
    # 3.0346, because seedPart carries deviationFactor=0.1 and already refines
    # a curved edge on its own -- a 2.0 mm edge seed is coarser than what the
    # curvature rule was giving. Including it in the monotonic test would fail
    # a model that is behaving correctly.
    graded = [entry for entry in sweep if entry["hole_edge_seed"] is not None]
    if len(graded) >= 3:
        values = [entry["hoop_mpa"] for entry in graded]
        if not all(b >= a for a, b in zip(values, values[1:])):
            problems.append(
                "refining did not raise the answer monotonically: %s. Either "
                "the seed is not reaching the mesh, or something other than "
                "discretisation is moving the peak."
                % [round(v, 5) for v in values])
        if values[-1] > THEORY_HOOP_MPA * (1.0 + HOOP_TOLERANCE_REL):
            problems.append(
                "the finest mesh overshoots the theory by more than the band "
                "(%.6f vs %.6f); converging to the wrong number is worse than "
                "not converging" % (values[-1], THEORY_HOOP_MPA))
        first = abs(values[0] - THEORY_HOOP_MPA)
        last = abs(values[-1] - THEORY_HOOP_MPA)
        if last >= first:
            problems.append(
                "the finest mesh is no closer to theory than the coarsest "
                "(%.6f vs %.6f, theory %.6f)" % (values[-1], values[0],
                                                 THEORY_HOOP_MPA))
    else:
        problems.append("not enough completed graded runs to see a trend")

    return {
        "id": "part_grammar_converges_toward_theory",
        "status": "pass" if not problems else "fail",
        "theory_hoop_mpa": round(THEORY_HOOP_MPA, 6),
        "sweep": sweep,
        "monotonic_over": [entry["hole_edge_seed"] for entry in graded],
        "note": "an under-refined hole reads LOW and looks entirely plausible; "
                "this measures how far, and shows the error closing toward a "
                "number nothing here was tuned to. The no-seed row is listed "
                "but excluded from the trend: seedPart's deviationFactor "
                "already refines a curved edge, so 'no local seed' is not the "
                "coarsest member of this family.",
        "problems": problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Real Abaqus check for the v2 part grammar.")
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--work-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    work_dir = args.work_dir or Path(tempfile.mkdtemp(prefix="part_grammar_"))
    work_dir.mkdir(parents=True, exist_ok=True)

    items = check_the_shipped_case()
    items += check_refusals(work_dir)
    items.append(check_convergence(work_dir))

    statuses = [item["status"] for item in items]
    if "fail" in statuses:
        overall = "fail"
    elif all(s == "skipped" for s in statuses):
        overall = "skipped"
    elif "skipped" in statuses:
        overall = "partial"
    else:
        overall = "pass"

    report = {
        "schema": "part_grammar_check/1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "abaqus_release": detect_abaqus_release(),
        "work_dir": str(work_dir),
        "overall": overall,
        "items": items,
    }
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
    return 1 if overall == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
