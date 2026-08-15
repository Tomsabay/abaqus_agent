#!/usr/bin/env python3
"""Real-solver check for the generic interaction layer.

Everything that joins instances hangs off the MODEL -- Tie, Coupling,
RigidBody, ShellSolidCoupling, MultipointConstraint, the whole contact family,
ConnectorSection -- 299 callables in all, of which the `interactions:` sugar
reached exactly two. These items drive the model object the same way the part
layer drives Part.

The measurement everything here is built around, taken on Abaqus 2021 on a
two-layer cantilever with both layers built in at the root and pressure on top
(artifacts/scratch_generic/probe_inter3):

    gap 0.00, position tolerance 0.01 -> tie holds,        tip U3 = -0.3533
    gap 0.05, position tolerance 0.01 -> tie holds NOTHING, tip U3 = -2.8094

The second job COMPLETED SUCCESSFULLY. Same *Tie card, same tolerance printed
in the .dat, 7.95x the deflection -- which is what losing one of two bonded
layers does to a bending stiffness. Abaqus does mutter ("*TIE ... IS REVERTED
... CANNOT FIND NODES TO TIE TOGETHER" in the .dat, "2 UNCONNECTED REGIONS" in
the .msg) but both are warnings inside a job that reports success, and by then
the solve has been paid for. So the pair is measured from surface node
coordinates before the job is written, and a call that builds two surfaces has
to say how far apart it expects them to be.

  1. `generic_tie_matches_the_named_tie`
  2. `generic_tie_survives_the_keyword_rename` -- the spec writes main=, this
     release wants master=, and the shim says so in the log
  3. `generic_interaction_requires_a_gap_statement`
  4. `generic_tie_refuses_a_pair_that_cannot_bind`
  5. `generic_unbonded_pair_solves_to_the_wrong_answer` -- the same deck with
     the gap stated honestly instead of tightly: it SOLVES, and the answer is
     eight times wrong. This is the evidence that item 4 is load-bearing.
  6. `generic_contact_takes_behaviour_on_the_result` -- ContactProperty, then
     NormalBehavior on what it returned, which is not a method on the model
  7. `generic_general_contact_needs_no_pair` -- ContactStd, previously
     unreachable at any price
  8. `generic_interaction_refuses_an_unknown_method`

Exit codes: 0 = nothing failed (no Abaqus => "skipped", still 0);
            1 = at least one item ran and failed.
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.helpers import check_abaqus  # noqa: E402
from runner import build_v2  # noqa: E402
from tools.abaqus_cmd import detect_abaqus_release, get_abaqus_cmd  # noqa: E402

TIE_CASE = "two_plate_tie"
CONTACT_CASE = "two_plate_contact"

# The pair is 0.05 apart and the tie tolerance is 0.01, so it binds nothing.
# Small enough that the model still meshes and solves happily -- which is the
# whole problem.
DEAD_GAP = 0.05
TIE_TOLERANCE = 0.01

# Euler-Bernoulli for the bonded pair, from the case's own expected.json.
BONDED_U_TIP = -0.0714285714

# What a dead tie costs, and it is NOT the same as the contact case. Under
# contact the upper plate rests on the lower and the two share the load, each
# carrying its own I: 4x. With a tie that binds nothing there is no contact
# either, so the lower plate carries NOTHING and the whole pressure sits on a
# single 5 mm plate: qL^4/(8EI) with I = 10*5^3/12 = 104.17 gives -0.5714, or
# 8x. Measured -0.5671, 0.75% from that. A dead tie is therefore worse than no
# tie at all, which is the opposite of the intuition that it "falls back" to
# contact.
UNBONDED_FACTOR = 8.0


def _load(case: str) -> dict:
    return yaml.safe_load(
        (ROOT / "cases" / case / "spec.yaml").read_text(encoding="utf-8"))


# --- the specs -------------------------------------------------------------

def _generic_tie(gap: float = 0.0, expect: object = "tight",
                 method: str = "Tie") -> dict:
    """two_plate_tie with its tie written as the Abaqus call it is."""
    spec = _load(TIE_CASE)
    spec["meta"]["model_name"] = "GenericInterCheck"
    if gap:
        for inst in spec["assembly"]["instances"]:
            if inst["name"] == "Upper":
                inst["translate"] = [0.0, 5.0 + gap, 0.0]
    # main=/secondary= on purpose: Abaqus 2021 answers "keyword error on main"
    # and the rename shim has to carry it to master=/slave=.
    call = {
        "call": method,
        "name": {"literal": "MidPlane"},
        "main": {"surface": "Lower:face@y=max", "name": "BOND_MAIN",
                 "expect": "=1"},
        "secondary": {"surface": "Upper:face@y=min", "name": "BOND_SEC",
                      "expect": "=1"},
        "positionToleranceMethod": "SPECIFIED",
        "positionTolerance": TIE_TOLERANCE,
        "adjust": "OFF", "tieRotations": "ON", "thickness": "ON",
    }
    if expect == "tight":
        call["expect"] = {"gap": {"max": TIE_TOLERANCE / 10.0}}
    elif expect == "honest":
        # States what is really there. It passes -- and the job then solves to
        # the wrong answer, which is the point of item 5.
        call["expect"] = {"gap": {"max": gap + 0.01}}
    elif expect is not None:
        call["expect"] = expect
    spec["interactions"] = [call]
    return spec


def _generic_contact() -> dict:
    """two_plate_contact, with the property built and then configured."""
    spec = _load(CONTACT_CASE)
    spec["meta"]["model_name"] = "GenericInterCheck"
    spec["interactions"] = [
        {"call": "ContactProperty", "name": {"literal": "PAIRPROP"},
         "as": "prop"},
        {"call": "NormalBehavior", "target": {"ref": "prop"},
         "pressureOverclosure": "HARD", "allowSeparation": "ON",
         "constraintEnforcementMethod": "DEFAULT"},
        {"call": "TangentialBehavior", "target": {"ref": "prop"},
         "formulation": "FRICTIONLESS"},
        {"call": "SurfaceToSurfaceContactStd",
         "name": {"literal": "Pair"},
         "createStepName": {"literal": "Initial"},
         "main": {"surface": "Lower:face@y=max", "name": "PAIR_MAIN"},
         "secondary": {"surface": "Upper:face@y=min", "name": "PAIR_SEC"},
         "sliding": "SMALL", "thickness": "ON",
         "interactionProperty": {"literal": "PAIRPROP"},
         "adjustMethod": "NONE", "initialClearance": "OMIT",
         "datumAxis": None, "clearanceRegion": None,
         "expect": {"gap": {"max": 0.001}}},
    ]
    return spec


def _general_contact() -> dict:
    """No pairs at all: Abaqus finds the surfaces itself."""
    spec = _load(CONTACT_CASE)
    spec["meta"]["model_name"] = "GenericInterCheck"
    spec["interactions"] = [
        {"call": "ContactProperty", "name": {"literal": "GCPROP"}, "as": "prop"},
        {"call": "NormalBehavior", "target": {"ref": "prop"},
         "pressureOverclosure": "HARD", "allowSeparation": "ON",
         "constraintEnforcementMethod": "DEFAULT"},
        {"call": "TangentialBehavior", "target": {"ref": "prop"},
         "formulation": "FRICTIONLESS"},
        {"call": "ContactStd", "name": {"literal": "GC"},
         "createStepName": {"literal": "Initial"}, "as": "gc"},
        # General contact is configured through MEMBERS, not keywords, so the
        # surfaces and the property are attached by dispatching against them.
        {"call": "setValuesInStep", "target": {"ref": "gc",
                                               "attr": "includedPairs"},
         "stepName": {"literal": "Initial"}, "useAllstar": "ON"},
        {"call": "appendInStep",
         "target": {"ref": "gc", "attr": "contactPropertyAssignments"},
         "stepName": {"literal": "Initial"},
         "assignments": [["GLOBAL", "SELF", {"literal": "GCPROP"}]]},
    ]
    return spec


# --- plumbing --------------------------------------------------------------

def _build(work: Path, spec: dict) -> dict:
    """Generate and run the CAE script only. Never reaches the solver."""
    work = work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    log_path = work / "selectors.log"
    if log_path.exists():
        log_path.unlink()
    try:
        text = build_v2.generate_script(spec)
    except Exception as exc:
        return {"rc": None, "log": "", "built": False,
                "error": "%s: %s" % (type(exc).__name__, exc)}
    script = work / "build_model_script.py"
    script.write_text(text, encoding="utf-8")
    proc = subprocess.run(
        [get_abaqus_cmd(), "cae", "noGUI=" + script.name, "--", str(work), "spec"],
        cwd=str(work), capture_output=True, text=True,
        errors="replace", encoding="utf-8", stdin=subprocess.DEVNULL,
        timeout=1800)
    log = (log_path.read_text(encoding="utf-8", errors="replace")
           if log_path.exists() else "")
    return {"rc": proc.returncode, "log": log, "built": True,
            "error": (proc.stderr or "")[-4000:]}


def _solve(case: str, spec: dict, work: Path) -> dict:
    """Drive a synthesised spec all the way through, exactly as the CLI does."""
    from agent.orchestrator import build_orchestrator

    runner_path = ROOT / "cases" / case / "runner.json"
    runner_cfg = (json.loads(runner_path.read_text(encoding="utf-8"))
                  if runner_path.exists() else None)
    work.mkdir(parents=True, exist_ok=True)
    orch = build_orchestrator(spec_dict=copy.deepcopy(spec), workdir=work,
                              expected_path=None, runner_cfg=runner_cfg)
    return orch.run()


def _kpi(result: dict, name: str):
    value = result.get("kpis", {}).get(name)
    if isinstance(value, dict):
        return value.get("value")
    return value


def _evidence(out: dict) -> str:
    return "\n".join([out.get("error") or "", out.get("log") or ""])


def _line(out: dict, needle: str) -> str:
    for line in out["log"].splitlines():
        if needle in line:
            return line.strip()
    return ""


def _skipped(item_id: str, reason: str) -> dict:
    return {"id": item_id, "status": "skipped", "reason": reason}


def _refused_at_generation(out: dict) -> bool:
    return out["rc"] is None and not out["built"]


# --- items -----------------------------------------------------------------

def check_tie_matches(work: Path) -> list[dict]:
    """Items 1 and 2: same physics as the sugar, and the rename in the log."""
    run_dir = work / "tie_generic"
    result = _solve(TIE_CASE, _generic_tie(), run_dir)
    u_tip = _kpi(result, "U_TIP")

    problems = []
    if result.get("status") != "COMPLETED":
        problems.append("orchestrator status %s: %s"
                        % (result.get("status"), result.get("error")))
    elif u_tip is None:
        problems.append("no U_TIP in the result")
    else:
        deviation = abs(u_tip - BONDED_U_TIP) / abs(BONDED_U_TIP)
        if deviation > 0.10:
            problems.append(
                "U_TIP %r is %.1f%% from the bonded prediction %r; an unbonded "
                "pair would land near %r"
                % (u_tip, deviation * 100.0, BONDED_U_TIP,
                   BONDED_U_TIP * UNBONDED_FACTOR))

    log_text = ""
    log_path = run_dir / "selectors.log"
    for candidate in ([log_path] + sorted(run_dir.rglob("selectors.log"))):
        if candidate.exists():
            log_text = candidate.read_text(encoding="utf-8", errors="replace")
            break
    renamed = [ln.strip() for ln in log_text.splitlines()
               if "GENERIC_RENAMED" in ln]

    rename_problems = []
    if not problems and not renamed:
        rename_problems.append(
            "no GENERIC_RENAMED line. The spec writes main=/secondary= and "
            "Abaqus 2021 answers 'keyword error on main', so the shim should "
            "have renamed them to master=/slave=. Log tail: %s"
            % log_text[-600:])

    return [
        {
            "id": "generic_tie_matches_the_named_tie",
            "status": "pass" if not problems else "fail",
            "u_tip": u_tip,
            "bonded_prediction": BONDED_U_TIP,
            "unbonded_would_be": BONDED_U_TIP * UNBONDED_FACTOR,
            "note": "the tie is dispatched by name against the model, its two "
                    "regions are built by {surface:}, and the pair binds: the "
                    "two 5 mm halves behave as one 10 mm section.",
            "problems": problems,
        },
        {
            "id": "generic_tie_survives_the_keyword_rename",
            "status": ("skipped" if problems else
                       ("pass" if not rename_problems else "fail")),
            "reason": "the tie run failed" if problems else None,
            "log_line": renamed[0] if renamed else "",
            "note": "Abaqus renamed master/slave to main/secondary and did not "
                    "finish: 2021 refuses main=. A deck should not have to know "
                    "which install it will meet.",
            "problems": rename_problems,
        },
    ]


def check_requires_a_gap(work: Path) -> dict:
    """Item 3: a two-surface call with nothing said about the gap."""
    out = _build(work / "tie_no_expect", _generic_tie(expect=None))
    evidence = _evidence(out)
    problems = []
    if not _refused_at_generation(out):
        problems.append("a pair with no stated gap was accepted")
    elif "gap" not in evidence:
        problems.append("refused, but not about the gap: %s" % evidence[-400:])
    return {
        "id": "generic_interaction_requires_a_gap_statement",
        "status": "pass" if not problems else "fail",
        "refused_before_abaqus_started": _refused_at_generation(out),
        "message": (out.get("error") or "")[:400],
        "note": "nothing downstream can see an unbonded pair, so a call that "
                "builds two surfaces has to say how far apart they should be. "
                "A deliberate clearance is a fine answer; silence is not.",
        "problems": problems,
    }


def check_refuses_a_dead_pair(work: Path) -> dict:
    """Item 4: the gap is measured before the job is written."""
    out = _build(work / "tie_dead_gap", _generic_tie(gap=DEAD_GAP))
    evidence = _evidence(out)
    problems = []
    if out["rc"] == 0 and "EXPECT_GAP" not in evidence:
        problems.append("a pair 0.05 apart with a 0.01 tolerance was accepted")
    elif "EXPECT_GAP" not in evidence:
        problems.append("aborted, but not on the gap check: %s" % evidence[-500:])
    return {
        "id": "generic_tie_refuses_a_pair_that_cannot_bind",
        "status": "pass" if not problems else "fail",
        "gap": DEAD_GAP,
        "position_tolerance": TIE_TOLERANCE,
        "log_line": _line(out, "EXPECT_GAP"),
        "note": "measured from the two surfaces' node coordinates inside CAE, "
                "before the job is written -- so the solve is never paid for.",
        "problems": problems,
    }


def check_unbonded_solves_wrong(work: Path) -> dict:
    """Item 5: why item 4 is load-bearing.

    The same deck with the gap stated honestly instead of tightly. The check
    passes, the job runs to completion, and the answer is eight times wrong.
    """
    result = _solve(TIE_CASE, _generic_tie(gap=DEAD_GAP, expect="honest"),
                    work / "tie_unbonded")
    u_tip = _kpi(result, "U_TIP")
    problems = []
    if result.get("status") != "COMPLETED":
        problems.append(
            "the unbonded model did not complete (%s). The item depends on it "
            "completing: a job that fails is not the dangerous case."
            % result.get("status"))
    elif u_tip is None:
        problems.append("no U_TIP in the result")
    else:
        ratio = u_tip / BONDED_U_TIP
        if ratio < 2.0:
            problems.append(
                "U_TIP %r is only %.2fx the bonded value; the pair seems to "
                "have bound after all, which would make this item prove "
                "nothing" % (u_tip, ratio))
    return {
        "id": "generic_unbonded_pair_solves_to_the_wrong_answer",
        "status": "pass" if not problems else "fail",
        "job_status": result.get("status"),
        "u_tip": u_tip,
        "bonded_prediction": BONDED_U_TIP,
        "ratio_to_bonded": (None if u_tip is None else u_tip / BONDED_U_TIP),
        "single_plate_prediction": -0.5714285714,
        "note": "a completed job with a wrong number, from a deck that differs "
                "from the passing one by 0.05 mm of assembly translation. "
                "Nothing but the gap check stands between the two. 8x rather "
                "than the contact case's 4x because a dead tie leaves no "
                "contact either: the lower plate carries nothing and the whole "
                "pressure sits on one 5 mm plate.",
        "problems": problems,
    }


def check_contact_on_a_result(work: Path) -> dict:
    """Item 6: NormalBehavior is a method on the property, not on the model."""
    spec = _generic_contact()
    result = _solve(CONTACT_CASE, spec, work / "contact_generic")
    expected = json.loads(
        (ROOT / "cases" / CONTACT_CASE / "expected.json").read_text(
            encoding="utf-8"))
    want = expected["kpis"]["U_TIP"]["value"]
    rtol = float(expected["kpis"]["U_TIP"].get("rtol", 0.1))
    u_tip = _kpi(result, "U_TIP")
    problems = []
    if result.get("status") != "COMPLETED":
        problems.append("orchestrator status %s: %s"
                        % (result.get("status"), result.get("error")))
    elif u_tip is None:
        problems.append("no U_TIP in the result")
    elif abs(u_tip - want) / abs(want) > rtol:
        problems.append("U_TIP %r is outside %g of the case baseline %r"
                        % (u_tip, rtol, want))
    return {
        "id": "generic_contact_takes_behaviour_on_the_result",
        "status": "pass" if not problems else "fail",
        "u_tip": u_tip,
        "case_baseline": want,
        "note": "ContactProperty is called on the model and bound with `as:`; "
                "NormalBehavior and TangentialBehavior are then called on what "
                "it returned via `target: {ref: ...}`. The model has no such "
                "methods, so without that the contact family stays behind a "
                "hand-written wrapper.",
        "problems": problems,
    }


def check_general_contact(work: Path) -> dict:
    """Item 7: general contact, which the sugar could not express at all."""
    out = _build(work / "general_contact", _general_contact())
    evidence = _evidence(out)
    problems = []
    if out["rc"] != 0:
        problems.append("the build failed: %s" % evidence[-700:])
    elif not _line(out, "GENERIC_OK: interaction 4 ContactStd"):
        problems.append("no ContactStd in the log: %s" % evidence[-500:])
    return {
        "id": "generic_general_contact_needs_no_pair",
        "status": "pass" if not problems else "fail",
        "log_line": _line(out, "ContactStd"),
        "note": "ContactStd asks Abaqus to find the contacting surfaces "
                "itself, so there is no pair and nothing for expect.gap to "
                "measure -- which is why the gap is required only of a call "
                "that builds exactly two surfaces.",
        "problems": problems,
    }


def check_unknown_method(work: Path) -> dict:
    """Item 8: the dispatch is only safe because a mistake is loud."""
    out = _build(work / "unknown_method", _generic_tie(method="TieTheKnot"))
    evidence = _evidence(out)
    problems = []
    # NOT out["rc"]: the Abaqus launcher returns 0 whatever the script did, so
    # every item here has to look for a positive marker in the log instead. The
    # first version of this item checked rc and passed a broken build.
    if "GENERIC_OK: interaction 1 TieTheKnot" in evidence:
        problems.append("a method the model does not have was accepted")
    elif "GENERIC_NO_METHOD" not in evidence:
        problems.append(
            "the build stopped, but the log does not say why. print() from a "
            "noGUI script never reaches the launcher, so a refusal that only "
            "raises leaves selectors.log ending mid-build: %s" % evidence[-400:])
    return {
        "id": "generic_interaction_refuses_an_unknown_method",
        "status": "pass" if not problems else "fail",
        "log_line": _line(out, "GENERIC_NO_METHOD"),
        "note": "measured on Abaqus 2021, the model answers a method it has "
                "not got with an AttributeError naming it -- the same as Part. "
                "That is what makes dispatching to all 299 callables safe.",
        "problems": problems,
    }


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=ROOT / "artifacts" / "generic_interaction_check"
                    / "report.json")
    ap.add_argument("--work", type=Path, default=None)
    args = ap.parse_args()

    work = args.work or (ROOT / "artifacts" / "generic_interaction_check")
    work.mkdir(parents=True, exist_ok=True)
    started = time.time()

    if not check_abaqus():
        reason = ("Abaqus not found (set ABAQUS_AGENT_ABAQUS_CMD or put "
                  "abaqus.bat on PATH)")
        items = [_skipped(name, reason) for name in (
            "generic_tie_matches_the_named_tie",
            "generic_tie_survives_the_keyword_rename",
            "generic_interaction_requires_a_gap_statement",
            "generic_tie_refuses_a_pair_that_cannot_bind",
            "generic_unbonded_pair_solves_to_the_wrong_answer",
            "generic_contact_takes_behaviour_on_the_result",
            "generic_general_contact_needs_no_pair",
            "generic_interaction_refuses_an_unknown_method")]
        release = None
    else:
        release = detect_abaqus_release()
        items = []
        items.extend(check_tie_matches(work))
        items.append(check_requires_a_gap(work))
        items.append(check_refuses_a_dead_pair(work))
        items.append(check_unbonded_solves_wrong(work))
        items.append(check_contact_on_a_result(work))
        items.append(check_general_contact(work))
        items.append(check_unknown_method(work))

    failed = [i for i in items if i["status"] == "fail"]
    report = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "abaqus_release": release,
        "seconds": round(time.time() - started, 1),
        "overall": "fail" if failed else "pass",
        "items": items,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
