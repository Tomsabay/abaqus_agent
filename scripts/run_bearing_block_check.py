#!/usr/bin/env python3
"""Real-solver check for the bearing_block case, and for the failure it hides.

`bearing_block` is the case where every layer of the v2 dialect is present at
once: named part shorthand and dispatched sketch entities, faces picked by
radius, a surface tie, a planar friction contact, two materials, dispatched
steps and conditions. Complexity on its own proves nothing, so the case carries
three arithmetic identities that only hold if the model is the one the spec
described, and each is broken by a different mistake:

  1. `WEIGHT_TOTAL` — the summed vertical reaction under gravity is the sum of
     the three weights, Sum(rho_i * V_i) * g. The volumes are measured by
     Abaqus through `expect:` and the densities come from the materials, so
     this is the item that checks the DENSITY DIMENSION. 7850 kg/m^3 written
     into a mm-MPa-t spec is off by 1e12 and no contour plot shows it.
  2. `CLAMP_REACTION` — step 2 adds 0.05 MPa over the cap's 80 x 60 top face,
     so the same sum becomes weight + 240 N. Equilibrium is an identity and
     holds whatever the mesh is; what it catches is a pressure that landed on
     the wrong face or pointed the wrong way.
  3. `FRICTION_FORCE` — step 3 pushes the cap 0.4 mm, far past the elastic
     slip, so the horizontal reaction is exactly mu*N = 0.25 * 243.6964.

### And the reason this script exists at all

Those three identities are BLIND to the failure this case was built around.
Measured here, on one coarse model in which 85 constraint findings were raised
and eleven blocks of secondary nodes were left untied: every identity still
lands inside its own tolerance, to five or six digits. Equilibrium does not
care WHICH nodes carry the load, so a tie that dropped its secondary nodes
reads exactly like one that did not. The only thing that sees it is the .dat,
which is why `runner/dat_warnings.py` exists and why `dat_integrity` is a
pipeline stage.

### What actually keeps the tie bound — measured, and not what the spec says

The spec's own comment credits the local seeds on `edges@r=12`: the two tied
faces are discretisations of the same r=12 cylinder, the facet chord height is
h^2/(8r), and at the part seeds that is 0.51 mm against a 0.1 mm tolerance.
Correct in outline, wrong on which knob is doing the work. All four
combinations, measured on Abaqus 2021 through the datacheck alone:

    local seeds   position_tolerance   `WILL NOT BE TIED` blocks
    1.5 mm        0.05                 0
    1.5 mm        0.10                 0
    (none)        0.05                 11
    (none)        0.10                 0

So the seeds fix it at EITHER tolerance -- that part of the comment holds. But
the shipped spec also raised the tolerance from 0.05 to 0.1, and that change
alone silences the warning on a mesh that has not been improved by one element.
Two fixes were applied where one was needed, and the redundant one is the
anti-fix the design doc warns about: widening a tolerance until the warning
goes away does not make the model right, it stops the check from being one.
The items below pin the tolerance at 0.05 wherever the mesh is the variable,
because 0.1 masks the very thing being measured.

### The two directions a tie check stops being a check

  * TOO TIGHT for the mesh -- nodes drop, the identities do not notice, and
    `dat_integrity` must be the thing that reports it.
  * TOO LOOSE for the geometry -- a real misalignment binds quietly. Push the
    bushing 0.5 mm out of its bore: at the shipped 0.1 mm the datacheck must
    notice, and `--tie-tolerance 1.0` is the mutation that makes it stop
    noticing, at which point this script must report FAIL.

### Cost

The shipped model is ~92k deck lines of C3D10 and takes about 23 minutes to
solve, which is what items 1-4 cost; there is no way around it, because the
identities need real KPIs out of a real .odb. Everything after that is either
a 100-second coarse solve or a datacheck, because `WILL NOT BE TIED` appears
in `<job>_syntaxcheck.dat` exactly as it does in the analysis .dat -- measured,
eleven blocks in both -- so the tie questions buy nothing from a full solve.

Nothing is written inside the repository: every run here goes to a temporary
directory, so the case's own frozen runs/ cache is left alone.

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

CASE = "bearing_block"

# The three identities, restated here so this script does not depend on the
# case's own expected.json being right -- that file is the thing under test as
# much as the code is. Derivations are in cases/bearing_block/expected.json.
#
#   Housing  80*40*60 - pi*12^2*60 = 164856.64 mm^3 steel  @ 7.85e-9 t/mm^3
#   Bushing  pi*(12^2-8^2)*60      =  15079.64 mm^3 bronze @ 8.80e-9
#   Cap      80*10*60              =  48000.00 mm^3 steel
THEORY_WEIGHT_N = 17.6936
THEORY_CLAMP_N = 257.6936          # + 0.05 MPa * 80 * 60
THEORY_FRICTION_N = 60.9241        # 0.25 * (3.6964 + 240)

# Against theory, not against a frozen run. The bore is curved and a tet mesh
# facets it, so the meshed housing carries slightly more material than the CAD
# solid: measured 0.006% at seed 7. What these have to catch misses by factors.
WEIGHT_TOLERANCE_REL = 0.005
CLAMP_TOLERANCE_REL = 0.01
FRICTION_TOLERANCE_REL = 0.05

SHIPPED_TIE_TOL = 0.1
# The tolerance the case shipped with until 2026-08, and the only one at which
# the mesh is the variable: at 0.1 the coarse mesh ties cleanly and a
# mesh-versus-mesh comparison measures nothing.
SHARP_TIE_TOL = 0.05

# The misalignment for the too-loose item: a real error, an eighth of the 4 mm
# wall it sits in, and five times the shipped tolerance. A tie that cannot see
# this one is not checking position at all.
MISALIGN_MM = 0.5


def _skipped(item_id: str, reason: str, **extra: object) -> dict:
    out = {"id": item_id, "status": "skipped", "reason": reason}
    out.update(extra)
    return out


def _case_dir() -> Path:
    return ROOT / "cases" / CASE


def _load_spec() -> dict:
    return yaml.safe_load((_case_dir() / "spec.yaml").read_text(encoding="utf-8"))


def _runner_cfg() -> dict | None:
    path = _case_dir() / "runner.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Spec mutations
# ---------------------------------------------------------------------------

def _strip_local_seeds(spec: dict) -> dict:
    """Same geometry, no seed control on the bore: part seeds 7.0 and 3.5."""
    out = copy.deepcopy(spec)
    for part in out.get("parts", []):
        (part.get("mesh") or {}).pop("local_seeds", None)
    return out


def _set_tie_tolerance(spec: dict, tol: float) -> dict:
    out = copy.deepcopy(spec)
    for interaction in out.get("interactions", []):
        if interaction.get("type") == "tie":
            interaction["position_tolerance"] = float(tol)
    return out


def _misalign_bushing(spec: dict, by: float) -> dict:
    """Push the bushing out of its bore by a real, wrong amount."""
    out = copy.deepcopy(spec)
    for inst in out["assembly"]["instances"]:
        if inst.get("part") == "Bushing":
            translate = list(inst.get("translate") or [0.0, 0.0, 0.0])
            translate[0] += float(by)
            inst["translate"] = translate
    return out


# ---------------------------------------------------------------------------
# Running: the whole pipeline, or just as far as the datacheck
# ---------------------------------------------------------------------------

def _run(spec: dict, workdir: Path) -> dict:
    """Drive one spec through the orchestrator, into a scratch directory.

    `workdir` is always given. Without it the orchestrator writes under the
    case's own runs/, and a mutated spec hashes to a new run_id, so the
    mutations here would litter the directory that holds this case's frozen
    evidence.
    """
    from agent.orchestrator import build_orchestrator

    workdir.mkdir(parents=True, exist_ok=True)
    orch = build_orchestrator(
        spec_dict=copy.deepcopy(spec),
        workdir=workdir,
        expected_path=None,
        runner_cfg=_runner_cfg(),
    )
    return orch.run()


def _datacheck(spec: dict, workdir: Path) -> dict:
    """Build the deck and run Abaqus's datacheck. No solve.

    Every constraint question this script asks is answered here: measured on
    the misaligned model, `<job>_syntaxcheck.dat` carries the same eleven
    `WILL NOT BE TIED` blocks the analysis .dat does. A tie is resolved when
    the model is assembled, not when it converges.
    """
    from runner.build_model import build_model
    from runner.dat_warnings import parse_dat_warnings
    from runner.syntaxcheck import syntaxcheck_inp

    workdir.mkdir(parents=True, exist_ok=True)
    spec_path = workdir / "spec.yaml"
    spec_path.write_text(
        yaml.dump(copy.deepcopy(spec), allow_unicode=True,
                  default_flow_style=False),
        encoding="utf-8")
    built = build_model(spec_path, workdir)
    check = syntaxcheck_inp(built["inp_path"], built["workdir"])
    dat = Path(built["workdir"]) / (
        Path(built["inp_path"]).stem + "_syntaxcheck.dat")
    text = dat.read_text(encoding="utf-8", errors="replace") if dat.exists() else ""
    report = parse_dat_warnings(dat)
    return {
        "ok": bool(check.get("ok")),
        "read": report["read"],
        "untied_blocks": text.count("WILL NOT BE TIED"),
        "integrity_count": report["integrity_count"],
        "ids": sorted({f.get("id") for f in report["findings"] if f.get("id")}),
        "deck_lines": sum(1 for _ in Path(built["inp_path"]).open(
            encoding="utf-8", errors="replace")),
    }


def _kpi(result: dict, name: str):
    value = result.get("kpis", {}).get(name)
    if isinstance(value, dict):
        return value.get("value")
    return value


def _deviation(measured, reference: float):
    if measured is None:
        return None
    return abs(measured - reference) / abs(reference)


def _integrity(result: dict) -> dict:
    """What the .dat said about whether this is the spec's model."""
    stage = (result.get("stages") or {}).get("dat_integrity") or {}
    return {
        "read": bool(stage.get("read")),
        "count": int(stage.get("integrity_count") or 0),
        "ids": sorted({f.get("id") for f in (stage.get("findings") or [])
                       if f.get("id")}),
    }


def _completed(result: dict, label: str) -> list[str]:
    if result.get("status") == "COMPLETED":
        return []
    return ["%s: orchestrator status %s (expected COMPLETED): %s"
            % (label, result.get("status"), result.get("error"))]


def _graded(result: dict):
    """Each identity against its OWN band, the one its item uses."""
    return [
        ("WEIGHT_TOTAL", _deviation(_kpi(result, "WEIGHT_TOTAL"),
                                    THEORY_WEIGHT_N), WEIGHT_TOLERANCE_REL),
        ("CLAMP_REACTION", _deviation(_kpi(result, "CLAMP_REACTION"),
                                      THEORY_CLAMP_N), CLAMP_TOLERANCE_REL),
        ("FRICTION_FORCE", _deviation(_kpi(result, "FRICTION_FORCE"),
                                      THEORY_FRICTION_N),
         FRICTION_TOLERANCE_REL),
    ]


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

def check_identities(work: Path, tie_tol: float) -> list[dict]:
    """Items 1-4: the three identities and the tie's own integrity."""
    spec = _load_spec()
    if tie_tol != SHIPPED_TIE_TOL:
        spec = _set_tie_tolerance(spec, tie_tol)
    started = time.time()
    result = _run(spec, work / "shipped")
    elapsed = round(time.time() - started, 1)

    base = _completed(result, "shipped spec")
    integrity = _integrity(result)

    items = []
    catches = {
        "WEIGHT_TOTAL": "A density in the wrong unit misses by orders of "
                        "magnitude.",
        "CLAMP_REACTION": "A pressure on the wrong face reads 40 N low.",
        "FRICTION_FORCE": "A dropped coefficient reads about 0.",
    }
    theories = {"WEIGHT_TOTAL": THEORY_WEIGHT_N,
                "CLAMP_REACTION": THEORY_CLAMP_N,
                "FRICTION_FORCE": THEORY_FRICTION_N}
    ids = {"WEIGHT_TOTAL": "bearing_weight_is_the_sum_of_three_densities",
           "CLAMP_REACTION": "bearing_clamp_reaction_is_weight_plus_pressure",
           "FRICTION_FORCE": "bearing_friction_is_coulomb"}
    for name, deviation, band in _graded(result):
        problems = list(base)
        measured = _kpi(result, name)
        if measured is None:
            problems.append("%s missing from the KPIs" % name)
        elif deviation >= band:
            problems.append(
                "%s = %.6f N is %.3f%% from the identity %.6f N. %s"
                % (name, measured, deviation * 100, theories[name],
                   catches[name]))
        items.append({
            "id": ids[name],
            "status": "pass" if not problems else "fail",
            "predicted": theories[name],
            "measured": measured,
            "relative_deviation": deviation,
            "tolerance_relative": band,
            "seconds": elapsed,
            "problems": problems,
        })

    problems = list(base)
    if not integrity["read"]:
        problems.append(
            "no .dat was read, so nothing checked whether the tie bound. This "
            "case's whole point is that the identities above cannot see that.")
    elif integrity["count"]:
        problems.append(
            "the shipped spec reports %d integrity finding(s) %s. The local "
            "seeds on `edges@r=12` exist to keep the facet chord height under "
            "the tie tolerance; if they no longer do, the shipped case is "
            "quietly running a partly untied model."
            % (integrity["count"], integrity["ids"]))
    items.append({
        "id": "bearing_tie_binds_at_the_shipped_seeds",
        "status": "pass" if not problems else "fail",
        "identity": "chord height h^2/(8r) = 0.023 mm at the 1.5 mm local "
                    "seed, inside a 0.1 mm position tolerance",
        "tie_tolerance": tie_tol,
        "integrity_count": integrity["count"],
        "integrity_ids": integrity["ids"],
        "seconds": elapsed,
        "problems": problems,
    })
    return items


def check_coarse_mesh_drops_the_tie(work: Path, tie_tol: float) -> dict:
    """Item 5: the tie fails silently, and only the .dat says so.

    At the SHARP tolerance, because that is the only one where the mesh is the
    variable -- see the table in this module's docstring. This item passes when
    the failure happens AND the identities do not notice; a run in which they
    also broke would be a louder failure and would say nothing about whether
    anything is watching.
    """
    # The default run uses the sharp tolerance regardless of what the case
    # ships, because at 0.1 the coarse mesh ties cleanly and this comparison
    # would measure nothing. An explicit --tie-tolerance still wins: that is
    # the mutation, and at 1.0 this item is supposed to fail.
    tol = SHARP_TIE_TOL if tie_tol == SHIPPED_TIE_TOL else tie_tol
    spec = _set_tie_tolerance(_strip_local_seeds(_load_spec()), tol)
    started = time.time()
    result = _run(spec, work / "coarse")
    elapsed = round(time.time() - started, 1)

    integrity = _integrity(result)
    graded = _graded(result)
    problems = _completed(result, "coarse spec")
    if integrity["count"] == 0:
        problems.append(
            "taking the local seeds off did not drop a single tie node at a "
            "%s mm tolerance. Either this release ties differently than "
            "measured, or the seeds were never what kept the chord height "
            "down -- either way the reasoning written on the shipped case is "
            "wrong and needs remeasuring." % tol)
    elif "tie_node_outside_tolerance" not in integrity["ids"]:
        problems.append(
            "integrity findings were reported (%s) but not the tie one, so "
            "this item is measuring some other failure" % integrity["ids"])
    if any(d is None for _, d, _ in graded):
        problems.append("a KPI went missing, so this item cannot show that the "
                        "identities are blind to a dropped tie")
    else:
        moved = ["%s off by %.4f%% against its %.2f%% band"
                 % (name, d * 100, band * 100)
                 for name, d, band in graded if d >= band]
        if moved:
            problems.append(
                "the identities moved when the tie dropped (%s). That is a "
                "louder failure than the one this item is about, and the claim "
                "that equilibrium cannot see a dropped tie needs remeasuring."
                % "; ".join(moved))

    return {
        "id": "bearing_coarse_mesh_drops_the_tie_silently",
        "status": "pass" if not problems else "fail",
        "mutation": "mesh.local_seeds removed from Housing and Bushing, "
                    "position_tolerance %s" % SHARP_TIE_TOL,
        "identity": "chord height h^2/(8r) = 0.51 mm at seed 7, ten times the "
                    "0.05 mm tolerance the case shipped with until 2026-08",
        "integrity_count": integrity["count"],
        "integrity_ids": integrity["ids"],
        "measured": dict((name, _kpi(result, name))
                         for name, _, _ in graded),
        "identity_deviations": [None if d is None else round(d, 8)
                                for _, d, _ in graded],
        "note": "the identities are expected to pass here. That is the finding, "
                "not a pass: equilibrium does not care which nodes carry the "
                "load, so only the .dat can tell these two models apart.",
        "seconds": elapsed,
        "problems": problems,
    }


def check_the_seeds_are_the_fix(work: Path) -> dict:
    """Item 6: which knob binds the tie -- the seeds, or the tolerance?

    The 2x2, through the datacheck alone. This item fixes its own tolerances
    by construction, so `--tie-tolerance` deliberately does not reach it.

    The expected shape is the measured one: the seeds bind it at either
    tolerance, and widening the tolerance silences the warning on a mesh that
    was never improved. If a future release moves any cell, the reasoning
    written on the shipped case and in docs/ASSEMBLY_MODELING.md is out of date
    and this says so rather than passing quietly.
    """
    started = time.time()
    base = _load_spec()
    grid = {}
    for seeds in (True, False):
        for tol in (SHARP_TIE_TOL, SHIPPED_TIE_TOL):
            label = "%s@%s" % ("fine" if seeds else "coarse", tol)
            spec = base if seeds else _strip_local_seeds(base)
            grid[label] = _datacheck(
                _set_tie_tolerance(spec, tol),
                work / ("grid_" + label.replace("@", "_").replace(".", "p")))
    elapsed = round(time.time() - started, 1)

    untied = dict((k, v["untied_blocks"]) for k, v in grid.items())
    problems = []
    unread = sorted(k for k, v in grid.items() if not v["read"])
    if unread:
        # Every cell below reads zero when no .dat exists, and a grid of zeros
        # is indistinguishable from "the tie bound everywhere".
        problems.append(
            "no datacheck .dat for %s, so those cells measured nothing and the "
            "zeros in them mean nothing" % ", ".join(unread))
    fine_sharp = "fine@%s" % SHARP_TIE_TOL
    coarse_sharp = "coarse@%s" % SHARP_TIE_TOL
    coarse_loose = "coarse@%s" % SHIPPED_TIE_TOL
    if untied[fine_sharp] != 0:
        problems.append(
            "the local seeds did NOT bind the tie at the sharp tolerance "
            "(%d blocks untied). The spec credits them with exactly that, so "
            "either they stopped working or the credit was misplaced."
            % untied[fine_sharp])
    if untied[coarse_sharp] == 0:
        problems.append(
            "the coarse mesh bound cleanly at the sharp tolerance, so nothing "
            "in this repository currently demonstrates a dropped tie and the "
            "counterexample above has no geometry behind it")
    if untied[coarse_loose] != 0:
        problems.append(
            "widening the tolerance to %s no longer silences the coarse mesh "
            "(%d blocks untied). That is a better world than the measured one, "
            "but the note in docs/ASSEMBLY_MODELING.md now describes something "
            "that does not happen." % (SHIPPED_TIE_TOL, untied[coarse_loose]))

    return {
        "id": "bearing_the_seeds_bind_it_not_the_tolerance",
        "status": "pass" if not problems else "fail",
        "identity": "2x2 over {local seeds, none} x {%s, %s} mm, datacheck "
                    "only" % (SHARP_TIE_TOL, SHIPPED_TIE_TOL),
        "untied_blocks": untied,
        "integrity_counts": dict((k, v["integrity_count"])
                                 for k, v in grid.items()),
        "deck_lines": dict((k, v["deck_lines"]) for k, v in grid.items()),
        "note": "the seeds bind it at either tolerance; raising the tolerance "
                "silences the warning without adding one element. The shipped "
                "spec did both, and only the first was needed.",
        "seconds": elapsed,
        "problems": problems,
    }


def check_tolerance_still_sees_a_misalignment(work: Path, tie_tol: float) -> dict:
    """Item 7: is the tie tolerance still small enough to be a check?

    A tie whose position tolerance exceeds the misalignment it is supposed to
    catch binds a wrong model quietly and reports nothing. Datacheck only: a
    tie is resolved when the model is assembled, and the 23 minutes a solve
    costs would not add a fact.
    """
    spec = _misalign_bushing(_load_spec(), MISALIGN_MM)
    if tie_tol != SHIPPED_TIE_TOL:
        spec = _set_tie_tolerance(spec, tie_tol)
    started = time.time()
    out = _datacheck(spec, work / "misaligned")
    elapsed = round(time.time() - started, 1)

    problems = []
    # No .dat is not "clean", it is "we did not look". Without this the item
    # would report a silent pass for a datacheck that never produced a file.
    if not out["read"]:
        problems.append(
            "no datacheck .dat was produced, so nothing here measured whether "
            "the tie noticed the misalignment")
    # A misaligned model is allowed to fail loudly -- that is a caught error.
    # What must not happen is a clean datacheck with nothing said.
    elif out["ok"] and out["integrity_count"] == 0:
        problems.append(
            "the bushing was %s mm out of its bore and the datacheck came back "
            "clean: no integrity finding. The tie tolerance (%s mm) is %s times "
            "the misalignment, so it cannot tell a seated bushing from a "
            "displaced one. Widening a tolerance until the warning goes away "
            "does not fix the model, it stops the check from being one."
            % (MISALIGN_MM, tie_tol, round(tie_tol / MISALIGN_MM, 2)))

    return {
        "id": "bearing_tie_tolerance_still_catches_a_misalignment",
        "status": "pass" if not problems else "fail",
        "mutation": "Bushing translated +%s mm in x" % MISALIGN_MM,
        "tie_tolerance": tie_tol,
        "misalignment_mm": MISALIGN_MM,
        "datacheck_ok": out["ok"],
        "untied_blocks": out["untied_blocks"],
        "integrity_count": out["integrity_count"],
        "integrity_ids": out["ids"],
        "caught_by": ("dat_integrity" if out["integrity_count"]
                      else ("datacheck_error" if not out["ok"] else "nothing")),
        "note": "run this with --tie-tolerance 1.0 to see the item fail: that "
                "is the loosened tolerance the design doc warns against, "
                "measured rather than argued.",
        "seconds": elapsed,
        "problems": problems,
    }


ITEM_IDS = [
    "bearing_weight_is_the_sum_of_three_densities",
    "bearing_clamp_reaction_is_weight_plus_pressure",
    "bearing_friction_is_coulomb",
    "bearing_tie_binds_at_the_shipped_seeds",
    "bearing_coarse_mesh_drops_the_tie_silently",
    "bearing_the_seeds_bind_it_not_the_tolerance",
    "bearing_tie_tolerance_still_catches_a_misalignment",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Real Abaqus check for the bearing_block case.")
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--tie-tolerance", type=float, default=SHIPPED_TIE_TOL,
                        help="override every tie's position_tolerance. The "
                             "acceptance mutation: 1.0 must make this script "
                             "fail. The 2x2 item sets its own and ignores this.")
    parser.add_argument("--only", action="append", default=[],
                        help="run just these item ids (repeatable)")
    args = parser.parse_args(argv)

    work = args.work_dir or Path(tempfile.mkdtemp(prefix="bearing_block_"))
    work.mkdir(parents=True, exist_ok=True)

    if not check_abaqus():
        reason = "Abaqus not found (set ABAQUS_AGENT_ABAQUS_CMD)"
        items = [_skipped(item_id, reason) for item_id in ITEM_IDS]
    else:
        items = []
        wanted = set(args.only) if args.only else None
        groups = [
            (ITEM_IDS[:4], lambda: check_identities(work, args.tie_tolerance)),
            (ITEM_IDS[4:5],
             lambda: [check_coarse_mesh_drops_the_tie(work, args.tie_tolerance)]),
            (ITEM_IDS[5:6], lambda: [check_the_seeds_are_the_fix(work)]),
            (ITEM_IDS[6:7],
             lambda: [check_tolerance_still_sees_a_misalignment(
                 work, args.tie_tolerance)]),
        ]
        for ids, run_group in groups:
            if wanted is not None and not (wanted & set(ids)):
                continue
            try:
                produced = run_group()
            except Exception as exc:
                produced = [{"id": item_id, "status": "fail",
                             "problems": ["the check itself raised: %s: %s"
                                          % (type(exc).__name__, exc)]}
                            for item_id in ids]
            for item in produced:
                if wanted is None or item["id"] in wanted:
                    items.append(item)

    statuses = [item["status"] for item in items]
    if "fail" in statuses:
        overall = "fail"
    elif statuses and all(s == "skipped" for s in statuses):
        overall = "skipped"
    elif "skipped" in statuses:
        overall = "partial"
    else:
        overall = "pass"

    report = {
        "schema": "bearing_block_check/1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "abaqus_release": detect_abaqus_release(),
        "work_dir": str(work),
        "tie_tolerance": args.tie_tolerance,
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
