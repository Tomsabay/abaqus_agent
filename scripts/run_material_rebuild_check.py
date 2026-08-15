#!/usr/bin/env python3
"""Real-solver check: a rebuilt material is erased, and the way out actually works.

`material:` is a closed key set. Hyperelastic, an anisotropic LAMINA elastic, a
multi-point hardening curve, a temperature-dependent property -- none of them
can be spelled there, so the only route was to re-declare the material in
`model_setup`. That route silently destroys the declaration:

    before   elastic True   plastic True   density True
    after    elastic False  plastic False  density False     nothing raised

Not just the Elastic. The `yield` and the `density` are gone too, which is the
917 MPa failure `_materials` was written to prevent, arriving by a different
door -- and the block order guarantees the rebuild wins.

So the refusal cannot stand alone: closing the only door leaves people with no
way to write the model they came for. The route out is `target: {ref: <name>}`,
which reaches the material object itself, and item 4 below is the one that
matters -- it puts Hyperelastic on a material through the SHIPPED generator and
then reads the model back to confirm the Elastic survived.

Item 6 is the counterexample the runtime layer exists for. The generation-time
refusal knows one method name; a spec that erases a material some other way
gets past it, and the survival check has to catch that with no list at all.

Exit codes: 0 = nothing failed (no Abaqus => "skipped", still 0);
            1 = at least one item ran and failed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.helpers import check_abaqus  # noqa: E402
from runner import build_v2  # noqa: E402
from runner.build_v2 import SpecError  # noqa: E402
from tools.abaqus_cmd import detect_abaqus_release, get_abaqus_cmd  # noqa: E402

BASE = {
    "meta": {"abaqus_release": "2021", "model_name": "MatCheck",
             "units": "mm_MPa_t"},
    "material": {"name": "Steel", "E": 210000.0, "nu": 0.3,
                 "density": 7.85e-09, "yield": 250.0},
    # The op-form, copied from cases/two_plate_tie rather than invented: the
    # generic form's ConstrainedSketch hangs off the MODEL, and a part feature
    # dispatches to the PART, so writing it there fails in the kernel.
    "parts": [{
        "name": "Blk",
        "features": [
            {"op": "sketch", "id": "outline", "plane": "XY",
             "profile": {"rect": {"corner1": [0.0, 0.0],
                                  "corner2": [10.0, 10.0]}}},
            {"op": "extrude", "sketch": "outline", "depth": 10.0},
        ],
        "section": {"type": "solid", "material": "Steel"},
        "mesh": {"seed": 5.0, "element": "C3D8I"},
    }],
    "assembly": {"instances": [{"part": "Blk", "name": "b1"}]},
    # Not "S1": a bare ALL-CAPS value is read as an Abaqus symbolic constant,
    # so the step name compiled to an undefined bare `S1`. Mixed case sidesteps
    # it without needing {literal:}.
    "steps": [{"name": "Load", "call": "StaticStep", "previous": "Initial"}],
    "outputs": {"kpis": [{"name": "U", "type": "nodal_displacement",
                          "location": "whole_model", "component": "U2"}]},
}

# What the kernel is asked to report back, appended to a generated script.
_READBACK = '''

import json as _json
_report = {}
for _n in m.materials.keys():
    _mat = m.materials[_n]
    _report[str(_n)] = {
        'elastic': getattr(_mat, 'elastic', None) is not None,
        'plastic': getattr(_mat, 'plastic', None) is not None,
        'density': getattr(_mat, 'density', None) is not None,
        'hyperelastic': getattr(_mat, 'hyperelastic', None) is not None,
    }
_fh = open(%r, 'w')
_fh.write(_json.dumps(_report))
_fh.close()
print('READBACK_WRITTEN')
'''


def _spec(**extra):
    spec = json.loads(json.dumps(BASE))
    spec.update(extra)
    return spec


def _fresh(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def _run_script(work: Path, name: str, body: str) -> tuple:
    """Run a generated script in the kernel; return (log, readback, deck).

    NOT the return code. `abaqus cae` exits 0 whether the script ran to the end
    or died on its first line -- measured here, a NameError inside the script
    still came back 0. A check reading that code is reading nothing. What says
    the build was stopped is that no deck was written.
    """
    deck = work / ("%s.inp" % BASE["meta"]["model_name"])
    if deck.exists():
        deck.unlink()
    out = work / ("%s_materials.json" % name)
    script = work / ("%s.py" % name)
    script.write_text(body + (_READBACK % str(out.name)), encoding="utf-8")
    # `-- <workdir> spec` is the contract every generated script's header
    # reads; without it the script chdirs to the literal string '-tmpdir'.
    proc = subprocess.run(
        [get_abaqus_cmd(), "cae", "noGUI=%s" % script.name, "--",
         str(work), "spec"],
        cwd=str(work), stdin=subprocess.DEVNULL, capture_output=True,
        text=True, errors="replace", timeout=900)
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    # The refusals land in selectors.log, not on stdout: print() from a
    # `cae noGUI` script does not reach the launcher.
    sel = work / "selectors.log"
    if sel.exists():
        text += "\n" + sel.read_text(encoding="utf-8", errors="replace")
        sel.unlink()
    (work / ("%s.log" % name)).write_text(text, encoding="utf-8")
    readback = (json.loads(out.read_text(encoding="utf-8"))
                if out.exists() else None)
    return text, readback, deck.exists()


def _line(text: str, needle: str) -> str:
    for line in text.splitlines():
        if needle in line:
            return line.strip()[:200]
    return ""


def main() -> int:
    started = time.time()
    items = []

    def add(item_id, ok, detail, **extra):
        row = {"id": item_id, "status": "pass" if ok else "fail",
               "note": detail}
        row.update(extra)
        items.append(row)
        print("  %-4s %-38s %s" % ("PASS" if ok else "FAIL", item_id, detail))

    if not check_abaqus():
        print("SKIPPED: no Abaqus on this machine")
        print(json.dumps({"overall": "skipped", "reason": "no Abaqus",
                          "items": []}, ensure_ascii=False))
        return 0

    work = _fresh(ROOT / "artifacts" / "material_rebuild_check")

    # 1. The premise. A spec with no model_setup builds the material the spec
    #    declared -- so items 2 and 3 are about the rebuild, not about the
    #    generator failing to emit anything in the first place.
    _, intact, _ = _run_script(work, "v_plain",
                               build_v2.generate_script(_spec()))
    ok = bool(intact) and intact.get("Steel", {}).get("elastic") \
        and intact.get("Steel", {}).get("plastic") \
        and intact.get("Steel", {}).get("density")
    add("declared_material_is_built", ok,
        "Steel -> %s" % (intact.get("Steel") if intact else "no readback"),
        readback=intact.get("Steel") if intact else None)

    # 2. The failure itself, on the real kernel, with the guard removed. This
    #    is the whole justification for the refusal, so it is measured rather
    #    than quoted -- the deck is built by hand, exactly as the generator
    #    used to emit it.
    handmade = build_v2.generate_script(_spec())
    marker = "# --- Parts"
    rebuilt = handmade.replace(
        marker, "m.Material(name='Steel')\n\n" + marker, 1)
    _, wiped, _ = _run_script(work, "v_rebuilt", rebuilt)
    steel = (wiped or {}).get("Steel", {})
    add("rebuilding_erases_it_silently",
        bool(wiped) and not steel.get("elastic")
        and not steel.get("plastic") and not steel.get("density"),
        "after a second Material(name='Steel'): %s -- and the kernel raised "
        "nothing, so a spec declaring E, yield and density would build a "
        "model with none of them" % steel,
        readback=steel)

    # 3. Which the generator now refuses, before Abaqus is started at all.
    try:
        build_v2.generate_script(
            _spec(model_setup=[{"call": "Material", "name": "Steel"}]))
        refusal = ""
    except SpecError as exc:
        refusal = str(exc)
    add("the_rebuild_is_refused_at_generation",
        "Steel" in refusal and "ref: Steel" in refusal,
        (("refused, and the message names the route out: ...%s"
          % refusal[-90:]) if refusal else
         "NOT REFUSED -- the generator emitted a deck that erases its own "
         "material"),
        refusal=refusal)

    # 4. The route out, end to end. Not "the refusal mentions a route" -- the
    #    route is taken through the shipped generator and the model is read
    #    back. If Elastic did not survive this, the refusal above would be
    #    sending people somewhere no better than where they were.
    spec = _spec(model_setup=[{
        "call": "Hyperelastic", "target": {"ref": "Steel"},
        "materialType": "ISOTROPIC", "type": "NEO_HOOKE",
        "testData": "OFF", "volumetricResponse": "VOLUMETRIC_DATA",
        "table": [[0.5, 0.0]]}])
    text = build_v2.generate_script(spec)
    compiles = "_gcall(m.materials['Steel'], 'Hyperelastic'" in text
    _, after, _ = _run_script(work, "v_ref", text)
    steel = (after or {}).get("Steel", {})
    add("calling_into_the_material_keeps_what_was_there",
        compiles and steel.get("hyperelastic") and steel.get("elastic")
        and steel.get("plastic") and steel.get("density"),
        "target: {ref: Steel} compiles to m.materials['Steel'] and the model "
        "comes back %s -- Hyperelastic added, and the spec's own properties "
        "still there" % steel,
        readback=steel)

    # 5. A material this spec never declared is still an error, and says so
    #    where it can be acted on rather than as a KeyError from the kernel.
    try:
        build_v2.generate_script(_spec(model_setup=[{
            "call": "Density", "target": {"ref": "Ghost"},
            "table": [[1.0]]}]))
        ghost = ""
    except SpecError as exc:
        ghost = str(exc)
    add("an_undeclared_name_is_refused_with_the_list",
        "Ghost" in ghost and "Steel" in ghost,
        "refused, and the message says what IS reachable" if ghost
        else "NOT REFUSED",
        refusal=ghost)

    # 6. The counterexample for the runtime layer. The refusal knows the name
    #    `Material`; this spec erases the material with a call it has never
    #    heard of, gets past generation, and has to be caught by the check that
    #    knows no names at all.
    sneaky = build_v2.generate_script(
        _spec(model_setup=[{"call": "ContactProperty", "name": "Ip"}]))
    assert "MATERIAL_ERASED" in sneaky
    sneaky = sneaky.replace(
        "for _mat_name, _mat_attrs in",
        "del m.materials['Steel']\nm.Material(name='Steel')\n"
        "for _mat_name, _mat_attrs in", 1)
    log, _, deck_written = _run_script(work, "v_sneaky", sneaky)
    caught = "MATERIAL_ERASED" in log
    add("an_unmeasured_route_is_caught_at_runtime",
        caught and not deck_written,
        ("a call the refusal has never heard of erased Steel; the build "
         "stopped before any deck was written, naming what was lost -- %s"
         % _line(log, "MATERIAL_ERASED")) if caught else
        ("NOT CAUGHT -- the build ran on with a material this spec declares "
         "and the model does not have%s"
         % (", and wrote a deck" if deck_written else "")),
        deck_written=deck_written)

    failed = [i for i in items if i["status"] == "fail"]
    overall = "fail" if failed else "pass"
    elapsed = round(time.time() - started, 1)
    print("\nRESULT: %s (%d/%d) in %.1fs"
          % (overall.upper(), len(items) - len(failed), len(items), elapsed))
    print(json.dumps({"overall": overall, "seconds": elapsed,
                      "abaqus_release": detect_abaqus_release(),
                      "items": items}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
