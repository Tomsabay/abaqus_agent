"""`derived_stress_concentration` returns a STRESS, not a concentration factor.

#32, decided 2026-08-07: document it, do not change it.

WHAT IT ACTUALLY DOES. It reads the Mises field over the KPI's location and
reduces it. There is no division by a nominal stress anywhere in the branch,
and there never was -- the line above it used to carry the comment
`Kt = max_mises_at_hole / nominal_stress`, describing arithmetic the code does
not do. So the shipped `cases/plate_hole` case has a KPI named `SCF` whose
`note` promises "analytical ~3.0 for R/W=0.2" sitting beside a value of about
300 MPa.

AND IT IS NOT `MISES_HOLE_EDGE` IN DIFFERENT UNITS EITHER. `field_max` routes
a stress field through `_at_element_nodal`; this branch does not. So one is the
unaveraged extrapolation to the element nodes and the other is the integration
point, which on this very plate were measured 8.2% apart (Mises 3.0966 element
nodal against S22 2.8420 integration point -- see `_at_element_nodal`). Dividing
`SCF` by the nominal stress by hand does not recover the Kt the note promises,
and the shortfall is a position, not a rounding.

WHY IT IS NOT FIXED. `run_id = sha256(spec)`. The name and the note both live
in `cases/plate_hole/spec.yaml`, so correcting either -- even the note, even a
comment -- changes the hash, and the frozen Abaqus baseline under
`cases/plate_hole/runs/` was measured once on one machine and cannot be
recomputed for a spec that has since changed. The cost of the honest rename is
a piece of unreproducible evidence; the cost of leaving it is a misleading name
with this file attached to it.

WHAT THIS FILE IS FOR. Two directions, like every other guard here. It fails if
someone "fixes" the extractor into returning a ratio (which would silently
change what every existing plate_hole baseline means), and it fails if the
misleading `note` is quietly edited out of the spec (which would change the
run_id without anyone weighing that).
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

extract = importlib.import_module("post.extract_kpis")

SPEC = ROOT / "cases" / "plate_hole" / "spec.yaml"
EXPECTED = ROOT / "cases" / "plate_hole" / "expected.json"


def _source_of_branch() -> str:
    """The branch's CODE, with its comments stripped.

    Stripped because the comments explain the very things these tests look for
    -- the first draft of this file matched `_at_element_nodal` inside the
    comment saying the branch does not call it.
    """
    text = (ROOT / "post" / "extract_kpis.py").read_text(encoding="utf-8")
    body = text.split('elif kpi_type == "derived_stress_concentration":', 1)[1]
    body = body.split("\n    elif ", 1)[0].split("\n    else:", 1)[0]
    return "\n".join(line for line in body.splitlines()
                     if not line.strip().startswith("#"))


def test_the_branch_performs_no_division():
    """The heart of it. A concentration factor is a ratio; this is not one."""
    assert "/" not in _source_of_branch(), (
        "a division appeared in the SCF branch. If it now divides by a nominal "
        "stress, this KPI changed meaning and every frozen plate_hole baseline "
        "is a number of a different quantity")


def test_the_branch_does_not_extrapolate_to_element_nodes():
    """The second half of the mismatch, and the one that is easy to miss.

    `field_max` routes stress through `_at_element_nodal`; this does not, so
    the two are not the same reading of the same peak.
    """
    assert "_at_element_nodal" not in _source_of_branch()
    field_max = (ROOT / "post" / "extract_kpis.py").read_text(encoding="utf-8")
    assert field_max.count("_at_element_nodal(field, var_name)") >= 2, (
        "field_max/field_min stopped extrapolating, which would make this "
        "whole comparison moot and the docstring above it wrong")


def test_the_shipped_case_still_carries_the_misleading_note():
    """Deliberately unfixed, so its being unfixed has to stay visible.

    If this fails because the note was corrected, that is not automatically
    wrong -- but it means a run_id changed, so `cases/plate_hole/runs/` has to
    be archived first (NG-11) and this file updated to say so.
    """
    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    scf = [k for k in spec["outputs"]["kpis"] if k["name"] == "SCF"]
    assert len(scf) == 1
    assert scf[0]["type"] == "derived_stress_concentration"
    assert "3.0" in scf[0].get("note", ""), (
        "the note promising a dimensionless ~3.0 is gone. Good, if the run "
        "directory was archived and the baseline re-measured; a silent hash "
        "change otherwise")


def test_the_baseline_never_pinned_the_scf_value():
    """Why this has cost nothing so far: nothing checks the misleading number.

    `expected.json` grades MISES_HOLE_EDGE and U_X_MAX. SCF is extracted,
    reported, and compared against nothing -- so the wrong name has never made
    a run pass or fail.
    """
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    assert "SCF" not in expected["kpis"]
    assert "MISES_HOLE_EDGE" in expected["kpis"]


def test_the_type_is_documented_as_returning_a_stress():
    """The schema is where someone writing a new spec looks first."""
    schema = json.loads((ROOT / "schema" / "spec_schema.json")
                        .read_text(encoding="utf-8"))
    described = (schema["properties"]["outputs"]["properties"]["kpis"]["items"]
                 ["properties"]["type"]["description"])
    assert "derived_stress_concentration" in described, (
        "the one type in the enum whose name says something the code does not "
        "do is the one the description has to cover")
