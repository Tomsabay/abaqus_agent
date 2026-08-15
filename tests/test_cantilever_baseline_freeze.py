"""Cantilever frozen baseline guards (BUILD_SPEC W3, adjudication C3).

Freezes three things the on-camera theory acceptance depends on:
  1. element type C3D20R for the Standard cantilever build (generator output),
  2. expected.json baseline values = the real-solve values from run
     dd6ec1145b8de62f, with tolerances NOT widened (C3 forbids rtol widening),
  3. the frozen U_tip stays within 5% of Euler-Bernoulli PL^3/3EI.

Hermetic: only generates the CAE script text, never invokes Abaqus.
"""

import importlib
import json
from pathlib import Path

import pytest
import yaml

build_model_module = importlib.import_module("runner.build_model")

ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = ROOT / "cases" / "cantilever"
FROZEN_RUN_ID = "dd6ec1145b8de62f"
FROZEN_U_TIP = -0.0019039579201489687
FROZEN_MISES_MAX = 0.6528551578521729


def _load_spec():
    return yaml.safe_load((CASE_DIR / "spec.yaml").read_text(encoding="utf-8"))


def test_generated_cantilever_script_pins_c3d20r(tmp_path):
    spec = _load_spec()

    # The frozen baseline is only valid for this exact discretization: a
    # Standard/Static solve meshed at seed 5.0. Any of these moving means the
    # baseline must be re-frozen (new run + expected.json + this test).
    assert spec["analysis"]["solver"] == "standard"
    assert spec["analysis"]["step_type"] == "Static"
    assert spec["geometry"]["seed_size"] == 5.0

    script_path = tmp_path / "build_model_script.py"
    build_model_module._write_cae_script(spec, script_path, tmp_path)
    script = script_path.read_text(encoding="utf-8")

    # Standard branch pins C3D20R...
    assert "elemCode=_C.C3D20R, elemLibrary=_C.STANDARD" in script
    # ...and the emitted selector statically resolves to that branch for this
    # spec (mirror of the generated `_is_explicit` expression).
    step_type = spec["analysis"]["step_type"]
    solver = spec["analysis"]["solver"]
    emitted = "_is_explicit = '%s'.startswith('Dynamic_Explicit') or '%s' == 'explicit'" % (
        step_type,
        solver,
    )
    assert emitted in script
    assert not (step_type.startswith("Dynamic_Explicit") or solver == "explicit")


def test_expected_json_matches_frozen_c3d20r_baseline():
    expected = json.loads((CASE_DIR / "expected.json").read_text(encoding="utf-8"))
    u_tip = expected["kpis"]["U_tip"]
    mises = expected["kpis"]["MISES_MAX"]

    assert u_tip["value"] == FROZEN_U_TIP
    assert mises["value"] == FROZEN_MISES_MAX

    # C3 adjudication: passing by widening tolerances is forbidden.
    assert u_tip["rtol"] == 0.10
    assert u_tip["atol"] == 1e-6
    assert mises["rtol"] == 0.20
    assert mises["atol"] == 0.01

    for kpi in (u_tip, mises):
        assert "C3D20R" in kpi["note"]
        assert FROZEN_RUN_ID in kpi["note"]


def test_mises_baseline_note_states_the_position_the_extractor_uses():
    """The note has to name the stress definition, and name it correctly.

    Until 2026-08-03 it said "integration-point Mises max ... Not an
    extrapolated surface stress" -- the exact opposite of what the extractor
    does. post/extract_kpis.py has subset any MISES field_max to ELEMENT_NODAL
    since e2cd58c (2026-05-02), months before this baseline was frozen, so the
    frozen number is an extrapolated, unaveraged corner-node value. Anyone
    reproducing it with position=INTEGRATION_POINT gets a lower number and has
    no way to tell whether their model or the baseline is at fault.

    Mises is magnitude-only and the tolerance is 20%, so nothing in the suite
    would have caught the mislabel. This pins the prose to the code.
    """
    expected = json.loads((CASE_DIR / "expected.json").read_text(encoding="utf-8"))
    note = expected["kpis"]["MISES_MAX"]["note"]
    extractor = (ROOT / "post" / "extract_kpis.py").read_text(encoding="utf-8")

    assert "getSubset(position=ELEMENT_NODAL)" in extractor, (
        "extract_kpis.py no longer requests ELEMENT_NODAL for Mises; the frozen "
        "MISES_MAX is that position's value and must be re-frozen, note included"
    )
    # The definition claim is the first sentence; later sentences are free to
    # name the positions this baseline is NOT, which is the useful part.
    claim = note.split(":", 1)[-1].split(".", 1)[0].lower()
    assert "element_nodal" in claim, "first sentence must name the position: %r" % claim
    assert "integration-point" not in claim.replace("_", "-")


def test_frozen_u_tip_within_5_percent_of_euler_bernoulli():
    spec = _load_spec()
    geo, mat, load = spec["geometry"], spec["material"], spec["bc_load"]

    inertia = geo["W"] * geo["H"] ** 3 / 12.0
    theory = abs(load["value"]) * geo["L"] ** 3 / (3.0 * mat["E"] * inertia)

    rel_dev = abs(abs(FROZEN_U_TIP) - theory) / theory
    assert rel_dev < 0.05, "frozen U_tip deviates %.2f%% from theory" % (rel_dev * 100)


@pytest.mark.skipif(
    not (CASE_DIR / "runs" / FROZEN_RUN_ID / "Cantilever.inp").exists(),
    reason="archived run dir not present (runs/ is gitignored)",
)
def test_archived_baseline_run_inp_uses_c3d20r():
    inp = (CASE_DIR / "runs" / FROZEN_RUN_ID / "Cantilever.inp").read_text(
        encoding="utf-8", errors="replace"
    )
    element_lines = [
        line for line in inp.splitlines() if line.lower().startswith("*element, type=")
    ]
    assert element_lines == ["*Element, type=C3D20R"]
