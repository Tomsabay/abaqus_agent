#!/usr/bin/env python3
"""Real-solver check for the job layer, the buckling KPI, and when a KPI type
is checked.

Three things a spec could not say before, and one it could say too late.

THE LAUNCHER OPTIONS. Double precision, a user subroutine, what to restart
from, GPUs -- none of these are deck keywords, they are arguments to the
`abaqus` command, and a spec had nowhere to put them. `job:` is a passthrough
rather than a list of supported flags, and what makes a passthrough safe here
was measured rather than assumed (artifacts/probe_job): an unknown option, an
unsupported value, a missing subroutine file and a missing restart odb are all
rejected by the launcher, which prints the reason and the 36 options it
accepts -- AND ALL FOUR EXIT 0, writing no .dat and no .odb. So the option is
never judged here; Abaqus judges it and this side reads stdout, because the
exit code has nothing in it. The printed list is deliberately not used as a
validator either: it omits `gpus`, and `gpus=1` runs (6 licence tokens instead
of 5, 3m45s instead of 11s, same one-element deck).

THE BUCKLING KPI. A *BUCKLE step answers with a load multiplier, and it is not
where a frequency is. Measured: `frame.frequency` is None, `frame.frameValue`
is the mode ORDINAL, `step.historyRegions` is empty, and the number exists
only as text in `frame.description` -- to five significant figures, which the
.dat repeats exactly, so that ceiling is Abaqus's and not this parser's.

WHEN A KPI TYPE IS CHECKED. It used to be an unconstrained string: an unknown
one validated, built, meshed, solved, and raised "Unknown kpi type" from inside
the Abaqus kernel. Item 6 is the same typo, refused before anything starts.

Exit codes: 0 = nothing failed (no Abaqus => "skipped", still 0);
            1 = at least one item ran and failed.
"""

from __future__ import annotations

import copy
import json
import math
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.helpers import check_abaqus  # noqa: E402
from tools.abaqus_cmd import detect_abaqus_release, get_abaqus_cmd  # noqa: E402

MODEL = "JobLayerCheck"
E, NU, RHO = 210000.0, 0.3, 7.85e-9
B = 10.0                 # square section side
L = 200.0                # column length
INERTIA = B * B ** 3 / 12.0
REF_LOAD = 1.0
# Fixed-free Euler, which is the end condition this rig builds: encastre at
# z = 0 and a free tip carrying the reference load.
P_CR = math.pi ** 2 * E * INERTIA / (4.0 * L ** 2)      # 10794.88 N
# Measured 10744.0 against 10794.88, which is 0.47% out, so 2% is room for
# mesh and solver drift rather than room for the answer to be wrong. It was 6%
# while the rig still used a pressure load; that load turned out to be the
# problem, not the tolerance, and widening a band to admit a wrong number is
# the move this project exists to avoid.
BUCKLE_BAND = 0.02


def _column_part(seed: float) -> dict:
    return {"name": "Col",
            "features": [{"op": "sketch", "id": "o", "plane": "XY",
                          "profile": {"rect": {"corner1": [0.0, 0.0],
                                               "corner2": [B, B]}}},
                         {"op": "extrude", "sketch": "o", "depth": L}],
            "section": {"type": "solid", "material": "Steel"},
            "mesh": {"seed": seed, "element": "C3D8I",
                     "technique": "structured"}}


def _buckle_spec(seed: float = 5.0) -> dict:
    """A column that buckles, built through the ordinary v2 path.

    The load is 1 N so the eigenvalue IS the buckling load: Abaqus reports a
    multiplier on whatever the step's live load happens to be, and picking 1
    removes the one arithmetic step between the answer and the closed form.
    """
    return {
        "meta": {"abaqus_release": "2021", "model_name": MODEL,
                 "units": "mm_MPa_t"},
        "material": {"name": "Steel", "E": E, "nu": NU, "density": RHO},
        "parts": [_column_part(seed)],
        "assembly": {"instances": [{"name": "Col", "part": "Col",
                                    "translate": [0.0, 0.0, 0.0]}]},
        "steps": [{"call": "BuckleStep", "name": {"literal": "Buckle"},
                   "previous": {"literal": "Initial"},
                   "numEigen": 4, "vectors": 8, "maxIterations": 100}],
        "conditions": [
            {"call": "EncastreBC", "name": {"literal": "Fix"},
             "createStepName": {"literal": "Initial"},
             "region": {"set": "Col:face@z=min", "name": "FIX",
                        "expect": "=1"}},
            # The load arrives through a reference point rather than as a
            # pressure, and that is a physics decision rather than a stylistic
            # one. Measured first with `Pressure` at 1/(B*B): the eigenvalue
            # came back -25243 against a closed form of +10794.88 -- wrong
            # sign and 2.34x the magnitude -- because a distributed pressure
            # follows the face as it rotates, and a follower load is not the
            # dead load Euler's formula is about. A force on a control point
            # keeps its direction, which is the case pi^2 EI / 4L^2 describes.
            {"call": "Coupling", "name": {"literal": "Cap"},
             "controlPoint": {"reference_point": {"at": "Col:face@z=max"},
                              "name": "RP"},
             "surface": {"surface": "Col:face@z=max", "name": "TOP",
                         "expect": "=1"},
             "influenceRadius": "WHOLE_SURFACE", "couplingType": "KINEMATIC",
             "localCsys": None,
             "u1": "ON", "u2": "ON", "u3": "ON",
             "ur1": "ON", "ur2": "ON", "ur3": "ON"},
            {"call": "ConcentratedForce", "name": {"literal": "Squash"},
             "createStepName": {"literal": "Buckle"},
             "region": {"named_set": "RP"},
             "cf3": -REF_LOAD, "distributionType": "UNIFORM",
             "localCsys": None},
        ],
        "outputs": {"kpis": [
            {"name": "P_CR", "type": "eigenvalue", "location": "mode_1",
             "step": "Buckle"}]},
    }


def _static_spec(job: dict | None = None,
                 kpi_type: str = "field_min") -> dict:
    """A one-step static run, small enough to spend on a launcher option."""
    spec = {
        "meta": {"abaqus_release": "2021", "model_name": MODEL,
                 "units": "mm_MPa_t"},
        "material": {"name": "Steel", "E": E, "nu": NU, "density": RHO},
        "parts": [_column_part(25.0)],
        "assembly": {"instances": [{"name": "Col", "part": "Col",
                                    "translate": [0.0, 0.0, 0.0]}]},
        "steps": [{"call": "StaticStep", "name": {"literal": "One"},
                   "previous": {"literal": "Initial"}}],
        "conditions": [
            {"call": "EncastreBC", "name": {"literal": "Fix"},
             "createStepName": {"literal": "Initial"},
             "region": {"set": "Col:face@z=min", "name": "FIX",
                        "expect": "=1"}},
            {"call": "Pressure", "name": {"literal": "Push"},
             "createStepName": {"literal": "One"},
             "region": {"surface": "Col:face@z=max", "name": "TOP",
                        "expect": "=1"},
             "magnitude": 1.0, "distributionType": "UNIFORM"},
        ],
        "outputs": {"kpis": [
            {"name": "U", "type": kpi_type, "location": "whole_model",
             "component": "U3"}]},
    }
    if job is not None:
        spec["job"] = job
    return spec


# --- plumbing --------------------------------------------------------------

def _fresh(work: Path) -> Path:
    import shutil

    work = work.resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    return work


def _solve(spec: dict, work: Path) -> dict:
    from agent.orchestrator import build_orchestrator
    _fresh(work)
    return build_orchestrator(spec_dict=copy.deepcopy(spec), workdir=work,
                              expected_path=None, runner_cfg=None).run()


def _kpi(result: dict, name: str):
    value = (result.get("kpis") or {}).get(name)
    return value.get("value") if isinstance(value, dict) else value


def _error_text(result: dict) -> str:
    err = result.get("error")
    if isinstance(err, dict):
        return "%s: %s" % (err.get("error_code"), err.get("message"))
    return str(err or "")


def _submitted_cmd(result: dict) -> str:
    return str((result.get("stages") or {}).get("submit_job", {}).get("cmd", ""))


_PRECISION = """\
import json, sys
from odbAccess import openOdb
odb = openOdb(sys.argv[-1], readOnly=True)
print('PREC ' + json.dumps({'precision': str(odb.jobData.precision)}))
"""


def _odb_precision(work: Path) -> str:
    """What the ODB says about how the job was run.

    Read because item 1 asserts something uncomfortable: that this value does
    NOT move when the spec asks for double precision. If a later Abaqus starts
    reporting it properly, this item fails and the claim in the docs has to be
    rewritten -- which is the point of pinning it rather than only writing it
    down.
    """
    odb = work / ("%s.odb" % MODEL)
    if not odb.exists():
        return "NO_ODB"
    script = work / "_prec.py"
    script.write_text(_PRECISION, encoding="utf-8")
    proc = subprocess.run(
        [get_abaqus_cmd(), "python", "_prec.py", odb.name],
        cwd=str(work), stdin=subprocess.DEVNULL, capture_output=True,
        text=True, errors="replace", timeout=900)
    for line in (proc.stdout or "").splitlines():
        if line.startswith("PREC "):
            return json.loads(line[len("PREC "):])["precision"]
    return "UNREADABLE: %s" % ((proc.stdout or "") + (proc.stderr or ""))[-200:]


def _skipped(item_id: str, reason: str) -> dict:
    return {"id": item_id, "status": "skipped", "reason": reason}


# --- items -----------------------------------------------------------------

def check_option_reaches_the_launcher(work: Path) -> dict:
    """`job: {double: both}` gets onto the command line and the job still runs.

    And the second half, which is the uncomfortable half: NOTHING SHOWS IT
    TOOK EFFECT. Measured across six combinations (Standard and Explicit x
    default, double=both, output_precision=full), `odb.jobData.precision`
    reads SINGLE_PRECISION every time, and the .dat, .msg and .sta of a
    default run and a double=both run are identical line for line. So this
    item passes only while that gap is real, and fails the day it closes.
    """
    room = work / "double_both"
    result = _solve(_static_spec(job={"double": "both"}), room)
    cmd = _submitted_cmd(result)
    precision = _odb_precision(room)

    problems = []
    if result.get("status") != "COMPLETED":
        problems.append("the job did not complete: %s / %s"
                        % (result.get("status"), _error_text(result)[:250]))
    if "double=both" not in cmd:
        problems.append(
            "the recorded command line does not carry `double=both`, so the "
            "`job:` block did not reach the launcher: %r" % cmd[-300:])
    if precision != "SINGLE_PRECISION":
        problems.append(
            "odb.jobData.precision reads %r. Measured on Abaqus 2021 it reads "
            "SINGLE_PRECISION even for double=both, which is why the schema's "
            "`job:` description says this project cannot show you that the "
            "option changed the arithmetic. If that is no longer true, that "
            "description is now wrong and should be rewritten -- a caveat "
            "nobody rechecks outlives the thing it was warning about."
            % precision)
    return {
        "id": "a_launcher_option_reaches_abaqus_and_stays_unverifiable",
        "status": "pass" if not problems else "fail",
        "odb_precision": precision,
        "note": "the option gets through and the job runs. What no layer here "
                "can show is that the precision changed -- the ODB says "
                "SINGLE_PRECISION either way, and .dat/.msg/.sta are "
                "identical. Passed through, not vouched for.",
        "problems": problems,
    }


def check_a_refused_option_stops_the_run(work: Path) -> dict:
    """The counterexample the whole passthrough rests on.

    Without it, `job:` is a hole: the launcher rejects the command line, exits
    0, writes nothing, and the pipeline would have carried on to look for
    results that were never produced.
    """
    result = _solve(_static_spec(job={"bogusoption": "1"}), work / "bogus")
    message = _error_text(result)
    problems = []
    if result.get("status") == "COMPLETED":
        problems.append(
            "a command line the launcher REFUSED was reported COMPLETED. It "
            "exits 0 and writes no .dat, so nothing but stdout says otherwise.")
    if "bogusoption" not in message:
        problems.append(
            "the failure does not name the offending option, which is the one "
            "thing that turns it from a stop into a fix: %r" % message[:300])
    if "Abaqus Error" not in message:
        problems.append(
            "the launcher's own sentence was not carried through; it is "
            "better than anything this side could write: %r" % message[:300])
    return {
        "id": "an_option_the_launcher_refuses_stops_the_run",
        "status": "pass" if not problems else "fail",
        "reported_message": message[:400],
        "note": "measured: exit code 0, no .dat, no .odb, and the reason on "
                "stdout only. Reading the exit code here would have reported "
                "success.",
        "problems": problems,
    }


def check_missing_file_is_caught_first(work: Path) -> dict:
    """Abaqus does check this -- after taking a licence, and with exit code 0.

    Measured: `user=nosuch.f` answers "The following file(s) could not be
    located". Getting there first costs nothing and saves a checkout.
    """
    result = _solve(_static_spec(job={"user": "nosuch.f"}), work / "no_user")
    message = _error_text(result)
    problems = []
    if result.get("status") == "COMPLETED":
        problems.append("a job naming a subroutine that is not there ran")
    if "nosuch.f" not in message:
        problems.append("the refusal does not name the file: %r"
                        % message[:300])
    if "FILE_NOT_FOUND" not in message:
        problems.append(
            "this should be caught on this side before Abaqus starts, so it "
            "should carry FILE_NOT_FOUND rather than a solver error code: %r"
            % message[:200])
    return {
        "id": "a_missing_subroutine_is_caught_before_the_licence",
        "status": "pass" if not problems else "fail",
        "reported_message": message[:300],
        "note": "before CAE, before the solver, before a token.",
        "problems": problems,
    }


def check_reserved_option_is_refused(work: Path) -> dict:
    """`cpus` is already on the command line; setting it here passes it twice.

    Measured behaviour of a duplicated option is that the launcher takes one of
    them and does not say which -- so a spec asking for 8 could silently get
    the runner's 1, or the other way about.
    """
    result = _solve(_static_spec(job={"cpus": 8}), work / "reserved")
    message = _error_text(result)
    problems = []
    if result.get("status") == "COMPLETED":
        problems.append("job.cpus was accepted and passed alongside the "
                        "pipeline's own cpus=")
    if "runner.json" not in message:
        problems.append(
            "the refusal does not say where the setting really lives, which "
            "leaves the user with a no and no next step: %r" % message[:300])
    return {
        "id": "an_option_the_pipeline_already_sets_is_refused",
        "status": "pass" if not problems else "fail",
        "reported_message": message[:300],
        "note": "not a capability limit -- a collision. The message names "
                "runner.json so the setting is still reachable.",
        "problems": problems,
    }


def check_buckling_eigenvalue(work: Path) -> dict:
    """The buckling load against Euler, through the ordinary v2 path.

    The reference load is 1 N, so the eigenvalue IS the buckling load and no
    arithmetic sits between the ODB and pi^2 E I / 4 L^2.
    """
    room = work / "buckle"
    result = _solve(_buckle_spec(), room)
    measured = _kpi(result, "P_CR")

    problems = []
    if result.get("status") != "COMPLETED":
        problems.append("the buckling job did not complete: %s / %s"
                        % (result.get("status"), _error_text(result)[:300]))
    if measured is None:
        problems.append(
            "no P_CR came back. The eigenvalue lives only in "
            "frame.description on Abaqus 2021; if that text changed shape the "
            "reader refuses rather than guessing, because the other "
            "candidates on the frame are the mode ordinal and None.")
    else:
        deviation = abs(measured - P_CR) / P_CR
        if deviation > BUCKLE_BAND:
            problems.append(
                "eigenvalue %.6g against Euler %.6g is %.2f%% out"
                % (measured, P_CR, deviation * 100.0))
    return {
        "id": "a_buckling_eigenvalue_matches_euler",
        "status": "pass" if not problems else "fail",
        "measured_eigenvalue": measured,
        "euler_p_cr": P_CR,
        "note": "reference load 1 N, so the multiplier is the load. Abaqus "
                "publishes it as text to five significant figures and the "
                ".dat repeats exactly those five, so the precision ceiling "
                "here is Abaqus's, not this reader's.",
        "problems": problems,
    }


def check_unknown_kpi_type(work: Path) -> dict:
    """The typo that used to cost a whole solve.

    `field_minimum` for `field_min`. Before this it validated, built, meshed,
    solved, and then raised "Unknown kpi type" from inside a Python 2.7
    process -- an error message from the wrong layer, after the expensive part.
    """
    room = work / "bad_kpi"
    started = time.time()
    result = _solve(_static_spec(kpi_type="field_minimum"), room)
    seconds = time.time() - started
    message = _error_text(result)

    problems = []
    if result.get("status") == "COMPLETED":
        problems.append("a spec naming a KPI type nothing implements ran to "
                        "completion")
    if "field_minimum" not in message:
        problems.append("the refusal does not name the offending type: %r"
                        % message[:300])
    if (room / ("%s.odb" % MODEL)).exists():
        problems.append(
            "an .odb was produced, so the check still happened after the "
            "solve rather than before it")
    if (room / ("%s.inp" % MODEL)).exists():
        problems.append(
            "a deck was written, so the check happens after the build; it "
            "belongs in validation, which runs first")
    return {
        "id": "an_unknown_kpi_type_is_refused_before_anything_runs",
        "status": "pass" if not problems else "fail",
        "reported_message": message[:300],
        "seconds": round(seconds, 1),
        "note": "the same typo used to reach the Abaqus kernel. Nothing "
                "built, nothing solved -- the seconds on this item are the "
                "measurement.",
        "problems": problems,
    }


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=ROOT / "artifacts" / "job_layer_check"
                    / "report.json")
    ap.add_argument("--work", type=Path, default=None)
    args = ap.parse_args()

    work = args.work or (ROOT / "artifacts" / "job_layer_check")
    work.mkdir(parents=True, exist_ok=True)
    started = time.time()

    names = ("a_launcher_option_reaches_abaqus_and_stays_unverifiable",
             "an_option_the_launcher_refuses_stops_the_run",
             "a_missing_subroutine_is_caught_before_the_licence",
             "an_option_the_pipeline_already_sets_is_refused",
             "a_buckling_eigenvalue_matches_euler",
             "an_unknown_kpi_type_is_refused_before_anything_runs")

    release = None
    if not check_abaqus():
        reason = ("Abaqus not found (set ABAQUS_AGENT_ABAQUS_CMD or put "
                  "abaqus.bat on PATH)")
        items = [_skipped(name, reason) for name in names]
    else:
        release = detect_abaqus_release()
        items = [check_option_reaches_the_launcher(work),
                 check_a_refused_option_stops_the_run(work),
                 check_missing_file_is_caught_first(work),
                 check_reserved_option_is_refused(work),
                 check_buckling_eigenvalue(work),
                 check_unknown_kpi_type(work)]

    failed = [i for i in items if i["status"] == "fail"]
    report = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "abaqus_release": release,
        "seconds": round(time.time() - started, 1),
        "rig": {"euler_p_cr": P_CR, "reference_load_n": REF_LOAD,
                "column_length": L, "section": B},
        "overall": "fail" if failed else "pass",
        "items": items,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
