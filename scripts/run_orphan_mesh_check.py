#!/usr/bin/env python3
"""Real-solver check for a part read from a deck: `node@` and `element@`.

#65 imported STEP, IGES and SAT and stopped at orphan meshes with a note
saying the real gap was somewhere else. It was, and it was not where the note
guessed either. Everything below was measured first (artifacts/probe_orphan).

WHAT AN ORPHAN PART IS. `m.PartFromInputFile` on a deck holding one meshed bar
returns 189 nodes, 80 elements and **0 cells, 0 faces, 0 edges, 0 vertices**.
Every selector this dialect had resolves against `p.faces` or `p.cells`, so
every one of them matched an empty sequence -- and `Set(name=..., faces=<empty>)`
is accepted in silence, which is the failure the selector layer exists for. The
import also DROPS the sets and surfaces the source deck carried (3 `*Nset`,
4 `*Elset`, 1 `*Surface` in, `sets: []` and `surfaces: []` out), so the names
in the file cannot be leaned on either.

SO `node@` AND `element@` -- BUT NOT SYMMETRICALLY. A node is a point and the
plane form is exact: `node@z=min` matched the 9 on the root plane. An element
is a VOLUME, and `getByBoundingBox` on elements means wholly inside: the
tolerance band this dialect emits (span x 1e-6) matched **0 of 80**, while a
band one element thick matched the 4 of that layer. A plane never cuts an
element, so `element@<axis>=` is refused at generation with that measurement,
and `element@all` is what an orphan part actually needs -- the element set the
section is assigned to.

AND TWO SILENT ZEROS. `getVolume()` on an orphan part returns **0.0 without
raising**, exactly as the IGES shell does. And the section path every other
part takes is `p.Set(name='ALL', cells=p.cells)`: measured, on a part with no
cells that builds a set holding 0 cells and then assigns a section to 0 cells,
neither raising. So an import must state what came back -- volume/cells for a
shape, mesh.nodes/mesh.elements for a mesh -- and which pair is stated is also
what tells this layer which kind of part it is.

Rig: a 10 x 10 x 100 bar, C3D8I at seed 5, meshed and written out by CAE, then
read back through `parts[].import` and solved. Beam theory P L^3 / 3EI =
0.190476 mm.

Exit codes: 0 = nothing failed (no Abaqus => "skipped", still 0);
            1 = at least one item ran and failed.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.helpers import check_abaqus            # noqa: E402
from runner import build_v2                      # noqa: E402
from tools.abaqus_cmd import (                   # noqa: E402
    detect_abaqus_release, get_abaqus_cmd)

MODEL = "OrphanMeshCheck"
W = H = 10.0
L = 100.0
E, NU, RHO = 210000.0, 0.3, 7.85e-9
SEED = 5.0
TIP_LOAD = 100.0
BEAM_TIP = TIP_LOAD * L ** 3 / (3.0 * E * (W * H ** 3 / 12.0))   # 0.190476...
BAND = 0.05
# Measured on this rig, and what the whole gate is anchored to.
NODES = 189
ELEMENTS = 80
PLANE_NODES = 9           # the 3 x 3 grid on an end face
TRUE_VOLUME = W * H * L   # what the bar WOULD measure if it had geometry


_EXPORT = '''# -*- coding: utf-8 -*-
"""Write the source decks the import items read back.

One deck with a single meshed bar, and one with two bars in it -- the second
exists only so the "a spec names one part" refusal has something real to
refuse. Sets and a surface go into the first on purpose: the import drops
them, and an item asserts that it does.
"""
import json
from abaqus import *
from abaqusConstants import *
import part, mesh, regionToolset

W, H, L, SEED = %(w)r, %(h)r, %(l)r, %(seed)r
OUT = {}


def deck(job_name, part_names):
    m = mdb.Model(name='Src_' + job_name)
    mm = m.Material(name='Steel')
    mm.Elastic(table=((%(e)r, %(nu)r),))
    mm.Density(table=((%(rho)r,),))
    m.HomogeneousSolidSection(name='Sec', material='Steel', thickness=None)
    a = m.rootAssembly
    a.DatumCsysByDefault(CARTESIAN)
    for nm in part_names:
        s = m.ConstrainedSketch(name='s' + nm, sheetSize=400.0)
        s.rectangle(point1=(0.0, 0.0), point2=(W, H))
        p = m.Part(name=nm, dimensionality=THREE_D, type=DEFORMABLE_BODY)
        p.BaseSolidExtrude(sketch=s, depth=L)
        p.setElementType(regions=(p.cells,), elemTypes=(
            mesh.ElemType(elemCode=C3D8I, elemLibrary=STANDARD),))
        p.seedPart(size=SEED, deviationFactor=0.1, minSizeFactor=0.1)
        p.generateMesh()
        p.SectionAssignment(region=regionToolset.Region(cells=p.cells),
                            sectionName='Sec')
        p.Set(name='ROOT', faces=p.faces.getByBoundingBox(zMin=-1e-6, zMax=1e-6))
        p.Set(name='ALLCELLS', cells=p.cells)
        p.Surface(name='TOPFACE',
                  side1Faces=p.faces.getByBoundingBox(zMin=L - 1e-6))
        a.Instance(name=nm, part=p, dependent=ON)
        OUT[nm] = {'nodes': len(p.nodes), 'elements': len(p.elements)}
    m.StaticStep(name='One', previous='Initial')
    j = mdb.Job(name=job_name, model=m.name)
    j.writeInput(consistencyChecking=OFF)
    text = open(job_name + '.inp').read()
    OUT[job_name] = {'Nset': text.count('*Nset'), 'Elset': text.count('*Elset'),
                     'Surface': text.count('*Surface')}


deck('one_bar', ['Bar'])
deck('two_bars', ['Alpha', 'Beta'])

f = open('exported.json', 'w')
json.dump(OUT, f, indent=2)
f.close()
'''


# --- plumbing --------------------------------------------------------------

def _fresh(work: Path) -> Path:
    work = work.resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    return work


def _export(work: Path) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    (work / "export_bar.py").write_text(
        _EXPORT % {"w": W, "h": H, "l": L, "seed": SEED,
                   "e": E, "nu": NU, "rho": RHO},
        encoding="utf-8")
    proc = subprocess.run(
        [get_abaqus_cmd(), "cae", "noGUI=export_bar.py"],
        cwd=str(work), stdin=subprocess.DEVNULL, capture_output=True,
        text=True, errors="replace", encoding="utf-8", timeout=1800)
    written = work / "exported.json"
    if not written.exists():
        return {"ok": False, "stderr": (proc.stderr or "")[-1500:]}
    out = json.loads(written.read_text(encoding="utf-8"))
    out["ok"] = True
    return out


def _part(deck_name: str = "one_bar.inp", expect=None) -> dict:
    return {
        "name": "Bar",
        "import": {"part": {"call": "PartFromInputFile",
                            "inputFileName": {"file": deck_name}}},
        "expect": expect if expect is not None
        else {"mesh": {"nodes": NODES, "elements": ELEMENTS}},
        "section": {"type": "solid", "material": "Steel"},
    }


def _spec(part: dict, conditions=None) -> dict:
    return {
        "meta": {"abaqus_release": "2021", "model_name": MODEL,
                 "units": "mm_MPa_t"},
        "material": {"name": "Steel", "E": E, "nu": NU, "density": RHO},
        "parts": [part],
        "assembly": {"instances": [{"name": "B", "part": "Bar",
                                    "translate": [0.0, 0.0, 0.0]}]},
        "steps": [{"call": "StaticStep", "name": {"literal": "One"},
                   "previous": {"literal": "Initial"}}],
        "conditions": conditions if conditions is not None else [
            {"call": "EncastreBC", "name": {"literal": "Fix"},
             "createStepName": {"literal": "Initial"},
             "region": {"set": "B:nodes@z=min", "name": "ROOTN",
                        "expect": "=%d" % PLANE_NODES}},
            {"call": "ConcentratedForce", "name": {"literal": "Tip"},
             "createStepName": {"literal": "One"},
             "region": {"set": "B:nodes@z=max", "name": "TIPN",
                        "expect": "=%d" % PLANE_NODES},
             # The load is written PER NODE, so the spec divides and says so.
             "expect": {"points": PLANE_NODES},
             "cf2": -TIP_LOAD / PLANE_NODES,
             "distributionType": "UNIFORM", "localCsys": None}],
        "outputs": {"kpis": [{"name": "U_TIP", "type": "field_min",
                              "location": "whole_model", "component": "U2"}]},
    }


def _build(work: Path, spec: dict, source: Path) -> dict:
    """Generate and run, with the source deck beside the spec it names."""
    work = _fresh(work)
    for deck in ("one_bar.inp", "two_bars.inp"):
        if (source / deck).exists():
            shutil.copy(str(source / deck), str(work / deck))
    try:
        text = build_v2.generate_script(spec, spec_dir=str(work))
    except Exception as exc:
        return {"log": "", "inp_written": False, "script": "",
                "refused_at_generation": "%s: %s" % (type(exc).__name__, exc)}
    (work / "build_model_script.py").write_text(text, encoding="utf-8")
    proc = subprocess.run(
        [get_abaqus_cmd(), "cae", "noGUI=build_model_script.py", "--",
         str(work), "spec"],
        cwd=str(work), stdin=subprocess.DEVNULL, capture_output=True,
        text=True, errors="replace", encoding="utf-8", timeout=1800)
    log = work / "selectors.log"
    inp = work / ("%s.inp" % MODEL)
    return {"log": log.read_text(encoding="utf-8", errors="replace")
            if log.exists() else "",
            "script": text,
            "inp": inp.read_text(encoding="utf-8", errors="replace")
            if inp.exists() else "",
            "inp_written": inp.exists(),
            "stderr": (proc.stderr or "")[-2000:],
            "refused_at_generation": None}


def _solve(spec: dict, work: Path, source: Path) -> dict:
    from agent.orchestrator import build_orchestrator

    _fresh(work)
    for deck in ("one_bar.inp", "two_bars.inp"):
        if (source / deck).exists():
            shutil.copy(str(source / deck), str(work / deck))
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


def _log_line(work: Path, needle: str) -> str:
    log = work / "selectors.log"
    if not log.exists():
        return ""
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if needle in line:
            return line.strip()
    return ""


def _skipped(item_id: str, reason: str) -> dict:
    return {"id": item_id, "status": "skipped", "reason": reason}


# --- items -----------------------------------------------------------------

def check_the_import_drops_what_the_deck_carried(source: dict) -> dict:
    """Why the names in the file cannot be leaned on.

    The source deck is written with two sets and a surface in it, and this
    reads the counts out of the file rather than asserting them from memory.
    """
    counts = source.get("one_bar") or {}
    problems = []
    if not counts.get("Nset") or not counts.get("Elset") \
            or not counts.get("Surface"):
        problems.append(
            "the source deck does not carry sets and a surface (%r), so the "
            "next item would be showing that nothing was dropped rather than "
            "that something was" % counts)
    return {
        "id": "the_source_deck_carries_sets_and_a_surface",
        "status": "pass" if not problems else "fail",
        "source_deck": counts,
        "note": "measured: the import returns sets: [] and surfaces: [] from "
                "this file, so a selector is the only way back to a region -- "
                "which is what node@ and element@ are for.",
        "problems": problems,
    }


def check_an_imported_mesh_carries_the_load(work: Path, source: Path) -> dict:
    """The end-to-end number, and the only item that proves any of this works.

    Load reaches the bar through node sets built by `nodes@z=max`, and the
    section through the element set `element@all` puts on the part.
    """
    result = _solve(_spec(_part()), work / "solve", source)
    tip = _kpi(result, "U_TIP")
    import_line = _log_line(work / "solve", "IMPORT_OK")
    mesh_line = _log_line(work / "solve", "MESH_OK")
    problems = []
    if str(result.get("status")) != "COMPLETED":
        problems.append("the run did not complete: %r (%s)"
                        % (result.get("status"),
                           str(result.get("error"))[:200]))
    if tip is None:
        problems.append("no U_TIP came back")
    else:
        off = abs(abs(tip) - BEAM_TIP) / BEAM_TIP
        if off > BAND:
            problems.append(
                "tip %.8f against beam theory %.8f is %.1f%% out, outside the "
                "%.0f%% band. The mesh came out of a file, so this is the only "
                "thing that says the file that arrived is a bar"
                % (tip, -BEAM_TIP, off * 100.0, BAND * 100.0))
    if "was BAR" not in import_line:
        problems.append(
            "the import line does not record the name Abaqus gave it: %r"
            % import_line)
    return {
        "id": "an_imported_mesh_takes_a_load_through_node_sets",
        "status": "pass" if not problems else "fail",
        "measured_tip": tip,
        "beam_theory_tip": -BEAM_TIP,
        "import_line": import_line,
        "mesh_line": mesh_line,
        "note": "the load is on a node set from `nodes@z=max` and the section "
                "on an element set, because the part has no faces and no "
                "cells to put either on.",
        "problems": problems,
    }


def check_the_uppercased_name_is_taken_back(work: Path, source: Path) -> dict:
    """`PartFromInputFile` takes no name, and the deck's is upper-cased.

    Measured: `Bar` arrives as `BAR`. Every other line in the generated script
    names the part from the spec, so without the rename the assembly would
    reach for a part that is not there.
    """
    out = _build(work / "name", _spec(_part()), source)
    line = _line(out, "IMPORT_OK")
    problems = []
    if not out.get("inp_written"):
        problems.append("the build did not write a deck: %s"
                        % str(out.get("refused_at_generation")
                              or out.get("stderr"))[:250])
    if "-> Bar (was BAR)" not in line:
        problems.append(
            "the log does not show the rename: %r. Both halves matter -- the "
            "name the spec asked for and the name the file actually produced"
            % line)
    if "*Part, name=Bar" not in (out.get("inp") or ""):
        problems.append(
            "the written deck does not carry the spec's name for the part")
    return {
        "id": "the_name_abaqus_upper_cased_is_taken_back",
        "status": "pass" if not problems else "fail",
        "import_line": line,
        "note": "measured on Abaqus 2021: the method takes no `name` argument "
                "at all, so the part is renamed after the fact with "
                "parts.changeKey.",
        "problems": problems,
    }


def check_a_deck_with_two_parts_is_refused(work: Path, source: Path) -> dict:
    """A spec names one part, and picking one of two would be picking for the
    author."""
    out = _build(work / "two", _spec(_part(deck_name="two_bars.inp")), source)
    refusal = _line(out, "IMPORT_PART_COUNT")
    problems = []
    if out.get("inp_written"):
        problems.append("a two-part deck built a model naming one part")
    if not refusal:
        problems.append("nothing in the log says IMPORT_PART_COUNT")
    elif "ALPHA" not in refusal or "BETA" not in refusal:
        problems.append(
            "the refusal does not name the parts that did arrive, which is "
            "what tells the author what the file holds: %r" % refusal)
    return {
        "id": "a_deck_holding_two_parts_is_refused_by_name",
        "status": "pass" if not problems else "fail",
        "refusal_line": refusal,
        "note": "and both arrive upper-cased, which is why the message lists "
                "them as ALPHA and BETA rather than as Alpha and Beta.",
        "problems": problems,
    }


def check_an_element_plane_selector_is_refused(work: Path, source: Path) -> dict:
    """The asymmetry between node@ and element@, with the measurement.

    A plane is a surface and an element is a volume. Refused at generation, so
    no licence is taken out to find out.
    """
    spec = _spec(_part())
    spec["conditions"][0]["region"] = {"set": "B:element@z=min",
                                       "name": "ROOTE", "expect": "=1"}
    out = _build(work / "element_plane", spec, source)
    message = str(out.get("refused_at_generation") or "")
    problems = []
    if out.get("inp_written"):
        problems.append("an element plane selector built a deck")
    if "wholly inside" not in message:
        problems.append(
            "the refusal does not say WHY a plane cannot cut an element: %r"
            % message[:250])
    if "0 of 80" not in message:
        problems.append(
            "the refusal does not carry the measurement, so it reads as a "
            "rule rather than as a fact: %r" % message[:250])
    if "element@all" not in message or "node@z=min" not in message:
        problems.append(
            "the refusal does not offer the two things that DO work: %r"
            % message[:250])
    return {
        "id": "an_element_on_a_plane_is_refused_with_the_measurement",
        "status": "pass" if not problems else "fail",
        "refusal": message[:400],
        "note": "measured: the emitted tolerance band matched 0 of 80 "
                "elements, a band one element thick matched the 4 of that "
                "layer, and node@z=min matched the 9 on the plane.",
        "problems": problems,
    }


def check_a_volume_claim_on_a_mesh_is_caught(work: Path, source: Path) -> dict:
    """The counterexample the whole expect rule rests on.

    `getVolume()` on an orphan part returns 0.0 WITHOUT RAISING -- the same
    silent zero the IGES shell gives. A spec claiming the bar's real volume
    has to be stopped by the check rather than by an exception, or the rule is
    a rule nobody has seen enforced.
    """
    out = _build(work / "volume_claim",
                 _spec(_part(expect={"volume": TRUE_VOLUME,
                                     "mesh": {"elements": ELEMENTS}})),
                 source)
    refusal = _line(out, "EXPECT_VOLUME")
    problems = []
    if out.get("inp_written"):
        problems.append(
            "an orphan part claiming volume %g built a deck. Measured, "
            "getVolume() answers 0.0 on it without raising, so nothing else "
            "would have caught this" % TRUE_VOLUME)
    if not refusal:
        problems.append("nothing in the log says EXPECT_VOLUME")
    elif "came out at 0.0" not in refusal:
        problems.append(
            "the refusal does not report the measured volume, which is the "
            "whole content of the item -- 0.0 is what Abaqus answers, and it "
            "answers it without raising: %r" % refusal)
    return {
        "id": "a_volume_stated_on_a_mesh_import_aborts",
        "status": "pass" if not problems else "fail",
        "refusal_line": refusal,
        "true_volume": TRUE_VOLUME,
        "note": "the bar really is 10000 mm3 as a shape; read as a mesh it "
                "has no volume at all and Abaqus says 0.0 rather than "
                "objecting.",
        "problems": problems,
    }


def check_a_wrong_node_count_aborts(work: Path, source: Path) -> dict:
    """`expect.mesh.nodes` has to be able to say no, or it says nothing."""
    out = _build(work / "wrong_nodes",
                 _spec(_part(expect={"mesh": {"nodes": NODES + 1,
                                              "elements": ELEMENTS}})),
                 source)
    refusal = _line(out, "MESH_NODES")
    problems = []
    if out.get("inp_written"):
        problems.append("a wrong node count built a deck")
    if not refusal:
        problems.append("nothing in the log says MESH_NODES")
    elif str(NODES) not in refusal:
        problems.append("the refusal does not report the count found: %r"
                        % refusal)
    return {
        "id": "a_wrong_node_count_aborts_the_build",
        "status": "pass" if not problems else "fail",
        "refusal_line": refusal,
        "note": "the element count alone does not pin the mesh: the same 80 "
                "elements are 189 nodes as C3D8 and far more as C3D20.",
        "problems": problems,
    }


def check_the_two_refusals_before_abaqus_starts(work: Path,
                                                source: Path) -> dict:
    """Stated nothing, and a mesh import carrying a `mesh:` block.

    Both are generation-time, so neither costs a licence.
    """
    nothing = _build(work / "no_expect",
                     _spec(_part(expect={"faces": 6})), source)
    seeded = _spec(_part())
    seeded["parts"][0]["mesh"] = {"seed": SEED, "element": "C3D8I"}
    with_mesh = _build(work / "with_mesh_block", seeded, source)

    first = str(nothing.get("refused_at_generation") or "")
    second = str(with_mesh.get("refused_at_generation") or "")
    problems = []
    if nothing.get("inp_written"):
        problems.append("an import stating only `faces` built a deck")
    if "expect.mesh.nodes" not in first:
        problems.append(
            "the refusal does not name the mesh keys, so an author importing "
            "a deck is told only about volume and cells: %r" % first[:250])
    if with_mesh.get("inp_written"):
        problems.append("a mesh import carrying a `mesh:` block built a deck")
    if "nothing to seed" not in second:
        problems.append(
            "the refusal does not say why a mesh import cannot be seeded: %r"
            % second[:250])
    return {
        "id": "an_import_states_what_came_back_and_does_not_seed_it",
        "status": "pass" if not problems else "fail",
        "no_expect_refusal": first[:300],
        "mesh_block_refusal": second[:300],
        "note": "`faces: 6` is the specific trap the geometry half already "
                "measured -- the IGES shell has the same 6 faces the solid "
                "has -- so it is what an author would reach for.",
        "problems": problems,
    }


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=ROOT / "artifacts" / "orphan_mesh_check"
                    / "report.json")
    ap.add_argument("--work", type=Path, default=None)
    args = ap.parse_args()

    work = args.work or (ROOT / "artifacts" / "orphan_mesh_check")
    work.mkdir(parents=True, exist_ok=True)
    started = time.time()

    names = ("the_source_deck_carries_sets_and_a_surface",
             "an_imported_mesh_takes_a_load_through_node_sets",
             "the_name_abaqus_upper_cased_is_taken_back",
             "a_deck_holding_two_parts_is_refused_by_name",
             "an_element_on_a_plane_is_refused_with_the_measurement",
             "a_volume_stated_on_a_mesh_import_aborts",
             "a_wrong_node_count_aborts_the_build",
             "an_import_states_what_came_back_and_does_not_seed_it")

    release = None
    if not check_abaqus():
        reason = ("Abaqus not found (set ABAQUS_AGENT_ABAQUS_CMD or put "
                  "abaqus.bat on PATH)")
        items = [_skipped(name, reason) for name in names]
    else:
        release = detect_abaqus_release()
        source = _fresh(work / "source")
        exported = _export(source)
        if not exported.get("ok"):
            reason = ("the source decks could not be written: %s"
                      % str(exported.get("stderr"))[:300])
            items = [_skipped(name, reason) for name in names]
        else:
            items = [
                check_the_import_drops_what_the_deck_carried(exported),
                check_an_imported_mesh_carries_the_load(work, source),
                check_the_uppercased_name_is_taken_back(work, source),
                check_a_deck_with_two_parts_is_refused(work, source),
                check_an_element_plane_selector_is_refused(work, source),
                check_a_volume_claim_on_a_mesh_is_caught(work, source),
                check_a_wrong_node_count_aborts(work, source),
                check_the_two_refusals_before_abaqus_starts(work, source),
            ]

    failed = [i for i in items if i["status"] == "fail"]
    report = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "abaqus_release": release,
        "seconds": round(time.time() - started, 1),
        "rig": {"nodes": NODES, "elements": ELEMENTS,
                "plane_nodes": PLANE_NODES,
                "beam_theory_tip": -BEAM_TIP},
        "overall": "fail" if failed else "pass",
        "items": items,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
