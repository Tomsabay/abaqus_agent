#!/usr/bin/env python3
"""Real-solver check for the things a spec could say and not get.

All of these came out of one question the layer had never been asked: is any of
this measured, or is it all argued from the shape of the API? It was all argued.

  1. `material_declared_plasticity_reaches_the_model` -- a spec declaring
     `yield: 250` used to solve elastically. Measured before the fix: peak Mises
     917.4 MPa against the 250 it declared, job COMPLETED, no *Plastic card, and
     nothing in the log. The v1 generator emitted Plastic for the same key, so
     one spec meant two models.
  2. `material_an_unbuildable_key_is_refused_not_dropped` -- the other half. A
     property this side cannot build must stop the spec, not vanish from it.
  3. `material_thermal_properties_reach_the_model` -- conductivity and specific
     heat, and the element companions a heat transfer mesh needs.
  4. `conditions_a_reused_name_is_refused` -- Abaqus REPLACES a condition of an
     existing name rather than adding one, keeping only the later region and the
     later step, so the earlier step ends up with no card at all. Measured, and
     the input file was written.
  5. `steps_a_replacement_is_caught_at_run_time_too` -- the same collision with
     the name written where the host side cannot read it, caught against the
     model's own registries instead.
  6. `outputs_a_heat_transfer_analysis_can_ask_for_its_own_variables` -- the
     field output request was a literal ('S','E','U','RF'); S, E and RF do not
     exist in a heat transfer step, so Abaqus refused the request and no input
     file was written at all.
  7. `diagnostics_a_kernel_crash_says_so` -- FluidPipeSection takes ABQcaeK.exe
     down with EXCEPTION_ACCESS_VIOLATION. Not a Python exception, so no gate in
     the deck can catch it; the launcher still returns 0. The pipeline used to
     report ".inp not generated, check the log" with an empty snippet and a
     suggestion to simplify the geometry.
  8. `dispatch_a_target_reaches_the_object_it_names` -- `target:` was dropped
     without a word on three of the five dispatch paths, and honouring it makes
     the seven methods a load or BC exposes reachable at all.
  9. `dispatch_attr_alone_reaches_the_keyword_block` -- `m.keywordBlock` is not
     the result of any call, so no `{ref:}` can name it and the escape hatch
     for cards this dialect has no name for did not exist. Measured while
     wiring it: one spec, one card, two positions -- after block 21 the deck
     datachecks with 0 errors, after block 3 CAE wraps it in a *Conflicts block
     and Abaqus reports 4 FATAL ERRORS, and BOTH used to report success with
     KEYWORD_OK in the log.
 10. `dispatch_attr_alone_reaches_engineering_features` -- the other member
     the same route was written for. Proven the strongest way available: a
     `ContourIntegral` dispatched through `{attr: engineeringFeatures}` on the
     assembly RUNS, and the build writes an input file. It used to be proven by
     Abaqus's complaint about the argument, because nothing on that object
     could be called successfully from a spec; #76 changed that. The other half
     is the one call there still refused -- `assignSeam` -- and what is pinned
     is that it routes to the PART and gives the reason that is actually true
     (timing: a seam has to be assigned before generateMesh), because a no with
     no next step is not a fix.
 11. `steps_a_named_step_chains_onto_a_dispatched_one` -- the two step forms
     have to be mixable.

Rig: 10 x 10 x 100 cantilever, C3D8I, encastred at z = 0, E = 210000, nu = 0.3,
I = 833.333 mm^4. First yield is at 416.7 N and the plastic limit load is 625 N,
so the 560 N used here is 90% of collapse: M/My = 1.34 and 44% of the depth has
yielded at the root. Two things about the rig were learned the hard way. The
mesh has to be fine enough for an integration point to SEE the yield -- at seed
5.0 the outermost one sits 3.94 mm from the neutral axis and reads 236 MPa,
under the 250 MPa yield, so nothing yields and the surface stress shows up only
as extrapolation. And the load has to be spread over the end face rather than
put on its four corner nodes, because a point load on a mesh that fine is a
singularity: it read 677 MPa peak Mises where beam theory says 300.

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

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.helpers import check_abaqus  # noqa: E402
from runner import build_v2  # noqa: E402
from tools.abaqus_cmd import detect_abaqus_release, get_abaqus_cmd  # noqa: E402

MODEL = "DroppedInputCheck"
W = H = 10.0
L = 100.0
E, NU, RHO = 210000.0, 0.3, 7.85e-9
YIELD = 250.0
INERTIA = W * H ** 3 / 12.0
# Between first yield and collapse, on purpose. First yield is
# sigma_y I / (c L) = 416.7 N and the plastic limit load is
# sigma_y b h^2 / (4 L) = 625 N; the first attempt used 1500 N, which is
# 2.4x the limit, so the beam collapsed and the job correctly refused to
# converge -- plasticity working, but a test that proves nothing about the
# answer.
TIP_LOAD = 560.0                                         # 90% of the limit
ELASTIC_PEAK = TIP_LOAD * L * (H / 2.0) / INERTIA        # 336 MPa


def _part(element="C3D8I", seed=1.25):
    return {"name": "Beam",
            "features": [{"op": "sketch", "id": "o", "plane": "XY",
                          "profile": {"rect": {"corner1": [0.0, 0.0],
                                               "corner2": [W, H]}}},
                         {"op": "extrude", "sketch": "o", "depth": L}],
            "section": {"type": "solid", "material": "Steel"},
            "mesh": {"seed": seed, "element": element,
                     "technique": "structured"}}


def _spec(material, steps, conditions, kpis, outputs_extra=None,
          element="C3D8I", seed=1.25):
    outputs = {"kpis": kpis}
    outputs.update(outputs_extra or {})
    return {"meta": {"abaqus_release": "2021", "model_name": MODEL,
                     "units": "mm_MPa_t"},
            "material": material,
            "parts": [_part(element, seed)],
            "assembly": {"instances": [{"name": "Bar", "part": "Beam",
                                        "translate": [0.0, 0.0, 0.0]}]},
            "steps": steps,
            "conditions": conditions,
            "outputs": outputs}


FIX = {"call": "EncastreBC", "name": {"literal": "Fix"},
       "createStepName": {"literal": "Initial"},
       "region": {"set": "Bar:face@z=min", "name": "FIX", "expect": "=1"}}
# initialInc below the default 1.0 because plasticity needs the load put on
# in steps; one increment straight to 80% of the collapse load does not
# converge and the item would fail for a reason that is not the point.
STATIC = [{"call": "StaticStep", "name": {"literal": "One"},
           "previous": {"literal": "Initial"}, "initialInc": 0.1,
           "maxNumInc": 200}]
# The same 500 N spread over the end face rather than put on its four corner
# nodes. A point load on a mesh fine enough for plasticity is a singularity:
# the four-vertex form read 677 MPa peak Mises against the 300 MPa beam theory
# says, because the peak was at the load and not at the root.
TIP_FORCE = {"call": "SurfaceTraction", "name": {"literal": "Tip"},
             "createStepName": {"literal": "One"},
             "region": {"surface": "Bar:face@z=max", "name": "TIPFACE",
                        "expect": "=1"},
             "magnitude": TIP_LOAD / (W * H),
             "directionVector": [[0.0, 0.0, 0.0], [0.0, -1.0, 0.0]],
             "distributionType": "UNIFORM", "traction": "GENERAL"}
ELASTIC_TIP = TIP_LOAD * L ** 3 / (3.0 * E * INERTIA)    # 1.067 mm
STRESS_KPIS = [{"name": "MISES_MAX", "type": "field_max",
                "location": "whole_model", "invariant": "MISES"},
               {"name": "U_TIP", "type": "field_min",
                "location": "whole_model", "component": "U2"}]


# --- plumbing --------------------------------------------------------------

def _build(work: Path, spec: dict, edit=None) -> dict:
    """Generate and run one build script.

    `edit` rewrites the generated script before it runs. Nothing a spec can say
    should need it -- it exists so an item can knock out one emitted line and
    watch a check react, which is the only way to make a truth-layer check face
    the failure it was written for when the generator will not produce that
    failure on its own. `script_edited` says whether the rewrite changed
    anything, so an item cannot pass on an edit that silently matched nothing.
    """
    work = work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    for junk in ("selectors.log", "%s.inp" % MODEL):
        if (work / junk).exists():
            (work / junk).unlink()
    try:
        text = build_v2.generate_script(spec)
    except Exception as exc:
        return {"built": False, "log": "", "inp": "",
                "refused_at_generation": "%s: %s" % (type(exc).__name__, exc)}
    edited = False
    if edit is not None:
        rewritten = edit(text)
        edited = rewritten != text
        text = rewritten
    (work / "build_model_script.py").write_text(text, encoding="utf-8")
    proc = subprocess.run(
        [get_abaqus_cmd(), "cae", "noGUI=build_model_script.py", "--",
         str(work), "spec"],
        cwd=str(work), capture_output=True, text=True, errors="replace",
        encoding="utf-8", stdin=subprocess.DEVNULL, timeout=1800)
    log = work / "selectors.log"
    inp = work / ("%s.inp" % MODEL)
    return {"built": True,
            "log": log.read_text(encoding="utf-8", errors="replace")
                   if log.exists() else "",
            "inp": inp.read_text(encoding="utf-8", errors="replace")
                   if inp.exists() else "",
            "inp_written": inp.exists(),
            "script_edited": edited,
            "stderr": (proc.stderr or "")[-2000:],
            "refused_at_generation": None}


def _datacheck_errors(work: Path) -> dict:
    """Run the input file processor over a written deck and count its errors.

    Reads the .dat rather than the exit code, because `abaqus ... datacheck`
    returns 0 on a deck it refused: measured on Abaqus 2021, a deck carrying a
    *Conflicts block exits 0 with "THE PROGRAM HAS DISCOVERED 4 FATAL ERRORS"
    and "EXECUTION IS TERMINATED" in the .dat. Same launcher-always-succeeds
    trap as everywhere else on this side.

    Copied into a subdirectory because the processor writes over the job files,
    and the caller still needs the deck it handed in.
    """
    inp = work / ("%s.inp" % MODEL)
    if not inp.exists():
        return {"ran": False, "errors": None, "fatal": ""}
    room = work / "datacheck"
    room.mkdir(parents=True, exist_ok=True)
    (room / "deck.inp").write_text(
        inp.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    try:
        subprocess.run(
            [get_abaqus_cmd(), "job=deck", "input=deck.inp", "datacheck",
             "interactive"],
            cwd=str(room), stdin=subprocess.DEVNULL, capture_output=True,
            text=True, errors="replace", timeout=1800)
    except Exception as exc:
        return {"ran": False, "errors": None,
                "fatal": "%s: %s" % (type(exc).__name__, exc)}
    dat = room / "deck.dat"
    if not dat.exists():
        return {"ran": False, "errors": None, "fatal": "no .dat written"}
    text = dat.read_text(encoding="utf-8", errors="replace")
    fatal = [ln.strip() for ln in text.splitlines() if "FATAL ERRORS" in ln]
    return {"ran": True, "errors": text.upper().count("***ERROR"),
            "fatal": "; ".join(fatal)}


def _solve(spec: dict, work: Path) -> dict:
    from agent.orchestrator import build_orchestrator
    work.mkdir(parents=True, exist_ok=True)
    return build_orchestrator(spec_dict=copy.deepcopy(spec), workdir=work,
                              expected_path=None, runner_cfg=None).run()


def _kpi(result: dict, name: str):
    value = (result.get("kpis") or {}).get(name)
    return value.get("value") if isinstance(value, dict) else value


def _line(out: dict, needle: str) -> str:
    for line in (out.get("log") or "").splitlines():
        if needle in line:
            return line.strip()
    return ""


def _skipped(item_id: str, reason: str) -> dict:
    return {"id": item_id, "status": "skipped", "reason": reason}


# --- items -----------------------------------------------------------------

def check_plasticity(work: Path) -> dict:
    """Two decks, one key apart, two different answers, both COMPLETED."""
    elastic_mat = {"name": "Steel", "E": E, "nu": NU, "density": RHO}
    plastic_mat = dict(elastic_mat)
    plastic_mat["yield"] = YIELD
    plastic_mat["hardening"] = 1000.0

    elastic = _solve(_spec(elastic_mat, STATIC, [FIX, TIP_FORCE], STRESS_KPIS),
                     work / "elastic_control")
    plastic = _solve(_spec(plastic_mat, STATIC, [FIX, TIP_FORCE], STRESS_KPIS),
                     work / "plastic")

    elastic_peak = _kpi(elastic, "MISES_MAX")
    plastic_peak = _kpi(plastic, "MISES_MAX")
    inp = work / "plastic" / ("%s.inp" % MODEL)
    text = inp.read_text(encoding="utf-8", errors="replace") if inp.exists() else ""

    problems = []
    for label, result in (("elastic control", elastic), ("plastic", plastic)):
        if result.get("status") != "COMPLETED":
            problems.append("%s: status %s -- %s"
                            % (label, result.get("status"),
                               str(result.get("error"))[:200]))
    if not problems:
        if "*Plastic" not in text:
            problems.append("no *Plastic card in the input file")
        if elastic_peak is None or plastic_peak is None:
            problems.append("no MISES_MAX to compare")
        else:
            if plastic_peak >= elastic_peak:
                problems.append(
                    "declaring yield %r changed nothing: %r against the "
                    "elastic %r" % (YIELD, plastic_peak, elastic_peak))
            elastic_tip = _kpi(elastic, "U_TIP")
            plastic_tip = _kpi(plastic, "U_TIP")
            if elastic_tip is None or plastic_tip is None:
                problems.append("no U_TIP to compare")
            elif abs(abs(elastic_tip) - ELASTIC_TIP) / ELASTIC_TIP > 0.06:
                problems.append(
                    "the elastic control deflected %r where P L^3 / (3 E I) is "
                    "%r, so this rig is not the beam the item reasons about "
                    "and neither number below means anything"
                    % (elastic_tip, -ELASTIC_TIP))
            elif abs(plastic_tip) <= 1.005 * abs(elastic_tip):
                problems.append(
                    "the yielded beam is not measurably softer: tip %r against the "
                    "elastic %r. A beam with a plastic zone at the root deflects "
                    "more, "
                    "so this is the signature that the plasticity is carrying "
                    "load rather than merely appearing in the input file."
                    % (plastic_tip, elastic_tip))
    return {
        "id": "material_declared_plasticity_reaches_the_model",
        "status": "pass" if not problems else "fail",
        "declared_yield": YIELD,
        "tip_load_n": TIP_LOAD,
        "beam_theory_root_fibre_stress": ELASTIC_PEAK,
        "beam_theory_elastic_tip": -ELASTIC_TIP,
        "elastic_control_peak": elastic_peak,
        "with_yield_declared_peak": plastic_peak,
        "elastic_tip": _kpi(elastic, "U_TIP"),
        "plastic_tip": _kpi(plastic, "U_TIP"),
        "plastic_card": [ln.strip() for ln in text.splitlines()
                         if ln.startswith("*Plastic")][:1],
        "note": "peak Mises is compared between the two runs and not against "
                "beam theory: on a solid model the largest Mises is at the "
                "encastred corner, which concentrates. The rig is checked on "
                "the tip deflection instead, which is global. The load sits "
                "at 90% of the plastic limit load (625 N) and well past "
                "first yield (416.7 N): M/My = 1.34, so 44% of the depth has "
                "yielded at the root and the softening is structural rather "
                "than a sliver at the surface. Before "
                "the fix the same spec solved elastically: measured 917.4 MPa "
                "at a 1500 N load against the 250 MPa it declared, COMPLETED, "
                "no *Plastic card, nothing in the log. The v1 generator emitted "
                "Plastic for this key all along.",
        "problems": problems,
    }


def check_unbuildable_key(work: Path) -> dict:
    """A property this side cannot build must stop the spec."""
    rows = {}
    problems = []
    for key, value in (("fracture_energy", 1.0), ("max_traction", 10.0),
                       ("yield_stress", 250.0), ("poissons_ratio", 0.3)):
        material = {"name": "Steel", "E": E, "nu": NU, "density": RHO,
                    key: value}
        out = _build(work / ("bad_%s" % key),
                     _spec(material, STATIC, [FIX], STRESS_KPIS))
        rows[key] = out.get("refused_at_generation")
        if not rows[key]:
            problems.append("%s was accepted and silently dropped" % key)
    return {
        "id": "material_an_unbuildable_key_is_refused_not_dropped",
        "status": "pass" if not problems else "fail",
        "refusals": rows,
        "note": "the other half of the plasticity fix: emitting what is known "
                "is only safe if what is not known stops the build.",
        "problems": problems,
    }


def check_thermal_properties(work: Path) -> dict:
    material = {"name": "Steel", "E": E, "nu": NU, "density": RHO,
                "conductivity": 45.0, "specific_heat": 5.0e8,
                "expansion_coeff": 1.2e-5}
    out = _build(work / "thermal",
                 _spec(material,
                       [{"call": "HeatTransferStep", "name": {"literal": "One"},
                         "previous": {"literal": "Initial"},
                         "response": "STEADY_STATE", "amplitude": "RAMP"}],
                       [{"call": "TemperatureBC", "name": {"literal": "Cold"},
                         "createStepName": {"literal": "One"},
                         "region": {"set": "Bar:face@z=min", "name": "COLD",
                                    "expect": "=1"}, "magnitude": 0.0},
                        {"call": "TemperatureBC", "name": {"literal": "Hot"},
                         "createStepName": {"literal": "One"},
                         "region": {"set": "Bar:face@z=max", "name": "HOT",
                                    "expect": "=1"}, "magnitude": 100.0}],
                       [{"name": "NT_MAX", "type": "field_max",
                         "location": "whole_model", "invariant": "MISES"}],
                       outputs_extra={"field_variables": ["NT", "HFL"]},
                       element="DC3D8", seed=10.0))
    text = out.get("inp") or ""
    problems = []
    if not out.get("inp_written"):
        problems.append("no input file: %s" % (out.get("stderr") or "")[-400:])
    else:
        for card in ("*Conductivity", "*Specific Heat", "*Expansion"):
            if card not in text:
                problems.append("no %s card" % card)
    return {
        "id": "material_thermal_properties_reach_the_model",
        "status": "pass" if not problems else "fail",
        "cards": [ln.strip() for ln in text.splitlines()
                  if ln.startswith(("*Conductivity", "*Specific Heat",
                                    "*Expansion"))],
        "note": "conductivity / specific_heat / expansion_coeff are declared in "
                "the schema and were dropped by this dialect. A thermal "
                "analysis with no conductivity is not a thermal analysis.",
        "problems": problems,
    }


def _two_step(second_name):
    return _spec(
        {"name": "Steel", "E": E, "nu": NU, "density": RHO},
        [{"call": "StaticStep", "name": {"literal": "One"},
          "previous": {"literal": "Initial"}},
         {"call": "StaticStep", "name": {"literal": "Two"},
          "previous": {"literal": "One"}}],
        [FIX,
         {"call": "DisplacementBC", "name": {"literal": "Push"},
          "createStepName": {"literal": "One"},
          "region": {"set": "Bar:face@z=max", "name": "TIP", "expect": "=1"},
          "u2": 0.0},
         {"call": "DisplacementBC", "name": second_name,
          "createStepName": {"literal": "Two"},
          "region": {"set": "Bar:face@z=max", "name": "TIP2", "expect": "=1"},
          "u2": -5.0}],
        STRESS_KPIS)


def check_reused_name(work: Path) -> dict:
    out = _build(work / "reused_name", _two_step({"literal": "Push"}))
    problems = []
    message = out.get("refused_at_generation") or ""
    if "already carries the name" not in message:
        problems.append("a reused condition name was accepted: %r" % message)
    return {
        "id": "conditions_a_reused_name_is_refused",
        "status": "pass" if not problems else "fail",
        "refusal": message,
        "note": "measured before the fix: Abaqus accepted it, wrote the input "
                "file, and the model had NO boundary card in step One at all -- "
                "the second call replaced the first, keeping only the later "
                "region and the later step. The log line read GENERIC_OK.",
        "problems": problems,
    }


def check_reused_name_at_runtime(work: Path) -> dict:
    """The same collision somewhere the host-side check does not look.

    _reuse_refuse compares the names of CONDITIONS. Two dispatched STEPS of the
    same name go straight past it -- and Abaqus replaces the first there too, so
    a spec that meant two steps gets one. The runtime gate does not know what a
    step is; it knows that a named call which added nothing to any registry,
    whose name is already in one, landed on top of something.
    """
    folder = work / "reused_name_runtime"
    spec = _spec({"name": "Steel", "E": E, "nu": NU, "density": RHO},
                 [{"call": "StaticStep", "name": {"literal": "One"},
                   "previous": {"literal": "Initial"}},
                  {"call": "StaticStep", "name": {"literal": "One"},
                   "previous": {"literal": "Initial"}}],
                 [FIX], STRESS_KPIS, seed=10.0)
    out = _build(folder, spec)
    evidence = "\n".join([out.get("log") or "", out.get("stderr") or "",
                          out.get("refused_at_generation") or ""])
    problems = []
    if "NAME_REPLACED" not in evidence:
        problems.append(
            "a replacement got through with an unreadable name: %s"
            % evidence[-600:])
    if out.get("inp_written"):
        problems.append("the input file was written anyway")
    return {
        "id": "steps_a_replacement_is_caught_at_run_time_too",
        "status": "pass" if not problems else "fail",
        "log_line": _line(out, "NAME_REPLACED"),
        "note": "two dispatched steps of the same name. The host-side check "
                "compares conditions, so this goes straight past it; the "
                "runtime gate asks the model instead and needs to know nothing "
                "about what a step is.",
        "problems": problems,
    }


def check_output_variables(work: Path) -> dict:
    """The field output request used to be a literal, and it blocked a physics."""
    spec = _spec({"name": "Steel", "E": E, "nu": NU, "density": RHO,
                  "conductivity": 45.0, "specific_heat": 5.0e8},
                 [{"call": "HeatTransferStep", "name": {"literal": "One"},
                   "previous": {"literal": "Initial"},
                   "response": "STEADY_STATE", "amplitude": "RAMP"}],
                 [{"call": "TemperatureBC", "name": {"literal": "Cold"},
                   "createStepName": {"literal": "One"},
                   "region": {"set": "Bar:face@z=min", "name": "COLD",
                              "expect": "=1"}, "magnitude": 0.0},
                  {"call": "TemperatureBC", "name": {"literal": "Hot"},
                   "createStepName": {"literal": "One"},
                   "region": {"set": "Bar:face@z=max", "name": "HOT",
                              "expect": "=1"}, "magnitude": 100.0}],
                 [{"name": "NT", "type": "field_max",
                   "location": "whole_model", "invariant": "MISES"}],
                 outputs_extra={"field_variables": ["NT", "HFL"]},
                 element="DC3D8", seed=10.0)
    folder = work / "thermal_outputs"
    out = _build(folder, spec)
    problems = []
    if not out.get("inp_written"):
        problems.append("stated outputs still did not build: %s"
                        % (out.get("stderr") or "")[-400:])

    # And the control: the same spec with the default variables, which is what
    # every spec used to get.
    default_spec = copy.deepcopy(spec)
    default_spec["outputs"].pop("field_variables")
    control = _build(work / "thermal_outputs_default", default_spec)
    if control.get("inp_written"):
        problems.append(
            "the default variables built a heat transfer deck too, so this "
            "item is not testing what it claims")

    solved = None
    if out.get("inp_written"):
        subprocess.run(
            [get_abaqus_cmd(), "job=%s" % MODEL, "interactive",
             "ask_delete=OFF"],
            cwd=str(folder), capture_output=True, text=True, errors="replace",
            encoding="utf-8", stdin=subprocess.DEVNULL, timeout=3600)
        sta = folder / ("%s.sta" % MODEL)
        solved = "COMPLETED SUCCESSFULLY" in (
            sta.read_text(encoding="utf-8", errors="replace")
            if sta.exists() else "")
        if not solved:
            problems.append("the heat transfer job did not complete")
    return {
        "id": "outputs_a_heat_transfer_analysis_can_ask_for_its_own_variables",
        "status": "pass" if not problems else "fail",
        "stated": ["NT", "HFL"],
        "built_with_stated_variables": out.get("inp_written"),
        "built_with_the_old_default": control.get("inp_written"),
        "job_completed": solved,
        "why_the_default_fails": [
            ln.strip() for ln in (control.get("stderr") or "").splitlines()
            if "Invalid variables" in ln][:1],
        "note": "same spec, one key different. S, E and RF do not exist in a "
                "heat transfer step, so Abaqus refuses the whole request and "
                "writes no input file -- which is why this was not a missing "
                "convenience but a physics that could not be built.",
        "problems": problems,
    }


def check_kernel_crash(work: Path) -> dict:
    """A crash inside Abaqus must not be reported as a modelling problem."""
    spec = _spec({"name": "Steel", "E": E, "nu": NU, "density": RHO},
                 STATIC,
                 [FIX,
                  {"call": "FluidPipeSection", "name": {"literal": "Boom"},
                   "createStepName": {"literal": "One"},
                   "region": {"set": "Bar:face@z=max", "name": "PIPE",
                              "expect": "=1"}}],
                 STRESS_KPIS, seed=10.0)
    result = _solve(spec, work / "kernel_crash")
    error = result.get("error") or {}
    message = "%s %s" % (error.get("message", ""), error.get("log_snippet", ""))
    problems = []
    if result.get("status") == "COMPLETED":
        problems.append("the kernel crash produced a COMPLETED run")
    if "EXCEPTION_ACCESS_VIOLATION" not in message:
        problems.append("the report does not mention the kernel crash: %r"
                        % message[:400])
    if "PIPE" not in message and "condition 2" not in message:
        problems.append("the report does not say which condition it died on: "
                        "%r" % message[:400])
    return {
        "id": "diagnostics_a_kernel_crash_says_so",
        "status": "pass" if not problems else "fail",
        "reported_message": error.get("message"),
        "reported_snippet": error.get("log_snippet"),
        "note": "FluidPipeSection with a step-scoped region takes ABQcaeK.exe "
                "down with EXCEPTION_ACCESS_VIOLATION. No Python exception is "
                "raised, so no gate in the deck can catch it, and the launcher "
                "returns 0 as always. This used to be reported as '.inp not "
                "generated, check the log' with an empty snippet and a "
                "suggestion to simplify the geometry.",
        "problems": problems,
    }


def check_dispatch_target(work: Path) -> dict:
    """`target:` must reach the object it names, or say it cannot.

    `target` sits in _generic_call's reserved tuple, and three of the five
    dispatch paths passed their target as a hard-coded string. So on a condition,
    on a step and on a part feature the key was read by nothing and dropped
    without a word: `target: "banana"` generated a clean deck that solved.

    Both halves are checked. The refusal, and the redirect actually working --
    a load created in step One and changed by setValuesInStep in step Two, which
    is a call on the LOAD and was unreachable from a spec until the target was
    honoured here.
    """
    mat = {"name": "Steel", "E": E, "nu": NU, "density": RHO}
    two_steps = [{"call": "StaticStep", "name": {"literal": "One"},
                  "previous": {"literal": "Initial"}},
                 {"call": "StaticStep", "name": {"literal": "Two"},
                  "previous": {"literal": "One"}}]

    nonsense = dict(FIX)
    nonsense["target"] = "banana"
    refused = _build(work / "target_nonsense",
                     _spec(mat, STATIC, [nonsense], STRESS_KPIS, seed=10.0))
    unbound = dict(FIX)
    unbound["target"] = {"ref": "nothing_bound_this"}
    refused_ref = _build(work / "target_unbound",
                         _spec(mat, STATIC, [unbound], STRESS_KPIS, seed=10.0))

    load = dict(TIP_FORCE)
    load["as"] = "tip"
    halved = TIP_LOAD / 2.0
    redirect = _solve(
        _spec(mat, two_steps,
              [FIX, load,
               {"call": "setValuesInStep", "target": {"ref": "tip"},
                "stepName": {"literal": "Two"},
                "magnitude": halved / (W * H)}],
              STRESS_KPIS, seed=10.0),
        work / "target_redirect")

    tip = _kpi(redirect, "U_TIP")
    wanted = halved * L ** 3 / (3.0 * E * INERTIA)
    problems = []
    for label, out in (("target: banana", refused),
                       ("target: {ref: unbound}", refused_ref)):
        if not out.get("refused_at_generation"):
            problems.append("%s was accepted, and the deck it wrote says "
                            "nothing about it" % label)
    if redirect.get("status") != "COMPLETED":
        problems.append("the redirect run: status %s -- %s"
                        % (redirect.get("status"),
                           str(redirect.get("error"))[:200]))
    elif tip is None:
        problems.append("no U_TIP from the redirect run")
    elif abs(abs(tip) - wanted) / wanted > 0.06:
        problems.append(
            "setValuesInStep did not reach the load: the last frame reads %r "
            "where halving the traction gives %r. Unchanged would be %r."
            % (tip, -wanted, -(TIP_LOAD * L ** 3 / (3.0 * E * INERTIA))))
    return {
        "id": "dispatch_a_target_reaches_the_object_it_names",
        "status": "pass" if not problems else "fail",
        "banana_refusal": (refused.get("refused_at_generation") or "")[:220],
        "unbound_refusal": (refused_ref.get("refused_at_generation") or "")[:220],
        "step_two_tip": tip,
        "beam_theory_step_two_tip": -wanted,
        "beam_theory_if_unchanged": -(TIP_LOAD * L ** 3 / (3.0 * E * INERTIA)),
        "note": "the seven methods a load or BC exposes -- setValuesInStep, "
                "deactivate, suppress, move, reset, resume, setValues -- are "
                "calls on the object, not on the model, so no spec could reach "
                "them while the condition path hard-coded `m` as its target.",
        "problems": problems,
    }


def check_attr_only_target(work: Path) -> dict:
    """`target: {attr:}` with no `ref:`, which is the only route to keywordBlock.

    `m.keywordBlock` is not the result of any call, so nothing can bind it with
    `as:` and no `{ref:}` can name it. Until `target:` accepted an `attr:` on
    its own, a card this dialect has no name for could not be written at all --
    and that is the escape hatch the whole generic layer leans on for anything
    Abaqus can express and CAE's Python API cannot reach directly.

    `insert(position, text)` puts the text AFTER block `position` of
    keywordBlock.sieBlocks, so the integer decides everything. For this rig the
    block list runs (dumped from the real model, artifacts/probe_keyword_block
    /blocks/blocks.txt):

        1 *Part   2 *Node   3 *Element   ...   19 *Material   20 *Density
        21 *Elastic   22 **   23 *Boundary   25 *Step

    Four builds:

      1. insert(21), the end of *Elastic, so the card lands inside the material
         where a *Damping card belongs. The card must be in the input file
         Abaqus wrote -- and that file must survive the input file processor,
         because being present in the text is exactly the weak claim this item
         used to make.
      2. insert(3), the middle of the generated *Element table. Same card, same
         spec, one integer apart, and CAE wraps the edit in a *Conflicts block:
         4 FATAL ERRORS, EXECUTION IS TERMINATED. The build used to report
         success and the read-back used to log KEYWORD_OK over it. This is the
         verified counterexample, and it must now be refused.
      3. insert(100000), where a keyword insert was expected to fail SILENTLY
         and measurably does not: Abaqus raises IndexError and the build stops.
         Recorded because it is the opposite of the assumption this truth layer
         was written on.
      4. build 1's script with the insert line knocked out and the read-back
         left in, so the check faces a deck that genuinely lacks the card it
         was told to expect. No spec produces that situation, so it is made by
         hand -- a check that has never once said no proves only that it can
         say yes.
    """
    mat = {"name": "Steel", "E": E, "nu": NU, "density": RHO}
    card = "*Damping, alpha=0.5"
    sync = {"call": "synchVersions", "target": {"attr": "keywordBlock"},
            "storeNodesAndElements": {"bool": False}}

    def insert(position, text=card):
        return {"call": "insert", "target": {"attr": "keywordBlock"},
                "position": position, "text": text}

    def build(name, position, edit=None):
        return _build(work / name,
                      _spec(mat, STATIC, [FIX, sync, insert(position)],
                            STRESS_KPIS, seed=10.0), edit=edit)

    def drop_the_insert(text):
        keep = [line for line in text.splitlines()
                if not (line.startswith("_gcall(m.keywordBlock")
                        and "'insert'" in line)]
        return "\n".join(keep) + "\n"

    good = build("kw_good", 21)
    conflict = build("kw_conflict", 3)
    far = build("kw_far", 100000)
    blind = build("kw_blind", 21, edit=drop_the_insert)

    needle = " ".join(card.split()).upper()
    deck = " ".join((good.get("inp") or "").split()).upper()
    in_deck = needle in deck
    accepted = _datacheck_errors(work / "kw_good")

    problems = []
    if not good.get("inp_written"):
        problems.append("the keyword build wrote no input file: %s"
                        % str(good.get("refused_at_generation")
                              or good.get("stderr"))[:300])
    elif not in_deck:
        problems.append(
            "the build completed and the card is not in the deck, which is "
            "the case _expect_keywords exists for -- so it did not fire either")
    elif accepted.get("errors"):
        problems.append(
            "the card is in the deck and the input file processor refused the "
            "deck with %d error(s) %s -- the escape hatch has to deliver a "
            "model that runs, not text in a file"
            % (accepted["errors"], accepted.get("fatal") or ""))
    if "KEYWORD_OK" not in (good.get("log") or ""):
        problems.append("no KEYWORD_OK line, so the read-back never ran")

    if "KEYWORD_CONFLICT_BLOCK" not in (conflict.get("log") or ""):
        problems.append(
            "insert(3) landed in the generated *Element table and was not "
            "refused. Measured on this release that deck carries a *Conflicts "
            "wrapper and dies with 4 FATAL ERRORS, so a build that reports "
            "success here is the silent failure this item exists for.")
    elif conflict.get("inp_written"):
        problems.append(
            "the conflict build was refused and left its input file behind, so "
            "a caller that tests for the file reads a refused build as good")

    if far.get("inp_written"):
        problems.append(
            "an insert at position 100000 wrote a deck. Measured before this "
            "item was written, it raises IndexError -- if that changed, the "
            "silent-failure reasoning behind the read-back needs remeasuring.")

    if not blind.get("script_edited"):
        problems.append(
            "the negative control edited nothing, so it ran the same script as "
            "build 1 and proves nothing about the check")
    elif "KEYWORD_NOT_WRITTEN" not in (blind.get("log") or ""):
        problems.append(
            "the insert line was removed and the read-back did not refuse, so "
            "the check cannot say no and its PASS above means nothing")
    elif blind.get("inp_written"):
        problems.append(
            "the read-back refused and left the input file behind, so a caller "
            "that tests for the file reads a refused build as a good one")

    return {
        "id": "dispatch_attr_alone_reaches_the_keyword_block",
        "status": "pass" if not problems else "fail",
        "card": card,
        "card_in_written_deck": in_deck,
        "deck_input_processor_errors": accepted.get("errors"),
        "conflict_block_refused":
            "KEYWORD_CONFLICT_BLOCK" in (conflict.get("log") or ""),
        "out_of_range_aborted": not far.get("inp_written"),
        "refused_when_the_card_is_absent":
            "KEYWORD_NOT_WRITTEN" in (blind.get("log") or ""),
        "note": "the same card and the same spec, one integer apart: after "
                "block 21 (*Elastic) the deck datachecks clean, after block 3 "
                "(inside the generated *Element table) CAE wraps it in "
                "*Conflicts and Abaqus reports 4 FATAL ERRORS. Both used to "
                "log KEYWORD_OK and report success.",
        "problems": problems,
    }


def check_attr_only_reaches_engineering_features(work: Path) -> dict:
    """The other member the attr-only route was written for, on the real thing.

    `a.engineeringFeatures` is where seams, cracks and pressure penetration
    live, and like `keywordBlock` it is returned by nothing, so `as:` cannot
    bind it and `{ref:}` cannot name it. A hermetic test proves the generator
    EMITS `_gcall(a.engineeringFeatures, ...)`, which is a claim about text;
    this asks Abaqus.

    THE EVIDENCE CHANGED WITH #76, AND IT GOT STRONGER. It used to be Abaqus's
    own complaint about the ARGUMENT -- `assignSeam` handed the tuple a
    `{select:}` compiles to answers `regions; found tuple, expecting Set`,
    which only an object that has the method can say. That was the best proof
    available while nothing on this object could be called successfully from a
    spec. Now a `ContourIntegral` dispatched the same way RUNS: GENERIC_OK and
    an input file, with the crack front built as an assembly Set and reused by
    `{named_set:}`. A call that returns is better evidence than a call that
    complains.

    The refusal half stays, because one call here is still refused and its
    REASON was rewritten in #76. It is not that the form is unavailable -- the
    set gets built now. It is WRONGLY TIMED: measured in #70, a seam assigned
    after `generateMesh` leaves the node count exactly as it was and raises
    nothing, and assembly operations run after `generateMesh` while part
    features run before it. Whether Abaqus would accept an assembly set for
    this argument is deliberately not claimed either way; both answers make the
    route wrong. The message has to say the timing, and this item checks it
    because the advice has been wrong three times already.
    """
    mat = {"name": "Steel", "E": E, "nu": NU, "density": RHO}
    part = {"name": "Beam",
            "features": [{"op": "sketch", "id": "o", "plane": "XY",
                          "profile": {"rect": {"corner1": [0.0, 0.0],
                                               "corner2": [W, H]}}},
                         {"op": "extrude", "sketch": "o", "depth": L},
                         {"call": "DatumPlaneByPrincipalPlane", "as": "mid",
                          "principalPlane": "XYPLANE", "offset": L / 2.0},
                         {"call": "PartitionCellByDatumPlane",
                          "datumPlane": {"datum": "mid"},
                          "cells": {"select": "cell@all"}}],
            "expect": {"volume": W * H * L, "cells": 2},
            "section": {"type": "solid", "material": "Steel"},
            "mesh": {"seed": 10.0, "element": "C3D8I",
                     "technique": "structured"}}

    def spec_with(operation):
        out = _spec(mat, STATIC, [FIX], STRESS_KPIS, seed=10.0)
        out["parts"] = [part]
        out["assembly"]["operations"] = [operation]
        return out

    face = "Bar:face@z=%g" % (L / 2.0)
    # A crack on the partition face of a cantilever is not a meaningful crack
    # and no J is read off it -- run_crack_check.py is where the number gets
    # measured against a handbook. What this build shows is narrower and is the
    # point of the item: the attr-only route lands on the real
    # `a.engineeringFeatures` and the method returns.
    ran = _build(work / "contour_integral", spec_with({
        "call": "ContourIntegral", "target": {"attr": "engineeringFeatures"},
        "name": {"literal": "Crack"}, "symmetric": "OFF",
        "crackFront": {"set": face, "name": "CFRONT", "expect": "=1"},
        "crackTip": {"named_set": "CFRONT"},
        "extensionDirectionMethod": "Q_VECTORS",
        "qVectors": [[[0.0, 0.0, L / 2.0], [0.0, 0.0, L / 2.0 + 1.0]]]}))
    try:
        build_v2.generate_script(spec_with(
            {"call": "assignSeam", "target": {"attr": "engineeringFeatures"},
             "regions": {"set": face, "name": "SEAMFACE", "expect": "=1"}}))
        set_refusal = ""
    except Exception as exc:
        set_refusal = "%s: %s" % (type(exc).__name__, exc)

    reached = _line(ran, "ContourIntegral")
    problems = []
    if "GENERIC_OK" not in reached and "GENERIC_RETRIED" not in reached:
        problems.append(
            "ContourIntegral did not report success through the attr-only "
            "route; the log line was %r. Without it this item does not show "
            "the call reached the object -- an attribute resolving to nothing "
            "raises AttributeError before the argument is ever looked at."
            % (reached or "(absent)"))
    if not ran.get("inp_written"):
        problems.append(
            "the ContourIntegral build wrote no input file, so the call "
            "landing is not the whole story: something after it stopped the "
            "build. refused_at_generation=%r"
            % (ran.get("refused_at_generation") or "(none)"))
    if not _line(ran, "NAMED_SET_OK"):
        problems.append(
            "no NAMED_SET_OK line, so `crackTip: {named_set: CFRONT}` did not "
            "reuse the assembly set the crack front built -- and that pair is "
            "the form the shipped crack recipe uses.")
    # The advice here has been wrong THREE times and this is the fourth
    # wording. First: "put it in a condition" -- a condition dispatches against
    # the model, which has no engineeringFeatures, so it sent the reader to an
    # AttributeError. Then: a refusal naming the attribute and calling the gap
    # known, honest and still a dead end. Then #70's, "an assembly operation
    # cannot build a Set", which was true of this generator and never of
    # Abaqus, and #76 made it false outright. The reason is timing, so that is
    # what is required here, together with the route out.
    if "PART" not in set_refusal or "generateMesh" not in set_refusal:
        problems.append(
            "the assembly `assignSeam` refusal does not send the reader to the "
            "part route and say why: %r. Measured, a seam assigned after "
            "generateMesh changes nothing and part features are what run "
            "before it; a refusal without both halves is most of a bug report "
            "and none of a fix." % set_refusal[:300])
    for stale in ("known gap", "cannot build one", "cannot build a Set"):
        if stale in set_refusal:
            problems.append(
                "the refusal still says %r. That reason stopped being true in "
                "#76 -- an assembly operation CAN build a set now, and this "
                "call is refused for its timing instead. A message giving a "
                "reason that is no longer the reason sends the reader after "
                "the wrong workaround: %r" % (stale, set_refusal[:300]))

    return {
        "id": "dispatch_attr_alone_reaches_engineering_features",
        "status": "pass" if not problems else "fail",
        "reached_line": reached,
        "set_form_refusal": set_refusal[:300],
        "note": "the route is proven by a ContourIntegral that RUNS through "
                "`{attr: engineeringFeatures}` on the assembly, with the crack "
                "front built as an assembly Set and reused by `{named_set:}`. "
                "No J is read here -- run_crack_check.py measures the number "
                "on a real crack. The other half is the one call on this "
                "object still refused, `assignSeam`, and what is pinned is "
                "that its message gives the reason that is actually true "
                "(timing) and routes to the part.",
        "problems": problems,
    }


def check_mixed_step_forms(work: Path) -> dict:
    """A named step written after a dispatched one has to chain onto it.

    The named form takes its `previous` from the step before it. That variable
    only advanced in the named branch, so after a dispatched step it was still
    'Initial' -- and a step whose previous is Initial is inserted FIRST. Not
    solved wrong: _expect_steps catches the order at run time. But a legitimate
    spec that fails at the solver is still a defect, and the message it failed
    with named nothing the author had written.
    """
    mat = {"name": "Steel", "E": E, "nu": NU, "density": RHO}
    steps = [{"call": "StaticStep", "name": {"literal": "One"},
              "previous": {"literal": "Initial"}},
             {"name": "Two", "loads": [], "bcs": []}]
    out = _build(work / "mixed_steps",
                 _spec(mat, steps, [FIX], STRESS_KPIS, seed=10.0))

    deck = (work / "mixed_steps" / "build_model_script.py")
    text = deck.read_text(encoding="utf-8", errors="replace") if deck.exists() else ""
    inp = out.get("inp") or ""
    order = [ln.split(":", 1)[0].strip().lstrip("*").strip()
             for ln in inp.splitlines() if ln.startswith("*Step")]
    problems = []
    if out.get("refused_at_generation"):
        problems.append("refused at generation: %s"
                        % out["refused_at_generation"])
    elif not out.get("inp_written"):
        problems.append("no input file: %s" % _line(out, "GENERIC_FAILED"))
    else:
        if "previous='One'" not in text:
            problems.append("the named step did not chain onto the dispatched "
                            "one; the deck says %r"
                            % [ln.strip() for ln in text.splitlines()
                               if "previous=" in ln][:2])
        if "STEP_ORDER_OK" not in (out.get("log") or ""):
            problems.append("the step-order gate did not pass: %r"
                            % _line(out, "STEP_ORDER"))
    return {
        "id": "steps_a_named_step_chains_onto_a_dispatched_one",
        "status": "pass" if not problems else "fail",
        "step_cards_in_order": order,
        "step_order_line": _line(out, "STEP_ORDER"),
        "note": "the two step forms have to be mixable, because the dispatched "
                "form is how anything other than StaticStep gets written and "
                "the named form is what every shipped case still uses.",
        "problems": problems,
    }


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=ROOT / "artifacts" / "dropped_input_check"
                    / "report.json")
    ap.add_argument("--work", type=Path, default=None)
    args = ap.parse_args()

    work = args.work or (ROOT / "artifacts" / "dropped_input_check")
    work.mkdir(parents=True, exist_ok=True)
    started = time.time()

    names = ("material_declared_plasticity_reaches_the_model",
             "material_an_unbuildable_key_is_refused_not_dropped",
             "material_thermal_properties_reach_the_model",
             "conditions_a_reused_name_is_refused",
             "steps_a_replacement_is_caught_at_run_time_too",
             "outputs_a_heat_transfer_analysis_can_ask_for_its_own_variables",
             "diagnostics_a_kernel_crash_says_so",
             "dispatch_a_target_reaches_the_object_it_names",
             "dispatch_attr_alone_reaches_the_keyword_block",
             "dispatch_attr_alone_reaches_engineering_features",
             "steps_a_named_step_chains_onto_a_dispatched_one")

    if not check_abaqus():
        reason = ("Abaqus not found (set ABAQUS_AGENT_ABAQUS_CMD or put "
                  "abaqus.bat on PATH)")
        items = [_skipped(name, reason) for name in names]
        release = None
    else:
        release = detect_abaqus_release()
        items = [check_plasticity(work), check_unbuildable_key(work),
                 check_thermal_properties(work), check_reused_name(work),
                 check_reused_name_at_runtime(work),
                 check_output_variables(work), check_kernel_crash(work),
                 check_dispatch_target(work), check_attr_only_target(work),
                 check_attr_only_reaches_engineering_features(work),
                 check_mixed_step_forms(work)]

    failed = [i for i in items if i["status"] == "fail"]
    report = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "abaqus_release": release,
        "seconds": round(time.time() - started, 1),
        "rig": {"declared_yield": YIELD, "elastic_peak_mpa": ELASTIC_PEAK,
                "tip_load_n": TIP_LOAD},
        "overall": "fail" if failed else "pass",
        "items": items,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
