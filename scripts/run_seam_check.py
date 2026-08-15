#!/usr/bin/env python3
"""Real-solver check for seams: does one do anything, and is it caught when it
doesn't?

The acceptance criterion for this was written down before any of it was built,
in the ledger, as a guard against exactly the kind of claim this project keeps
having to retract: ANY CLAIM THAT A SEAM TOOK EFFECT MUST SHOW A NODE COUNT
THAT MOVED. Everything below is that sentence turned into items.

Two things were unknown and both were measured first (artifacts/probe_seam2).

WHERE THE BLOCKER WAS. #64 stopped at "engineeringFeatures.assignSeam requires
a Set and an assembly operation cannot build one". The hope was that the PART
route sidestepped it. It does not: `p.engineeringFeatures.assignSeam` answers a
raw sequence with the same complaint, `regions; found GeomSequence, expecting
Set`. What was actually missing was a PART set -- a different object from an
assembly set, which `{set:}` refused to build because it assumed sets live on
the assembly.

Part scope also turned out to be the right scope rather than a workable one.
Part features run before `generateMesh`, so a seam written there is assigned to
an unmeshed part; assigned afterwards it takes effect only if something
remeshes, which is the silent shape the ledger flagged as unmeasured.

AND THE FAILURE THAT HAS NO EXCEPTION. On one 10 x 10 x 10 block partitioned at
mid-height, meshed at seed 5:

    no seam                    27 nodes
    seam on the INTERIOR face  36 nodes
    seam on the top face       27 nodes   <- returned, no error
    seam on the bottom face    27 nodes   <- returned, no error

A face not shared by two cells cannot be separated and Abaqus does not say so.
So `expect.seams` is mandatory on any part that assigns one, and item 4 is the
counterexample that proves the check can say no.

Exit codes: 0 = nothing failed (no Abaqus => "skipped", still 0);
            1 = at least one item ran and failed.
"""

from __future__ import annotations

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

MODEL = "SeamCheck"
SIDE = 10.0
SEED = 5.0
# Measured on this rig, and the numbers the whole gate turns on.
NODES_PLAIN = 27
NODES_SEAMED = 36
SEAM_POSITIONS = 9        # the 3 x 3 grid on the mid-height face


def _part(seam: dict | None, expect_seams=None) -> dict:
    """The block, optionally with a seam on the face `seam` names."""
    features = [
        {"op": "sketch", "id": "o", "plane": "XY",
         "profile": {"rect": {"corner1": [0.0, 0.0],
                              "corner2": [SIDE, SIDE]}}},
        {"op": "extrude", "sketch": "o", "depth": SIDE},
        {"call": "DatumPlaneByPrincipalPlane", "principalPlane": "XYPLANE",
         "offset": SIDE / 2.0, "as": "mid"},
        {"call": "PartitionCellByDatumPlane", "datumPlane": {"datum": "mid"},
         "cells": {"select": "cell@all"}},
    ]
    expect = {"volume": SIDE ** 3, "cells": 2}
    if seam is not None:
        features.append(seam)
    if expect_seams is not None:
        expect["seams"] = expect_seams
    return {"name": "Blk", "features": features, "expect": expect,
            "section": {"type": "solid", "material": "Steel"},
            "mesh": {"seed": SEED, "element": "C3D8I",
                     "technique": "structured"}}


def _seam(selector: str, region_form: str = "set") -> dict:
    region = {region_form: selector, "expect": "=1"}
    if region_form == "set":
        region["name"] = "SEAMFACE"
    return {"call": "assignSeam", "target": {"attr": "engineeringFeatures"},
            "regions": region}


def _spec(part: dict) -> dict:
    return {
        "meta": {"abaqus_release": "2021", "model_name": MODEL,
                 "units": "mm_MPa_t"},
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3,
                     "density": 7.85e-9},
        "parts": [part],
        "assembly": {"instances": [{"name": "B", "part": "Blk",
                                    "translate": [0.0, 0.0, 0.0]}]},
        "steps": [{"call": "StaticStep", "name": {"literal": "One"},
                   "previous": {"literal": "Initial"}}],
        "conditions": [
            {"call": "EncastreBC", "name": {"literal": "Fix"},
             "createStepName": {"literal": "Initial"},
             "region": {"set": "B:face@z=min", "name": "FIX",
                        "expect": "=1"}}],
        "outputs": {"kpis": [{"name": "U", "type": "field_min",
                              "location": "whole_model", "component": "U2"}]},
    }


# --- plumbing --------------------------------------------------------------

def _fresh(work: Path) -> Path:
    import shutil

    work = work.resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    return work


def _build(work: Path, spec: dict) -> dict:
    """Generate and run the CAE script; report the deck rather than the rc."""
    work = _fresh(work)
    try:
        text = build_v2.generate_script(spec)
    except Exception as exc:
        return {"log": "", "inp_written": False, "script": "",
                "deck_nodes": None,
                "refused_at_generation": "%s: %s" % (type(exc).__name__, exc)}
    (work / "build_model_script.py").write_text(text, encoding="utf-8")
    proc = subprocess.run(
        [get_abaqus_cmd(), "cae", "noGUI=build_model_script.py", "--",
         str(work), "spec"],
        cwd=str(work), stdin=subprocess.DEVNULL, capture_output=True,
        text=True, errors="replace", encoding="utf-8", timeout=1800)
    log = work / "selectors.log"
    inp = work / ("%s.inp" % MODEL)
    deck_nodes = None
    if inp.exists():
        deck = inp.read_text(encoding="utf-8", errors="replace")
        if "*Node" in deck and "*Element" in deck:
            block = deck.split("*Node", 1)[1].split("*Element", 1)[0]
            deck_nodes = len([ln for ln in block.splitlines()
                              if ln.strip() and "," in ln])
    return {"log": log.read_text(encoding="utf-8", errors="replace")
            if log.exists() else "",
            "script": text,
            "inp_written": inp.exists(),
            "deck_nodes": deck_nodes,
            "stderr": (proc.stderr or "")[-1500:],
            "refused_at_generation": None}


def _line(out: dict, needle: str) -> str:
    for line in (out.get("log") or "").splitlines():
        if needle in line:
            return line.strip()
    return ""


def _skipped(item_id: str, reason: str) -> dict:
    return {"id": item_id, "status": "skipped", "reason": reason}


# --- items -----------------------------------------------------------------

def check_seam_moves_the_node_count(work: Path) -> dict:
    """The criterion, unchanged from the day it was written down.

    Both decks come out of the same run, so the comparison is not against a
    number somebody remembered.
    """
    plain = _build(work / "plain", _spec(_part(None)))
    seamed = _build(work / "seamed", _spec(
        _part(_seam("face@z=5"),
              expect_seams=[{"set": "SEAMFACE",
                             "duplicated": SEAM_POSITIONS}])))

    problems = []
    if not plain.get("inp_written"):
        problems.append("the control deck was not written: %s"
                        % str(plain.get("refused_at_generation")
                              or plain.get("stderr"))[:250])
    elif plain.get("deck_nodes") != NODES_PLAIN:
        problems.append(
            "the control deck has %s nodes, expected %d. The rig moved, so "
            "the comparison below is not the one this item was written for."
            % (plain.get("deck_nodes"), NODES_PLAIN))
    if not seamed.get("inp_written"):
        problems.append("the seamed deck was not written: %s"
                        % str(seamed.get("refused_at_generation")
                              or seamed.get("stderr"))[:250])
    elif seamed.get("deck_nodes") != NODES_SEAMED:
        problems.append(
            "the seamed deck has %s nodes, expected %d. A seam duplicates the "
            "nodes along it; if the count did not move, the seam is decoration"
            % (seamed.get("deck_nodes"), NODES_SEAMED))
    seam_line = _line(seamed, "SEAM_OK")
    if not seam_line:
        problems.append("no SEAM_OK line, so nothing checked the seam")

    return {
        "id": "a_seam_duplicates_the_nodes_along_it",
        "status": "pass" if not problems else "fail",
        "plain_deck_nodes": plain.get("deck_nodes"),
        "seamed_deck_nodes": seamed.get("deck_nodes"),
        "seam_line": seam_line,
        "note": "the two decks come from the same run. The seam adds %d "
                "nodes, one per position on the 3 x 3 mid-height face, and "
                "the count is read out of the written .inp rather than out of "
                "the kernel." % (NODES_SEAMED - NODES_PLAIN),
        "problems": problems,
    }


def check_a_seam_on_the_wrong_face_is_caught(work: Path) -> dict:
    """The counterexample, and the reason expect.seams is mandatory.

    Measured: assignSeam on the top face returns without an exception and the
    node count does not move. Without a check, that is a model with no crack
    in it that builds, solves and reports success.
    """
    out = _build(work / "wrong_face", _spec(
        _part(_seam("face@z=max"),
              expect_seams=[{"set": "SEAMFACE",
                             "duplicated": SEAM_POSITIONS}])))
    refusal = _line(out, "SEAM_NOT_SEPARATED")
    problems = []
    if out.get("inp_written"):
        problems.append(
            "a seam on an exterior face wrote a deck with %s nodes. Abaqus "
            "accepted the call and changed nothing, so this side is the only "
            "thing between that and a crack model with no crack in it"
            % out.get("deck_nodes"))
    if not refusal:
        problems.append("nothing in the log says SEAM_NOT_SEPARATED")
    elif "found 0" not in refusal:
        problems.append(
            "the refusal does not report how many positions were actually "
            "duplicated, which is the number that says what went wrong: %r"
            % refusal)
    return {
        "id": "a_seam_that_separates_nothing_is_refused",
        "status": "pass" if not problems else "fail",
        "refusal_line": refusal,
        "note": "assignSeam on a face that is not shared by two cells is "
                "accepted and does nothing. Nothing raises; the node count is "
                "the only witness.",
        "problems": problems,
    }


def check_a_seam_without_an_expect_is_refused(work: Path) -> dict:
    """Mandatory, on the same reasoning imports use.

    An import has to state volume or cells because a hollow shell looks like a
    solid; a seam has to state `duplicated` because a seam that did nothing
    looks like a seam that worked.
    """
    out = _build(work / "no_expect", _spec(_part(_seam("face@z=5"))))
    message = str(out.get("refused_at_generation") or "")
    problems = []
    if out.get("inp_written"):
        problems.append("a part assigning a seam with no expect.seams built")
    if "expect.seams" not in message:
        problems.append("the refusal does not name the key to write: %r"
                        % message[:250])
    if "27 nodes before and 27 after" not in message:
        problems.append(
            "the refusal does not carry the measurement, so it reads as a "
            "rule rather than as a reason: %r" % message[:250])
    return {
        "id": "a_seam_with_nothing_stated_is_refused_at_generation",
        "status": "pass" if not problems else "fail",
        "refusal": message[:300],
        "note": "before Abaqus starts, and the message carries the "
                "measurement that makes the rule make sense.",
        "problems": problems,
    }


def check_the_seam_needs_a_set(work: Path) -> dict:
    """The #64 boundary, measured again from the part side.

    `{select:}` produces a GeomSequence, and assignSeam refuses one -- on the
    part exactly as on the assembly. This pins that the refusal is Abaqus's own
    complaint about the argument rather than something invented here, which is
    also the evidence that the call was reached.
    """
    out = _build(work / "raw_sequence", _spec(
        _part(_seam("face@z=5", region_form="select"),
              expect_seams=[{"set": "SEAMFACE",
                             "duplicated": SEAM_POSITIONS}])))
    message = str(out.get("refused_at_generation") or "")
    problems = []
    if out.get("inp_written"):
        problems.append("assignSeam took a raw sequence and built a deck")
    if "expecting Set" not in message:
        problems.append(
            "the refusal does not carry Abaqus's own complaint, which is what "
            "shows the call reaches the real object: %r" % message[:250])
    return {
        "id": "a_seam_given_a_raw_sequence_is_refused",
        "status": "pass" if not problems else "fail",
        "refusal": message[:300],
        "note": "measured on the part as well as the assembly: `regions; "
                "found GeomSequence, expecting Set`. A part Set is what was "
                "missing, and it is what this task added.",
        "problems": problems,
    }


def check_the_seam_is_assigned_before_the_mesh() -> dict:
    """Order, which is the half of this the ledger flagged as unmeasured.

    A seam assigned after generateMesh only takes effect if something remeshes
    -- measured, 27 nodes until a second generateMesh() and 36 after. Part
    features run before the mesh, so writing a seam there removes the question
    rather than answering it, and this pins that the emitted order is that one.
    """
    # Generated, not run: this is a claim about what the generator emits, and
    # item 1 has already put the identical spec through Abaqus. Spending
    # another CAE start to re-read a string would buy nothing.
    lines = build_v2.generate_script(_spec(
        _part(_seam("face@z=5"),
              expect_seams=[{"set": "SEAMFACE",
                             "duplicated": SEAM_POSITIONS}]))).splitlines()
    problems = []
    # Each needle carries enough punctuation to hit the emitted call and not
    # the helper's own def or the prose about it. Counted rather than found,
    # because a needle that matched a docstring would let this item pass on
    # the ordering of two comments.
    where = {}
    for label, needle in (("seam", "'assignSeam'"),
                          ("mesh", "p.generateMesh()"),
                          ("check", "_expect_seam(p, '")):
        hits = [i for i, line in enumerate(lines) if needle in line]
        if len(hits) != 1:
            problems.append("%r appears %d times in the generated script, so "
                            "the order below would be read off the wrong line"
                            % (needle, len(hits)))
        where[label] = hits[0] if hits else -1
    seam_at, mesh_at, check_at = where["seam"], where["mesh"], where["check"]
    if not problems:
        if not seam_at < mesh_at:
            problems.append(
                "the seam is assigned after generateMesh, which measured "
                "leaves the node count untouched until something remeshes")
        if not mesh_at < check_at:
            problems.append(
                "the seam is checked before the mesh exists, and a seam has "
                "nothing to show before there is a mesh to show it in")
    return {
        "id": "the_seam_is_assigned_before_the_mesh_and_checked_after",
        "status": "pass" if not problems else "fail",
        "note": "assignSeam -> generateMesh -> _expect_seam. Writing the seam "
                "as a part feature is what puts it on the right side of the "
                "mesh; as an assembly operation it would land on the wrong one.",
        "problems": problems,
    }


def check_an_assembly_seam_points_somewhere(work: Path) -> dict:
    """The old dead end, now with an exit.

    Before this task an assembly-operation seam was refused with "this is a
    known gap". It is not a gap any more, so the refusal has to say where to
    go instead -- a no with no next step is most of a bug report and none of a
    fix.
    """
    spec = _spec(_part(None))
    spec["assembly"]["operations"] = [
        {"call": "assignSeam", "target": {"attr": "engineeringFeatures"},
         "regions": {"set": "B:face@z=5", "name": "SEAMFACE", "expect": "=1"}}]
    out = _build(work / "assembly_seam", spec)
    message = str(out.get("refused_at_generation") or "")
    problems = []
    if out.get("inp_written"):
        problems.append("an assembly-operation seam built a deck")
    if "PART" not in message:
        problems.append("the refusal does not point at the part route: %r"
                        % message[:250])
    # The WHY is timing, and since the #76 rewording the message states it
    # in measured terms ("a seam assigned AFTER `generateMesh` leaves the
    # node count exactly as it was"), not as the old "before the mesh"
    # phrase. Anchor on the word the measurement hangs on.
    if "generateMesh" not in message:
        problems.append(
            "the refusal does not say WHY the part is the right place, which "
            "is the part a reader needs to not try again: %r" % message[:250])
    if "features:" not in message:
        problems.append(
            "the refusal names no destination -- a no with no next step: %r"
            % message[:250])
    return {
        "id": "an_assembly_seam_is_refused_with_somewhere_to_go",
        "status": "pass" if not problems else "fail",
        "refusal": message[:300],
        "note": "the message changed from `known gap` to a route, because "
                "the gap closed.",
        "problems": problems,
    }


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=ROOT / "artifacts" / "seam_check" / "report.json")
    ap.add_argument("--work", type=Path, default=None)
    args = ap.parse_args()

    work = args.work or (ROOT / "artifacts" / "seam_check")
    work.mkdir(parents=True, exist_ok=True)
    started = time.time()

    names = ("a_seam_duplicates_the_nodes_along_it",
             "a_seam_that_separates_nothing_is_refused",
             "a_seam_with_nothing_stated_is_refused_at_generation",
             "a_seam_given_a_raw_sequence_is_refused",
             "the_seam_is_assigned_before_the_mesh_and_checked_after",
             "an_assembly_seam_is_refused_with_somewhere_to_go")

    release = None
    if not check_abaqus():
        reason = ("Abaqus not found (set ABAQUS_AGENT_ABAQUS_CMD or put "
                  "abaqus.bat on PATH)")
        items = [_skipped(name, reason) for name in names]
    else:
        release = detect_abaqus_release()
        items = [check_seam_moves_the_node_count(work),
                 check_a_seam_on_the_wrong_face_is_caught(work),
                 check_a_seam_without_an_expect_is_refused(work),
                 check_the_seam_needs_a_set(work),
                 check_the_seam_is_assigned_before_the_mesh(),
                 check_an_assembly_seam_points_somewhere(work)]

    failed = [i for i in items if i["status"] == "fail"]
    report = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "abaqus_release": release,
        "seconds": round(time.time() - started, 1),
        "rig": {"nodes_plain": NODES_PLAIN, "nodes_seamed": NODES_SEAMED,
                "seam_positions": SEAM_POSITIONS},
        "overall": "fail" if failed else "pass",
        "items": items,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
