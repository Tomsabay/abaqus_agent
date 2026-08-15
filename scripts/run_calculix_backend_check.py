#!/usr/bin/env python3
"""Real-solver check for the CalculiX fallback backend.

This is the gate that promotes anything in the CalculiX capability matrix
(core/backends.py) from "refused" to "supported": no feature ships enabled
without a passing item here. pytest stays hermetic and never invokes a solver.

Items:

  1. ``calculix_cantilever_e2e`` — drives cases/cantilever/spec.yaml through
     CalculiXOrchestrator end to end (pure-Python mesh -> flat .inp -> ccx ->
     .dat/.frd -> KPIs) with Abaqus forced out of the picture, and compares
     U_tip against the frozen Abaqus 2021 baseline
     -0.0019039579201489687 mm (cases/cantilever/expected.json, run
     dd6ec1145b8de62f). Pass = deviation < 5 %.
  2. ``calculix_mises_definition_gap`` — records the nodal-averaged Mises the
     same run produces. This is NOT graded against Abaqus (the definitions
     differ); it is a regression guard so a future ccx upgrade that changes the
     averaging is caught rather than absorbed.
  3. ``calculix_refuses_unsupported`` — a spec asking for something CalculiX
     cannot do faithfully (blast/CONWEP) must be REFUSED with a plain-language
     reason and produce zero KPIs.
  4. ``calculix_refuses_custom_inp_modal`` — the capability matrix reads
     ``analysis.step_type`` off the SPEC, but for ``geometry.type: custom_inp``
     the deck is the model and ``analysis:`` is optional, so a *FREQUENCY deck
     used to be graded as a static run: ccx solved it, exited 0, dropped
     nothing, and the pipeline reported a mass-normalised eigenvector component
     as a tip displacement. The deck-side gate must refuse it by card name.
  5. ``calculix_custom_inp_static_e2e`` — the counterexample to item 4: the
     same deck with its original ``*STATIC`` must still run end to end and land
     on the Abaqus baseline. A refusal with no verified door beside it would
     leave ``custom_inp`` enabled-but-unverified either way.

Nothing is written inside the repository: everything runs under %TEMP%.
Exit codes: 0 = nothing failed (missing ccx => "skipped", still 0);
            1 = at least one item ran and failed.
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from core.backends import BACKEND_CALCULIX, check_calculix, select_backend  # noqa: E402
from tools.ccx_cmd import detect_ccx_version  # noqa: E402

REFERENCE_U_TIP_MM = -0.0019039579201489687
U_TIP_TOLERANCE_REL = 0.05
# Measured on ccx 2.23 with the pure-Python mesh; see the module docstring.
REFERENCE_MISES_NODAL_AVG = 0.6108512433035294
MISES_TOLERANCE_REL = 0.02


def _skipped(item_id: str, reason: str, **extra: object) -> dict:
    out = {"id": item_id, "status": "skipped", "reason": reason}
    out.update(extra)
    return out


def _load_cantilever_spec() -> dict:
    return yaml.safe_load((ROOT / "cases" / "cantilever" / "spec.yaml").read_text(encoding="utf-8"))


def _run_ccx(spec: dict, workdir: Path, expected_path: Path | None = None) -> dict:
    """Drive the CalculiX orchestrator directly, with Abaqus explicitly out."""
    from agent.orchestrator import build_orchestrator

    decision = select_backend(
        spec,
        abaqus_available=False,       # the point of the fallback
        calculix_available=True,
        override=BACKEND_CALCULIX,
    )
    orch = build_orchestrator(
        decision=decision,
        spec_dict=copy.deepcopy(spec),
        workdir=workdir,
        expected_path=expected_path,
        runner_cfg={"timeout_seconds": 900},
    )
    return orch.run()


def check_cantilever(work_dir: Path) -> tuple[dict, dict]:
    if not check_calculix():
        reason = "CalculiX ccx not found (set ABAQUS_AGENT_CCX_EXE or put ccx on PATH)"
        return _skipped("calculix_cantilever_e2e", reason), _skipped(
            "calculix_mises_definition_gap", reason
        )

    run_dir = work_dir / "cantilever"
    run_dir.mkdir(parents=True, exist_ok=True)
    spec = _load_cantilever_spec()
    started = time.time()
    result = _run_ccx(spec, run_dir, ROOT / "cases" / "cantilever" / "expected.json")
    elapsed = time.time() - started

    kpis = result.get("kpis", {})
    provenance = result.get("kpi_provenance", {})
    u_tip = kpis.get("U_tip")
    mises = kpis.get("MISES_MAX")

    problems: list[str] = []
    if result.get("status") != "COMPLETED":
        problems.append("orchestrator status %s (expected COMPLETED): %s"
                        % (result.get("status"), result.get("error")))
    rel_dev = None
    if u_tip is None:
        problems.append("U_tip missing from KPIs")
    else:
        rel_dev = abs(u_tip - REFERENCE_U_TIP_MM) / abs(REFERENCE_U_TIP_MM)
        if rel_dev >= U_TIP_TOLERANCE_REL:
            problems.append("U_tip deviation %.4f%% >= %.1f%%"
                            % (rel_dev * 100, U_TIP_TOLERANCE_REL * 100))
    if provenance.get("U_tip", {}).get("abaqus_equivalent") is not True:
        problems.append("U_tip should be tagged Abaqus-equivalent")
    if provenance.get("MISES_MAX", {}).get("abaqus_equivalent") is not False:
        problems.append("MISES_MAX must be tagged NOT Abaqus-equivalent")
    comparisons = result.get("regression", {}).get("comparisons", {})
    if comparisons.get("MISES_MAX", {}).get("status") != "NOT_COMPARABLE":
        problems.append("MISES_MAX must not receive a PASS/FAIL verdict")
    if comparisons.get("U_tip", {}).get("status") != "PASS":
        problems.append("U_tip should be graded and PASS against the Abaqus baseline")
    if result.get("regression", {}).get("passed") is not True:
        problems.append("excluding a definition-mismatched KPI must not fail the run")

    e2e = {
        "id": "calculix_cantilever_e2e",
        "status": "pass" if not problems else "fail",
        "ccx_version": detect_ccx_version(),
        "spec": "cases/cantilever/spec.yaml",
        "workdir": str(result.get("stages", {}).get("build_model", {}).get("workdir", run_dir)),
        "elapsed_s": round(elapsed, 2),
        "orchestrator_status": result.get("status"),
        "backend": result.get("backend", {}).get("label"),
        "measured_u_tip_mm": u_tip,
        "reference_u_tip_mm": REFERENCE_U_TIP_MM,
        "relative_deviation": None if rel_dev is None else round(rel_dev, 10),
        "tolerance_relative": U_TIP_TOLERANCE_REL,
        "kpis": kpis,
        "kpi_provenance": provenance,
        "regression": comparisons,
        "problems": problems,
    }

    mises_problems: list[str] = []
    mises_dev = None
    if mises is None:
        mises_problems.append("MISES_MAX missing from KPIs")
    else:
        mises_dev = abs(mises - REFERENCE_MISES_NODAL_AVG) / REFERENCE_MISES_NODAL_AVG
        if mises_dev >= MISES_TOLERANCE_REL:
            mises_problems.append(
                "nodal-averaged Mises drifted %.4f%% from the recorded ccx value"
                % (mises_dev * 100)
            )
    gap = {
        "id": "calculix_mises_definition_gap",
        "status": "pass" if not mises_problems else "fail",
        "note": "NOT an Abaqus comparison: ccx .frd stress is nodal-averaged, "
                "Abaqus ELEMENT_NODAL is unaveraged. Recorded so a ccx upgrade "
                "that changes the averaging is visible.",
        "measured_mises_nodal_averaged": mises,
        "recorded_ccx_value": REFERENCE_MISES_NODAL_AVG,
        "abaqus_element_nodal_value": 0.6528551578521729,
        "gap_vs_abaqus_pct": None if mises is None else round(
            (mises - 0.6528551578521729) / 0.6528551578521729 * 100, 3),
        "problems": mises_problems,
    }
    return e2e, gap


def check_refusal(work_dir: Path) -> dict:
    if not check_calculix():
        return _skipped("calculix_refuses_unsupported", "CalculiX ccx not found")

    run_dir = work_dir / "refusal"
    run_dir.mkdir(parents=True, exist_ok=True)
    spec = _load_cantilever_spec()
    spec["bc_load"]["load_type"] = "blast_conwep"
    spec["bc_load"]["blast_tnt_kg"] = 1.0
    spec["bc_load"]["blast_standoff_mm"] = 500.0
    spec["analysis"]["step_type"] = "Dynamic_Explicit"

    result = _run_ccx(spec, run_dir)
    reasons = result.get("error", {}).get("refusals", [])
    problems: list[str] = []
    if result.get("status") != "REFUSED":
        problems.append("status %s (expected REFUSED)" % result.get("status"))
    if result.get("kpis"):
        problems.append("a refused run must produce no KPIs, got %s" % list(result["kpis"]))
    if not any("CONWEP" in r for r in reasons):
        problems.append("no plain-language reason naming the blast load")
    return {
        "id": "calculix_refuses_unsupported",
        "status": "pass" if not problems else "fail",
        "spec_change": "bc_load.load_type=blast_conwep + analysis.step_type=Dynamic_Explicit",
        "orchestrator_status": result.get("status"),
        "refusals": reasons,
        "kpis": result.get("kpis", {}),
        "problems": problems,
    }


def _write_flat_deck(dest_dir: Path) -> Path:
    """The deck the two custom_inp items below feed back in as a user's own.

    Generated from cases/cantilever with this project's own writer rather than
    read off disk, so this gate stays self-contained: it must run on a clone
    that carries no course materials.
    """
    from runner.ccx_deck import write_ccx_deck

    spec = _load_cantilever_spec()
    kpi_spec = (spec.get("outputs", {}) or {}).get("kpis", []) or []
    inp_path, _ = write_ccx_deck(spec, dest_dir, kpi_spec)
    return inp_path


def _custom_inp_spec(inp_path: Path, model_name: str) -> dict:
    """A custom_inp spec that describes a static run, whatever the deck says.

    `analysis.step_type: Static` is the honest thing for a custom_inp author to
    write — the spec has no field that could describe the deck's procedure, and
    the validator requires the block. That is exactly the bypass: the capability
    matrix grades this spec, concludes Static, and never sees the card the deck
    actually runs. Only the deck-side gate can.
    """
    return {
        "meta": {"abaqus_release": "2021", "model_name": model_name,
                 "units": "mm_MPa_t", "description": "custom_inp gate item"},
        "geometry": {"type": "custom_inp", "inp_path": str(inp_path)},
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
        "analysis": {"solver": "standard", "step_type": "Static", "cpus": 1},
        "bc_load": {"fixed_face": "FIXED_END", "load_type": "concentrated_force",
                    "value": 10.0, "direction": 2},
        "outputs": {"kpis": [
            {"name": "U_tip", "type": "nodal_displacement",
             "location": "TIP_NODES", "component": "U2"},
        ]},
    }


def check_custom_inp_modal_refused(work_dir: Path) -> dict:
    """The wall: a deck whose procedure the matrix would refuse must not solve."""
    if not check_calculix():
        return _skipped("calculix_refuses_custom_inp_modal", "CalculiX ccx not found")

    run_dir = work_dir / "custom_inp_modal"
    run_dir.mkdir(parents=True, exist_ok=True)
    source = _write_flat_deck(run_dir / "source")
    deck = source.read_text(encoding="utf-8")
    modal_deck = deck.replace("*STATIC", "*FREQUENCY\n6, 0., , , , ", 1)
    if modal_deck == deck:
        return {"id": "calculix_refuses_custom_inp_modal", "status": "fail",
                "problems": ["the generated deck no longer contains *STATIC, so "
                             "this item is not measuring what it claims"]}
    modal_path = run_dir / "ModalFromStatic.inp"
    modal_path.write_text(modal_deck, encoding="utf-8")

    result = _run_ccx(_custom_inp_spec(modal_path, "ModalFromStatic"), run_dir)
    error = result.get("error", {}) or {}
    message = error.get("message", "") or ""
    reasons = error.get("refusals", []) or ([message] if message else [])

    problems: list[str] = []
    if result.get("status") != "REFUSED":
        problems.append("status %s (expected REFUSED): the deck asks for "
                        "*FREQUENCY and ccx will happily solve it, exit 0 and "
                        "drop nothing" % result.get("status"))
    if result.get("kpis"):
        problems.append("a refused run must produce no KPIs, got %s" % list(result["kpis"]))
    if not any("*FREQUENCY" in r for r in reasons):
        problems.append("no reason naming the offending card: %s" % reasons)
    if not any("基准" in r for r in reasons):
        problems.append("the refusal must say it is an unverified-baseline "
                        "refusal, not 'CalculiX cannot do this'")
    return {
        "id": "calculix_refuses_custom_inp_modal",
        "status": "pass" if not problems else "fail",
        "deck": "the deck this project generates for cases/cantilever, with "
                "*STATIC replaced by *FREQUENCY (one card, nothing else)",
        "spec_shape": "geometry.type=custom_inp, no analysis: block at all",
        "orchestrator_status": result.get("status"),
        "error_code": error.get("error_code"),
        "refusals": reasons,
        "kpis": result.get("kpis", {}),
        "problems": problems,
    }


def check_custom_inp_static_e2e(work_dir: Path) -> dict:
    """The door: the same deck, unmodified, must still run end to end."""
    if not check_calculix():
        return _skipped("calculix_custom_inp_static_e2e", "CalculiX ccx not found")

    run_dir = work_dir / "custom_inp_static"
    run_dir.mkdir(parents=True, exist_ok=True)
    static_path = _write_flat_deck(run_dir / "source")

    started = time.time()
    result = _run_ccx(_custom_inp_spec(static_path, "StaticAsShipped"), run_dir)
    elapsed = time.time() - started

    kpis = result.get("kpis", {})
    u_tip = kpis.get("U_tip")
    problems: list[str] = []
    if result.get("status") != "COMPLETED":
        problems.append("status %s (expected COMPLETED): the procedure gate "
                        "must refuse a procedure, not custom_inp itself — %s"
                        % (result.get("status"), result.get("error")))
    rel_dev = None
    if u_tip is None:
        problems.append("U_tip missing: %s" % (result.get("kpi_errors") or result.get("error")))
    else:
        rel_dev = abs(u_tip - REFERENCE_U_TIP_MM) / abs(REFERENCE_U_TIP_MM)
        if rel_dev >= U_TIP_TOLERANCE_REL:
            problems.append("U_tip deviation %.4f%% >= %.1f%%"
                            % (rel_dev * 100, U_TIP_TOLERANCE_REL * 100))
    return {
        "id": "calculix_custom_inp_static_e2e",
        "status": "pass" if not problems else "fail",
        "deck": "the same generated deck, unmodified",
        "note": "the counterexample to the item above: without this, a passing "
                "refusal proves nothing except that the gate can say no",
        "elapsed_s": round(elapsed, 2),
        "orchestrator_status": result.get("status"),
        "measured_u_tip_mm": u_tip,
        "reference_u_tip_mm": REFERENCE_U_TIP_MM,
        "relative_deviation": None if rel_dev is None else round(rel_dev, 10),
        "kpis": kpis,
        "problems": problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Real CalculiX backend check.")
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(argv)

    if args.work_dir is not None:
        work_dir = args.work_dir
        work_dir.mkdir(parents=True, exist_ok=True)
        keep = True
    else:
        work_dir = Path(tempfile.mkdtemp(prefix="ccx_backend_check_"))
        keep = args.keep

    e2e, gap = check_cantilever(work_dir)
    items = [
        e2e,
        gap,
        check_refusal(work_dir),
        check_custom_inp_modal_refused(work_dir),
        check_custom_inp_static_e2e(work_dir),
    ]

    statuses = [item["status"] for item in items]
    if "fail" in statuses:
        overall = "fail"
    elif all(s == "skipped" for s in statuses):
        overall = "skipped"
    elif "skipped" in statuses:
        overall = "partial"
    else:
        overall = "pass"

    failed = overall == "fail"
    if not keep and not failed and work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)

    report = {
        "schema": "calculix_backend_check/1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "ccx_version": detect_ccx_version(),
        "work_dir": str(work_dir),
        "work_dir_kept": keep or failed,
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
