#!/usr/bin/env python3
"""Run every real-solver verification gate and summarize the evidence.

One command, one verdict. Each gate is a separate process so one failure
cannot poison the others, and every gate is read through the same contract
reader so adding one does not mean teaching this file a new output shape.

Two output contracts exist in the tree and both are honoured, because
rewriting nine working gate scripts to satisfy a summary reader is the tail
wagging the dog:

    {"result": "PASS"}                the five 2026-07 scenario gates
    {"overall": "pass", "items": []}  everything written since

The newer gates print a human-readable item list BEFORE their JSON, so the
payload starts at the first `{` rather than at byte zero. Feeding the whole of
stdout to json.loads -- which is what this file used to do -- judged every one
of them FAIL.

"skipped" is a third verdict, not a failure. A gate that cannot find Abaqus
says so and exits 0; on a machine without a seat the honest overall result is
SKIPPED, and the exit code stays 0. Only a real failure, a crash, or a timeout
sets exit 1 -- a timeout used to raise out of this function and abandon every
gate after it.

Usage:
    .venv/Scripts/python.exe scripts/run_all_real_checks.py
    .venv/Scripts/python.exe scripts/run_all_real_checks.py --only generic_mesh
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (name, script, solver). `solver` is reported, not enforced: a gate decides
# for itself whether it can run and says "skipped" if it cannot.
GATES = [
    # The 2026-07 scenario gates: closed-form answers on whole pipeline runs.
    ("cantilever_tip_theory", "scripts/run_cantilever_real_check.py", "abaqus"),
    ("simple_beam_theory", "scripts/run_simple_beam_real_check.py", "abaqus"),
    ("plate_hole_kt", "scripts/run_plate_hole_real_check.py", "abaqus"),
    ("modal_frequencies", "scripts/run_modal_real_check.py", "abaqus"),
    ("solver_failure_diagnosis", "scripts/run_solver_doctor_real_check.py",
     "abaqus"),
    # The generic-layer gates: what the spec dialect can express, and what it
    # refuses. These are where the engine work of 2026-08 lives.
    ("generic_part", "scripts/run_generic_part_check.py", "abaqus"),
    ("generic_mesh", "scripts/run_generic_mesh_check.py", "abaqus"),
    ("generic_load", "scripts/run_generic_load_check.py", "abaqus"),
    ("generic_interaction", "scripts/run_generic_interaction_check.py",
     "abaqus"),
    ("generic_connector", "scripts/run_generic_connector_check.py", "abaqus"),
    ("mesh_quality", "scripts/run_mesh_quality_check.py", "abaqus"),
    ("dropped_input", "scripts/run_dropped_input_check.py", "abaqus"),
    ("part_grammar", "scripts/run_part_grammar_check.py", "abaqus"),
    ("assembly", "scripts/run_assembly_check.py", "abaqus"),
    ("assembly_position", "scripts/run_assembly_position_check.py", "abaqus"),
    ("geometry_import", "scripts/run_geometry_import_check.py", "abaqus"),
    ("reference_point", "scripts/run_reference_point_check.py", "abaqus"),
    ("job_layer", "scripts/run_job_layer_check.py", "abaqus"),
    ("seam", "scripts/run_seam_check.py", "abaqus"),
    ("orphan_mesh", "scripts/run_orphan_mesh_check.py", "abaqus"),
    ("crack", "scripts/run_crack_check.py", "abaqus"),
    ("material_rebuild", "scripts/run_material_rebuild_check.py",
     "abaqus"),
    # Two small solves that differ by one string in `mesh.element`. It is here
    # because the WARNING has to stay attached to the phenomenon: if a release
    # or a generator change ever fixes the hourglassing, the warning would be
    # describing something that no longer happens, and this fails rather than
    # letting that ship.
    ("hourglass_warning", "scripts/run_hourglass_warning_check.py", "abaqus"),
    # The slowest gate in the list by an order of magnitude: the shipped
    # bearing_block mesh is ~92k deck lines of C3D10 and takes about 23 minutes
    # to solve, which roughly doubles a full harness run. It stays in the
    # default list anyway -- it is the only gate that shows a silent
    # constraint failure with the identities still passing -- and `--only`
    # exists for iteration.
    ("bearing_block", "scripts/run_bearing_block_check.py", "abaqus"),
    ("hallucination_pack", "scripts/run_hallucination_pack_check.py", "abaqus"),
    # The browser surface. Registered here because it had no registry at all,
    # which is how the preview's contact-surface overlay could be computed by
    # the backend and dropped before the wire for months with every gate green:
    # nothing in the harness ever looked at what the workbench actually draws.
    # Starts its own server and skips itself if Chromium is absent, so it costs
    # nothing on a machine that cannot run it.
    ("contact_preview_ui", "scripts/run_contact_preview_ui_check.py", "browser"),
    # Same reason, same blind spot: what the results grid DOES NOT draw. A KPI
    # the spec asked for and the extractor never returned used to leave a grid
    # that was quietly one tile shorter, on a run still reporting COMPLETED.
    ("kpi_missing_ui", "scripts/run_kpi_missing_ui_check.py", "browser"),
    # Written 2026-08 and never registered anywhere -- found while adding the
    # gate above. It is the gate that proves a failed run still shows its
    # error text after you click away and back, and nothing ran it.
    ("diagnosis_ui", "scripts/run_diagnosis_ui_check.py", "browser"),
    # @-mentions (#77): the chip must actually reach the model, and a dangling
    # mention must refuse on send. A chip is one DOM node away from being
    # decoration, which is precisely the failure a hermetic test cannot see.
    ("mention_ui", "scripts/run_mention_ui_check.py", "browser"),
    # Nine gates existed and were never listed here (2026-08-09). The three
    # comments above each record the same discovery one gate at a time; the
    # registry has no way to notice a script nobody added, so
    # tests/test_gate_registry.py now fails when one exists and is unlisted.
    ("assembly_preview_ui", "scripts/run_assembly_preview_check.py", "browser"),
    ("error_gallery", "scripts/run_error_gallery_check.py", "abaqus"),
    ("frontend_coherence", "scripts/run_frontend_coherence_check.py", "browser"),
    ("i18n_ui", "scripts/run_i18n_ui_check.py", "browser"),
    ("version_selector_ui", "scripts/run_version_selector_ui_check.py",
     "browser"),
    ("workbench_browser", "scripts/run_workbench_browser_check.py", "browser"),
    ("workbench_real", "scripts/run_workbench_real_check.py", "abaqus"),
    # Hermetic: no solver, no browser. They are here because a gate nobody
    # runs is a gate that does not exist, and these two are the cheapest in
    # the list -- there is no reason for them to be the ones left out.
    ("i18n_static", "scripts/run_i18n_static_check.py", "static"),
    ("readme_quickstart", "scripts/run_readme_quickstart_check.py", "static"),
    # 3D picking (#78): a click on a body mentions it, a drag does not, and
    # the preview constructor cannot be built without the handler. Real
    # pointer events against a deterministic camera, not synthetic calls.
    ("pick_ui", "scripts/run_pick_ui_check.py", "browser"),
    # Results mesh (#81): a node label is not a key. Nothing here had ever
    # looked at what the RESULTS viewport draws -- contact_preview_ui covers
    # the preview -- and a 3-instance assembly shipped with 63% of its exterior
    # surface deleted while every KPI stayed correct and the banner read
    # COMPLETED.
    ("result_mesh_ui", "scripts/run_result_mesh_ui_check.py", "browser"),
    # Whether a run was graded at all. The verdict layer had no rendering path
    # of its own -- the workbench only read `regression.passed === false` to
    # decide whether to open the diagnosis panel -- so a run with no baseline
    # and a run whose every KPI matched looked identical on screen.
    ("grading_ui", "scripts/run_grading_ui_check.py", "browser"),
]

# Scripts that exist only in the private development tree, and why. Their
# gates stay in GATES because this registry is the one honest list of every
# check that exists; in the public distribution each reports NOT_DISTRIBUTED
# with its reason, instead of an absent file reading as a crash -- or worse,
# the row silently disappearing. Keyed by file name so the registry tests can
# use the same set for the one EXEMPT script that is also private-only.
PRIVATE_ONLY = {
    "run_hallucination_pack_check.py":
        "its sample decks live in course/, not distributed",
    "run_error_gallery_check.py":
        "its six failure captures live in course/, not distributed",
    "run_from_scratch_planner_check.py":
        "drives the local claude CLI login; also EXEMPT from GATES",
}

# PARTIAL means "no item failed, but some were skipped" -- eight gates build
# their overall that way (`elif "skipped" in statuses`). It was on neither
# list: not PASSING, so the harness counted it a failure and went red while the
# gate itself exited 0 saying it was fine, and nobody could tell which of the
# two was authoritative. It joins PASSING, and is counted and reported under
# its own name so that a partial run can never read as a full pass.
PASSING = ("PASS", "SKIPPED", "PARTIAL", "NOT_DISTRIBUTED")


def _payload(stdout: str) -> dict | None:
    """The verdict object a gate printed: the last complete one on stdout.

    Not `json.loads(stdout)`: the newer gates print their item lines first.
    Not "the first `{` that parses to end of input" either, which is what this
    did until 2026-08-09 -- it requires the JSON to be the last byte, and
    run_workbench_browser_check.py prints an `evidence -> <path>` line after
    its payload. That gate was reported as "printed no JSON object", i.e. a
    FAIL, on a run where it printed `"overall": "PASS"`.

    So: decode each object where it starts, ignore whatever follows, and keep
    the last one. Gates that print an interim payload before their verdict
    (run_frontend_coherence_check) then still report the verdict.
    """
    decoder = json.JSONDecoder()
    found = None
    start = stdout.find("{")
    while start >= 0:
        try:
            obj, end = decoder.raw_decode(stdout, start)
        except (json.JSONDecodeError, ValueError):
            start = stdout.find("{", start + 1)
            continue
        if isinstance(obj, dict):
            found = obj
        start = stdout.find("{", max(end, start + 1))
    return found


def _verdict(payload: dict) -> str:
    if "result" in payload:                         # 2026-07 contract
        return str(payload["result"]).upper()
    if "overall" in payload:                        # everything since
        return str(payload["overall"]).upper()
    return "UNREADABLE"


def _interesting(payload: dict) -> dict:
    """The few numbers worth putting in the one-line summary."""
    out = {}
    for key in ("measured_over_theory", "measured_tip_mm", "kt_measured",
                "measured_f1_hz", "solver_doctor_category",
                "kpis_in_workspace", "abaqus_release", "seconds"):
        if key in payload:
            out[key] = payload[key]
    items = payload.get("items")
    if isinstance(items, list) and items:
        out["items"] = {
            "total": len(items),
            "pass": sum(1 for i in items
                        if str(i.get("status", "")).lower() == "pass"),
            "fail": sum(1 for i in items
                        if str(i.get("status", "")).lower() == "fail"),
            "skipped": sum(1 for i in items
                           if str(i.get("status", "")).lower() == "skipped"),
        }
    return out


def _run(name: str, script: str, solver: str, timeout: int) -> dict:
    t0 = time.time()
    detail: dict = {"name": name, "script": script, "solver": solver}
    if not (ROOT / script).is_file():
        detail["seconds"] = 0.0
        reason = PRIVATE_ONLY.get(Path(script).name)
        if reason:
            detail["result"] = "NOT_DISTRIBUTED"
            detail["reason"] = reason
        else:
            detail["result"] = "FAIL"
            detail["reason"] = "GATES names a script that is not in this tree"
        return detail
    try:
        proc = subprocess.run(
            [sys.executable, script],
            cwd=str(ROOT), stdin=subprocess.DEVNULL, capture_output=True,
            text=True, errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        detail["seconds"] = round(time.time() - t0, 1)
        detail["result"] = "FAIL"
        detail["reason"] = ("no verdict after %ds. A gate that hangs is a gate "
                            "that failed; it used to raise out of here and "
                            "abandon every gate after it." % timeout)
        return detail

    detail["seconds"] = round(time.time() - t0, 1)
    payload = _payload(proc.stdout)
    if payload is None:
        detail["result"] = "FAIL"
        detail["reason"] = "printed no JSON object"
        detail["exit_code"] = proc.returncode
        detail["stdout_tail"] = proc.stdout[-400:]
        detail["stderr_tail"] = proc.stderr[-400:]
        return detail

    detail["result"] = _verdict(payload)
    detail.update(_interesting(payload))
    # A gate that says PASS and exits non-zero is not passing. Measured
    # contract: every gate here returns 0 on pass and on skip.
    if detail["result"] in PASSING and proc.returncode != 0:
        detail["result"] = "FAIL"
        detail["reason"] = ("said %s but exited %d"
                            % (payload.get("overall", payload.get("result")),
                               proc.returncode))
    return detail


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", action="append", default=None,
                        help="gate name; repeatable")
    parser.add_argument("--timeout", type=int, default=2400,
                        help="per gate, seconds")
    args = parser.parse_args(argv)

    wanted = [g for g in GATES if not args.only or g[0] in args.only]
    if args.only:
        unknown = set(args.only) - {g[0] for g in GATES}
        if unknown:
            print("unknown gate(s): %s" % ", ".join(sorted(unknown)))
            return 2

    started = time.time()
    gates = []
    for name, script, solver in wanted:
        detail = _run(name, script, solver, args.timeout)
        gates.append(detail)
        print("[gate] %-22s -> %-9s (%.0fs)"
              % (name, detail["result"], detail["seconds"]), flush=True)

    failed = [g for g in gates if g["result"] not in PASSING]
    passed = [g for g in gates if g["result"] == "PASS"]
    partial = [g for g in gates if g["result"] == "PARTIAL"]
    if failed:
        overall = "FAIL"
    elif partial:
        # Not FAIL -- nothing failed -- but not PASS either: some items were
        # skipped, and a run that folds those into "PASS" claims coverage it
        # did not have.
        overall = "PARTIAL"
    elif passed:
        overall = "PASS"
    else:
        overall = "SKIPPED"

    summary = {
        "overall": overall,
        "total_seconds": round(time.time() - started, 1),
        "counts": {"total": len(gates), "pass": len(passed),
                   "partial": len(partial),
                   "skipped": sum(1 for g in gates
                                  if g["result"] == "SKIPPED"),
                   "not_distributed": sum(1 for g in gates
                                          if g["result"] == "NOT_DISTRIBUTED"),
                   "fail": len(failed)},
        "gates": gates,
    }
    out = ROOT / "artifacts" / "real_check_gate_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if overall == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
