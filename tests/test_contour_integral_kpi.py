"""The J-integral KPI: what it returns, and the three things it refuses.

Hermetic — the numbers here are the ones measured on Abaqus 2021
(artifacts/probe_crack), replayed through a fake ODB. A single-edge-notched
plate, a/W = 0.2, plane strain, sigma = 100 MPa, E = 210 GPa, nu = 0.3, against
the handbook

    F   = 1.12 - 0.231(a/W) + 10.55(a/W)^2 - 21.72(a/W)^3 + 30.39(a/W)^4
    K_I = F * sigma * sqrt(pi*a) = 768.3 MPa*sqrt(mm)
    J   = K_I^2 (1-nu^2)/E       = 2.5576 N/mm

WHY THIS LAYER EXISTS AND WHY IT IS HERE AND NOT IN THE BUILDER. Every other
`expect:` in this dialect is checked while the model is being built, because
geometry can be measured before a solve. J cannot: it does not exist until the
job is done, and a contour integral produces a number for any crack it is
handed. #70 closed seams and recorded that a crack's truth layer was an open
question — seams are checked by node count and a crack has no equivalent tell.
These are the three tells, and the third was a surprise.

    correct     2.4685 2.5013 2.5032 2.5033 2.5033 2.5033
                outermost is -2.12% from the handbook.

    no seam     -1.4e-16 .. -1.3e-14, i.e. round-off either side of nothing --
                NOT clean zeros. The crack line was never separated, so the
                "crack" runs through solid material. Job COMPLETED, no warning.

    q reversed  -2.5033: the right magnitude, wrong sign. Job COMPLETED, no
                warning — AND its contours are as path-independent as the
                correct model's (7.7e-04 either way). So path-independence
                alone would have passed it. Only the sign catches it.
"""

from __future__ import annotations

import importlib
import math
from types import SimpleNamespace

import pytest

extract = importlib.import_module("post.extract_kpis")

HANDBOOK_J = 2.5576

MEASURED_OK = [2.4684836864471436, 2.501328468322754, 2.503185272216797,
               2.503253698348999, 2.503265142440796, 2.503265619277954]
# Not clean zeros. This is what Abaqus actually returned, and it matters: an
# `== 0.0` test lets these fall through to the sign check and reports a missing
# seam as a reversed q vector. The real gate caught that.
MEASURED_NO_SEAM = [-1.3530843112619095e-16, -3.8337388819087437e-16,
                    -2.105954299835844e-15, -1.56472057533108e-15,
                    -4.165071065820314e-15, -1.3298390166838203e-14]
MEASURED_BACKWARDS = [-v for v in MEASURED_OK]


def _step(*cracks):
    """A step whose history holds one `J at <label>_Contour_<n>` per contour."""
    outputs = {}
    for label, values in cracks:
        for i, v in enumerate(values, start=1):
            key = "J at %s_Contour_%d" % (label, i)
            outputs[key] = SimpleNamespace(data=[(1.0, v)])
    return SimpleNamespace(
        historyRegions={"ElementSet  ALL ELEMENTS":
                        SimpleNamespace(historyOutputs=outputs)})


def _kpi(**extra):
    kpi = {"name": "J_TIP", "type": "contour_integral_j"}
    kpi.update(extra)
    return kpi


def test_the_handbook_value_is_what_the_measurement_was_checked_against():
    """The premise, recomputed rather than pasted, so a typo in one of the two
    numbers cannot go unnoticed."""
    w, a, e, nu, sig = 50.0, 10.0, 210000.0, 0.3, 100.0
    r = a / w
    f = 1.12 - 0.231 * r + 10.55 * r ** 2 - 21.72 * r ** 3 + 30.39 * r ** 4
    k = f * sig * math.sqrt(math.pi * a)
    assert k == pytest.approx(768.3, abs=0.1)
    assert k * k * (1 - nu * nu) / e == pytest.approx(HANDBOOK_J, abs=0.001)


def test_a_converged_crack_returns_the_outermost_contour():
    got = extract._contour_integral_j(_step(("J_CRACK_TIP", MEASURED_OK)), _kpi())
    assert got == pytest.approx(MEASURED_OK[-1])
    # And that value is the physics, not just a number off a list.
    assert abs(got - HANDBOOK_J) / HANDBOOK_J < 0.03


def test_the_inner_contour_is_not_averaged_in():
    """Contour 1 hugs the singularity. Averaging it in would drag the answer
    toward the tip -- and would also make the convergence test below fail on
    every correct model."""
    got = extract._contour_integral_j(_step(("J_CRACK_TIP", MEASURED_OK)), _kpi())
    assert got != pytest.approx(sum(MEASURED_OK) / len(MEASURED_OK))


def test_an_unseparated_crack_is_refused_rather_than_reported_as_zero():
    with pytest.raises(ValueError) as caught:
        extract._contour_integral_j(_step(("J_CRACK_TIP", MEASURED_NO_SEAM)), _kpi())
    assert "SEPARATED" in str(caught.value)
    # The diagnosis has to be the missing seam, not the sign -- every one of
    # these values is negative, so the sign check would also have fired and
    # would have sent the user to reverse a q vector that is already right.
    assert "negative" not in str(caught.value)
    assert all(v < 0 for v in MEASURED_NO_SEAM)


def test_a_reversed_extension_direction_is_refused_on_its_sign():
    """The one path-independence would have passed."""
    with pytest.raises(ValueError) as caught:
        extract._contour_integral_j(_step(("J_CRACK_TIP", MEASURED_BACKWARDS)),
                                    _kpi())
    assert "negative" in str(caught.value)

    # The premise of this test, asserted rather than assumed: the broken run's
    # contours really are as converged as the correct one's, so nothing but the
    # sign distinguishes them.
    outer_ok = MEASURED_OK[1:]
    outer_bad = MEASURED_BACKWARDS[1:]
    spread = lambda vs: (max(vs) - min(vs)) / abs(sum(vs) / len(vs))
    assert spread(outer_ok) == pytest.approx(spread(outer_bad), rel=1e-9)
    assert spread(outer_ok) < 1e-3


def test_contours_that_do_not_converge_are_refused():
    drifting = [2.4, 3.0, 3.6, 4.2, 4.8, 5.4]
    with pytest.raises(ValueError) as caught:
        extract._contour_integral_j(_step(("J_CRACK_TIP", drifting)), _kpi())
    assert "path-independent" in str(caught.value)


def test_the_convergence_tolerance_can_be_widened_but_is_not_open():
    # outer = 2.50 .. 2.70, mean 2.60, spread 0.0769 -- over the 0.05 default
    # and under an explicit 0.10.
    mild = [2.4, 2.50, 2.55, 2.60, 2.65, 2.70]
    with pytest.raises(ValueError):
        extract._contour_integral_j(_step(("J_CRACK_TIP", mild)), _kpi())
    got = extract._contour_integral_j(_step(("J_CRACK_TIP", mild)),
                                      _kpi(contour_tolerance=0.10))
    assert got == pytest.approx(2.70)
    # Widening is a decision, not an escape: a run that is nowhere near
    # converged still fails at the widened tolerance.
    wild = [2.4, 3.0, 3.6, 4.2, 4.8, 5.4]
    with pytest.raises(ValueError):
        extract._contour_integral_j(_step(("J_CRACK_TIP", wild)),
                                    _kpi(contour_tolerance=0.10))


def test_the_real_measurement_passes_the_default_tolerance():
    """The default is only right if a genuinely converged model clears it."""
    outer = MEASURED_OK[1:]
    spread = (max(outer) - min(outer)) / abs(sum(outer) / len(outer))
    assert spread == pytest.approx(7.7e-4, rel=0.1)
    assert spread < 0.05


def test_a_step_with_no_contour_integral_says_so():
    empty = SimpleNamespace(historyRegions={
        "Assembly ASSEMBLY": SimpleNamespace(
            historyOutputs={"ALLIE": SimpleNamespace(data=[(1.0, 118.7)])})})
    with pytest.raises(KeyError) as caught:
        extract._contour_integral_j(empty, _kpi())
    assert "contourIntegral" in str(caught.value)


def test_two_cracks_and_no_location_is_refused_not_averaged():
    """Reducing across cracks would average two different crack tips into one
    number, which is the shape #55 found in history_output_max."""
    two = _step(("J_A_TIP", MEASURED_OK), ("J_B_TIP", MEASURED_OK))
    with pytest.raises(KeyError) as caught:
        extract._contour_integral_j(two, _kpi())
    assert "names none" in str(caught.value)

    got = extract._contour_integral_j(two, _kpi(location="J_B"))
    assert got == pytest.approx(MEASURED_OK[-1])


def test_a_location_matching_nothing_or_everything_is_refused():
    two = _step(("J_A_TIP", MEASURED_OK), ("J_B_TIP", MEASURED_OK))
    with pytest.raises(KeyError):
        extract._contour_integral_j(two, _kpi(location="J_C"))
    with pytest.raises(KeyError) as caught:
        extract._contour_integral_j(two, _kpi(location="TIP"))
    assert "matches 2" in str(caught.value)


def test_the_type_is_reachable_through_the_schema():
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    schema = json.loads((root / "schema" / "spec_schema.json")
                        .read_text(encoding="utf-8"))
    enum = (schema["properties"]["outputs"]["properties"]["kpis"]["items"]
            ["properties"]["type"]["enum"])
    assert "contour_integral_j" in enum, (
        "an extractor the schema refuses is an extractor nobody can ask for")


def test_both_tolerances_can_actually_be_set_in_a_spec():
    """The knobs above are only knobs if a spec carrying them validates.

    `outputs.kpis[]` is `additionalProperties: false`, so an unpublished key is
    refused with "Additional properties are not allowed" — a message about a
    typo, not about the feature. `zero_tolerance` shipped that way and the
    tests above passed regardless, because they call the extractor directly.
    """
    from tools.schema_validator import validate_spec

    spec = {
        "meta": {"abaqus_release": "2021", "model_name": "M",
                 "units": "mm_MPa_t"},
        "material": {"name": "S", "E": 210000.0, "nu": 0.3,
                     "density": 7.85e-9},
        "parts": [{"name": "P",
                   "features": [{"call": "BaseSolidExtrude",
                                 "args": {"sketch": {"sketch": "s"},
                                          "depth": 1.0}}],
                   "section": {"type": "solid", "material": "S"},
                   "expect": {"volume": 1.0}}],
        "assembly": {"instances": [{"part": "P", "name": "p1"}]},
        "steps": [{"name": "S1", "call": "StaticStep", "args": {}}],
        "outputs": {"kpis": [{"name": "J_TIP", "type": "contour_integral_j",
                              "zero_tolerance": 1e-9,
                              "contour_tolerance": 0.1,
                              "location": "J_CRACK"}]},
    }
    valid, errors = validate_spec(spec)
    assert valid, errors


def test_the_type_is_reachable_through_the_odb_lens_gate_too():
    """The second door on the same path, and the one that opens after the solve.

    tests/test_kpi_type_closed.py holds all three copies of this list together
    and caught the omission here; this asserts the specific consequence. A type
    the extractor knows and odb_lens does not validates, builds, meshes and
    SOLVES, and is refused afterwards by the layer meant to be the cheap gate.
    """
    from odb_lens.recipe import validate_recipe

    valid, errors = validate_recipe(
        [{"name": "J_TIP", "type": "contour_integral_j"}])
    assert valid, errors


def test_the_zero_floor_is_a_statement_about_round_off_not_physics():
    """A real J that happens to be small must not be swallowed as "no crack"."""
    small = [1e-9] * 6
    got = extract._contour_integral_j(_step(("J_CRACK_TIP", small)), _kpi())
    assert got == pytest.approx(1e-9)

    # And the floor can be raised for a unit system where it needs to be.
    with pytest.raises(ValueError) as caught:
        extract._contour_integral_j(_step(("J_CRACK_TIP", small)),
                                    _kpi(zero_tolerance=1e-6))
    assert "SEPARATED" in str(caught.value)


def test_the_measured_round_off_is_orders_below_the_default_floor():
    """The basis for the default, asserted rather than asserted-to-be-obvious."""
    assert max(abs(v) for v in MEASURED_NO_SEAM) < 1e-13
    assert min(abs(v) for v in MEASURED_OK) > 1.0
