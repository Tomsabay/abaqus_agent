#!/usr/bin/env python3
"""Real-solver check for the multi-part assembly dialect (spec v2).

This is the gate that lets `tie`, `contact` and `friction` be called supported
rather than written. pytest stays hermetic and never invokes a solver, so
nothing in tests/ can prove that a generated deck describes the model the spec
asked for — only that it contains the strings we expect it to contain. That is
a real gap: every failure this dialect can produce is silent.

  - `getByBoundingBox` returns an empty sequence for a mis-typed face, and
    `Set()` accepts an empty sequence, so a model can lose its load entirely
    and still solve.
  - A tie whose surfaces fall outside the position tolerance is left untied
    with a warning in the .dat, and the job completes.
  - A contact pair whose friction was dropped converges *better* than one that
    kept it.

None of those raise. All of them produce a full .odb and plausible numbers. So
the items here are chosen to be arithmetic identities that only hold if the
interface did its job:

  1. `assembly_tie_equals_solid` — two 5 mm plates tied face to face must bend
     as the single 10 mm section they now are: I = 10*10^3/12 = 833.33 mm^4, so
     the tip deflects -0.0714 mm. A tie that failed to bind gives 4x that.
  2. `assembly_contact_equals_two_layers` — the same geometry with frictionless
     contact instead. The layers slide freely, so I = 2*10*5^3/12 = 208.33 mm^4
     and the deflection is exactly 4x the tied case. This is the item that
     proves the interface is doing something: the two specs differ in one word.
  3. `assembly_interface_ratio` — contact / tie = 4.00 from beam theory, from
     the two measurements above. Meshes and elements cancel in the ratio, so
     this is the sharpest of the three.
  4. `assembly_friction_is_coulomb` — a block pressed with a known normal force
     and pushed sideways past the stick limit must react with exactly mu*N.
     1.0 MPa over 20x20 is N = 400 N; mu = 0.3 gives F = 120 N. A dropped
     coefficient reads ~0; a misread mu reads 60 or 240. Nothing else in that
     model can produce 120.
  5. `assembly_refuses_a_selector_that_misses` — the honesty item. A selector
     edited to name a face that does not exist must abort the build inside the
     Abaqus kernel, not produce a model with an empty set.

Items 1-4 accept a cached run: the cache key is a hash of the spec, and a
cached result is the frozen evidence from the run that produced it. Whether
each number came from a fresh solve is recorded per item.

Nothing is written inside the repository except each case's own runs/ cache,
which is where the orchestrator writes anyway.

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

# Beam theory for the two-plate cantilever: 100 mm long, 10 mm wide, built as
# two 5 mm plates, under a uniform 0.1 MPa on the top face (q = 1.0 N/mm).
#   delta = q L^4 / (8 E I),  E = 210000 MPa
# Tied: one 10 mm section, I = 10 * 10^3 / 12 = 833.33 mm^4
# Free: two 5 mm layers,   I = 2 * 10 * 5^3 / 12 = 208.33 mm^4
THEORY_TIED_MM = -0.0714285714
THEORY_FREE_MM = -0.2857142857
THEORY_RATIO = 4.0

# Measured on Abaqus 2021, this machine. The tolerance below is against
# THEORY, not against these; they are recorded so a drift is visible even when
# it stays inside the theory band.
MEASURED_TIE_MM = -0.07150482386350632          # C3D20R
MEASURED_CONTACT_MM = -0.28309428691864014      # C3D8I, frictionless
MEASURED_FRICTION_N = 119.9996030330658
MEASURED_NORMAL_N = 399.9999970346689

# Discretisation error, not solver error: 1-2 % is what a 5 mm seed gives on
# this section. The failure this gate exists to catch is a factor of four.
DEFLECTION_TOLERANCE_REL = 0.05
# The ratio is the sharp one — element and mesh error largely cancel.
RATIO_TOLERANCE_REL = 0.03
# Coulomb's law is exact once the interface is fully sliding.
FRICTION_TOLERANCE_REL = 0.01

CASE_TIE = "two_plate_tie"
CASE_CONTACT = "two_plate_contact"
CASE_FRICTION = "block_friction_slide"


def _skipped(item_id: str, reason: str, **extra: object) -> dict:
    out = {"id": item_id, "status": "skipped", "reason": reason}
    out.update(extra)
    return out


def _case_dir(case: str) -> Path:
    return ROOT / "cases" / case


def _load_spec(case: str) -> dict:
    return yaml.safe_load((_case_dir(case) / "spec.yaml").read_text(encoding="utf-8"))


def _run_case(case: str, spec: dict | None = None, workdir: Path | None = None) -> dict:
    """Drive a case through the Abaqus orchestrator exactly as the CLI does."""
    from agent.orchestrator import build_orchestrator

    case_dir = _case_dir(case)
    expected = case_dir / "expected.json"
    runner_cfg_path = case_dir / "runner.json"
    runner_cfg = None
    if runner_cfg_path.exists():
        runner_cfg = json.loads(runner_cfg_path.read_text(encoding="utf-8"))

    orch = build_orchestrator(
        spec_dict=copy.deepcopy(spec if spec is not None else _load_spec(case)),
        workdir=workdir,
        expected_path=expected if expected.exists() and spec is None else None,
        runner_cfg=runner_cfg,
    )
    return orch.run()


def _was_cached(result: dict) -> bool:
    # The orchestrator stringifies every value on its way into result["stages"],
    # so the flag arrives as "True"/"False" and bool() on it is always True.
    raw = result.get("stages", {}).get("build_model", {}).get("cached")
    return str(raw).lower() == "true"


def _kpi(result: dict, name: str):
    value = result.get("kpis", {}).get(name)
    if isinstance(value, dict):
        return value.get("value")
    return value


def _deviation(measured: float | None, reference: float) -> float | None:
    if measured is None:
        return None
    return abs(measured - reference) / abs(reference)


def _run_problems(result: dict, case: str) -> list[str]:
    if result.get("status") == "COMPLETED":
        return []
    return ["%s: orchestrator status %s (expected COMPLETED): %s"
            % (case, result.get("status"), result.get("error"))]


def check_interfaces() -> list[dict]:
    """Items 1-3. Run both plate cases, then compare them to each other."""
    if not check_abaqus():
        reason = ("Abaqus not found (set ABAQUS_AGENT_ABAQUS_CMD or put "
                  "abaqus.bat on PATH)")
        return [_skipped("assembly_tie_equals_solid", reason),
                _skipped("assembly_contact_equals_two_layers", reason),
                _skipped("assembly_interface_ratio", reason)]

    started = time.time()
    tie_result = _run_case(CASE_TIE)
    tie_elapsed = time.time() - started

    started = time.time()
    contact_result = _run_case(CASE_CONTACT)
    contact_elapsed = time.time() - started

    tie_u = _kpi(tie_result, "U_TIP")
    contact_u = _kpi(contact_result, "U_TIP")

    tie_problems = _run_problems(tie_result, CASE_TIE)
    tie_dev = _deviation(tie_u, THEORY_TIED_MM)
    if tie_u is None:
        tie_problems.append("U_TIP missing from KPIs")
    elif tie_dev >= DEFLECTION_TOLERANCE_REL:
        tie_problems.append(
            "tied deflection %.8f mm is %.2f%% from the solid-section theory "
            "%.8f mm; a factor near 4 means the tie did not bind"
            % (tie_u, tie_dev * 100, THEORY_TIED_MM))

    contact_problems = _run_problems(contact_result, CASE_CONTACT)
    contact_dev = _deviation(contact_u, THEORY_FREE_MM)
    if contact_u is None:
        contact_problems.append("U_TIP missing from KPIs")
    elif contact_dev >= DEFLECTION_TOLERANCE_REL:
        contact_problems.append(
            "contact deflection %.8f mm is %.2f%% from the two-free-layers "
            "theory %.8f mm" % (contact_u, contact_dev * 100, THEORY_FREE_MM))

    ratio = None
    ratio_dev = None
    ratio_problems: list[str] = []
    if tie_u and contact_u:
        ratio = contact_u / tie_u
        ratio_dev = abs(ratio - THEORY_RATIO) / THEORY_RATIO
        if ratio_dev >= RATIO_TOLERANCE_REL:
            ratio_problems.append(
                "contact/tie = %.4f, theory 4.00 (%.2f%% off). A ratio near 1 "
                "means the two specs produced the same model, i.e. the "
                "interface type was ignored." % (ratio, ratio_dev * 100))
    else:
        ratio_problems.append("cannot form the ratio: one of the runs has no U_TIP")

    return [
        {
            "id": "assembly_tie_equals_solid",
            "status": "pass" if not tie_problems else "fail",
            "spec": "cases/%s/spec.yaml" % CASE_TIE,
            "identity": "two tied 5 mm plates == one 10 mm section",
            "element": "C3D20R",
            "measured_u_tip_mm": tie_u,
            "theory_u_tip_mm": THEORY_TIED_MM,
            "previously_measured_mm": MEASURED_TIE_MM,
            "relative_deviation": None if tie_dev is None else round(tie_dev, 8),
            "tolerance_relative": DEFLECTION_TOLERANCE_REL,
            "cached": _was_cached(tie_result),
            "elapsed_s": round(tie_elapsed, 2),
            "problems": tie_problems,
        },
        {
            "id": "assembly_contact_equals_two_layers",
            "status": "pass" if not contact_problems else "fail",
            "spec": "cases/%s/spec.yaml" % CASE_CONTACT,
            "identity": "frictionless contact == two independent 5 mm layers",
            "element": "C3D8I",
            "note": "C3D20R is unusable here: quadratic faces put unequal "
                    "consistent nodal forces on the contact surface and the "
                    "step fails to converge. C3D8I is linear with incompatible "
                    "modes, which is what makes it accurate in bending.",
            "measured_u_tip_mm": contact_u,
            "theory_u_tip_mm": THEORY_FREE_MM,
            "previously_measured_mm": MEASURED_CONTACT_MM,
            "relative_deviation": None if contact_dev is None else round(contact_dev, 8),
            "tolerance_relative": DEFLECTION_TOLERANCE_REL,
            "cached": _was_cached(contact_result),
            "elapsed_s": round(contact_elapsed, 2),
            "problems": contact_problems,
        },
        {
            "id": "assembly_interface_ratio",
            "status": "pass" if not ratio_problems else "fail",
            "identity": "contact / tie == I_solid / I_two_layers == 4.00",
            "note": "the sharpest item: mesh and element error largely cancel "
                    "in the ratio, and one word of spec separates the two runs",
            "measured_ratio": None if ratio is None else round(ratio, 6),
            "theory_ratio": THEORY_RATIO,
            "relative_deviation": None if ratio_dev is None else round(ratio_dev, 8),
            "tolerance_relative": RATIO_TOLERANCE_REL,
            "problems": ratio_problems,
        },
    ]


def check_friction() -> dict:
    if not check_abaqus():
        return _skipped("assembly_friction_is_coulomb", "Abaqus not found")

    started = time.time()
    result = _run_case(CASE_FRICTION)
    elapsed = time.time() - started

    friction = _kpi(result, "FRICTION_FORCE")
    normal = _kpi(result, "NORMAL_FORCE")

    problems = _run_problems(result, CASE_FRICTION)
    normal_dev = _deviation(normal, 400.0)
    if normal is None:
        problems.append("NORMAL_FORCE missing from KPIs")
    elif normal_dev >= FRICTION_TOLERANCE_REL:
        problems.append(
            "normal reaction %.6f N is not the applied 400 N (1.0 MPa over "
            "20x20); the friction number below is meaningless without it"
            % normal)

    expected_friction = None
    friction_dev = None
    if normal is not None:
        expected_friction = 0.3 * abs(normal)
    if friction is None:
        problems.append("FRICTION_FORCE missing from KPIs")
    elif expected_friction:
        friction_dev = abs(abs(friction) - expected_friction) / expected_friction
        if friction_dev >= FRICTION_TOLERANCE_REL:
            problems.append(
                "sliding reaction %.6f N vs Coulomb mu*N = %.6f N (%.2f%% off). "
                "Near zero means the coefficient never reached the deck."
                % (friction, expected_friction, friction_dev * 100))

    return {
        "id": "assembly_friction_is_coulomb",
        "status": "pass" if not problems else "fail",
        "spec": "cases/%s/spec.yaml" % CASE_FRICTION,
        "identity": "F = mu * N, mu = 0.3, N = 1.0 MPa * 20 * 20 = 400 N",
        "measured_normal_n": normal,
        "measured_friction_n": friction,
        "expected_friction_n": expected_friction,
        "previously_measured_friction_n": MEASURED_FRICTION_N,
        "previously_measured_normal_n": MEASURED_NORMAL_N,
        "relative_deviation": None if friction_dev is None else round(friction_dev, 8),
        "tolerance_relative": FRICTION_TOLERANCE_REL,
        "cached": _was_cached(result),
        "elapsed_s": round(elapsed, 2),
        "problems": problems,
    }


def check_selector_refusal(work_dir: Path) -> dict:
    """The honesty item: a selector that matches nothing must abort the build.

    This cannot be tested hermetically. Whether `getByBoundingBox` finds a face
    is decided inside the Abaqus kernel, and its answer for a face that is not
    there is an empty sequence, which `Set()` accepts without complaint. The
    only way to know the count assertion fires is to make it fire.
    """
    if not check_abaqus():
        return _skipped("assembly_refuses_a_selector_that_misses", "Abaqus not found")

    spec = _load_spec(CASE_TIE)
    # y=max is the top of the upper plate. y=7.5 is inside the material, where
    # no face exists — the selector is well-formed and simply matches nothing.
    original = spec["steps"][0]["loads"][0]["region"]
    spec["steps"][0]["loads"][0]["region"] = original.rsplit(":", 1)[0] + ":face@y=7.5"

    run_dir = work_dir / "selector_refusal"
    run_dir.mkdir(parents=True, exist_ok=True)
    result = _run_case(CASE_TIE, spec=spec, workdir=run_dir)

    problems: list[str] = []
    if result.get("status") == "COMPLETED":
        problems.append(
            "a spec whose pressure load lands on no face ran to completion. "
            "The load is silently gone and the deflection is whatever the "
            "model does with no load at all.")
    if result.get("kpis"):
        problems.append("a failed build must produce no KPIs, got %s"
                        % list(result["kpis"]))

    # The kernel's stderr is where the assertion surfaces; print() from
    # `abaqus cae noGUI` goes to abaqus.rpy, not to the launcher's stdout.
    evidence = ""
    log = run_dir / "build_model_script.log"
    if log.exists():
        evidence = log.read_text(encoding="utf-8", errors="replace")
    haystack = evidence + json.dumps(result.get("error", {}), ensure_ascii=False)
    if "SELECTOR_MISMATCH" not in haystack:
        problems.append(
            "the build failed without naming the selector; the message a user "
            "sees has to say which selector missed and by how much")

    return {
        "id": "assembly_refuses_a_selector_that_misses",
        "status": "pass" if not problems else "fail",
        "spec_change": "%s -> face@y=7.5 (inside the material, matches nothing)"
                       % original,
        "orchestrator_status": result.get("status"),
        "kpis": result.get("kpis", {}),
        "selector_mismatch_reported": "SELECTOR_MISMATCH" in haystack,
        "evidence_tail": evidence.strip().splitlines()[-6:] if evidence else [],
        "problems": problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Real Abaqus assembly-dialect check.")
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--skip-refusal", action="store_true",
                        help="skip the selector item (it needs a fresh solve)")
    args = parser.parse_args(argv)

    work_dir = args.work_dir or Path(tempfile.mkdtemp(prefix="assembly_check_"))
    work_dir.mkdir(parents=True, exist_ok=True)

    items = check_interfaces()
    items.append(check_friction())
    if not args.skip_refusal:
        items.append(check_selector_refusal(work_dir))

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
        "schema": "assembly_check/1",
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
