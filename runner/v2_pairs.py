"""The two ways a spec fastens one surface to another: tie and contact.

Both take the same four things -- a name and two assembly surface names -- and
turn them into kernel calls. Neither knows how the surfaces were selected or
what a step is, which is why they sit apart from the block that builds them.

The seam earns itself on the contact side. A contact pair is not one call but
four to six: the property, its normal behaviour, its tangential behaviour, and
then the pair itself in whichever of the two shapes the model's solver has.
build_v2.py decides WHICH interactions exist; how each one is spelled is here.
The one rule about the SET of them that is really a rule about tie semantics --
a surface may be the secondary of only one tie -- is here too, next to the
sentence it protects.

Runs in the host interpreter (3.13). It emits Python 2.7 text for the Abaqus
kernel; it does not execute it.
"""

from __future__ import annotations

import re

from runner.spec_base import SpecError


def _refuse_repeated_tie_secondary(entries: list) -> None:
    """One surface may be the secondary of only one tie. Refuse here, not there.

    A `*TIE` secondary surface hands its nodes to the constraint, and a node
    cannot obey two of them. Abaqus does say so -- `OVERCONSTRAINT CHECKS:
    NODE 289 INSTANCE BOLT1 IS USED MORE THAN ONCE AS A SLAVE NODE` -- but it
    says it in the input processor, about a node number, after a licence has
    been taken, and reading it requires knowing that `secondary` means slave.

    The shape this catches is the standard bolt: a shank through two plates,
    tied to both hole walls. Written the obvious way the shank is the
    secondary of both ties, and the whole model is refused. The fix is not a
    tolerance -- it is that the SHANK is the main of both ties and each hole
    wall is a secondary once. Measured 2026-08-18: a planner asked for this
    connection wrote the obvious way on its first attempt.

    Only an exactly repeated selector is refused. Two ties whose secondaries
    are different faces of the same instance are ordinary (a plate tied on
    top and on the bottom), so instance-level matching would refuse correct
    models -- and a refusal that fires on correct input is worse than this
    check not existing.
    """
    seen: dict = {}
    for i, inter in enumerate(entries):
        if "call" in inter or inter.get("type") != "tie":
            continue
        sec = inter.get("secondary")
        if not isinstance(sec, str):
            continue
        key = " ".join(sec.split())
        name = str(inter.get("name") or "interactions[%d]" % i)
        if key in seen:
            raise SpecError(
                "interaction %r and %r both give %r as their `secondary`. A "
                "tie's secondary surface hands its nodes to the constraint, "
                "and a node can only obey one, so Abaqus refuses the whole "
                "model (OVERCONSTRAINT CHECKS ... USED MORE THAN ONCE AS A "
                "SLAVE NODE). For a bolt shank tied into two hole walls, make "
                "the SHANK the `main` of both ties and each hole wall a "
                "`secondary` once." % (seen[key], name, sec))
        seen[key] = name


def _selector_radius(selector) -> float | None:
    """The `r` of an `@r=` selector, or None if it does not name one."""
    if not isinstance(selector, str):
        return None
    match = re.search(r"@r\s*=\s*([0-9]*\.?[0-9]+)", selector)
    return float(match.group(1)) if match else None


def _refuse_tie_gap_beyond_tolerance(entries: list) -> None:
    """A bolt in a clearance hole is 1 mm from the wall. Say so before solving.

    An M20 shank is `@r=10` and its hole is `@r=11`, so the surfaces the tie
    joins are a millimetre apart everywhere. A `position_tolerance` under that
    gap ties nothing: Abaqus writes the `*Tie`, mutters `WILL NOT BE TIED TO
    THE MASTER` in the .dat, and finishes the job COMPLETED with the bolts
    absent from the load path. Measured on a two-layer plate, a 0.05 gap under
    a 0.01 tolerance moved the tip 7.95x and still reported success.

    The .dat scanner does catch this afterwards, which is a solve already paid
    for -- and on this connection the arithmetic is available before CAE
    starts: both surfaces state their radius in the selector.

    Only refused when both selectors carry `@r=` and the tolerance is stated
    and is not more than the gap. A COMPUTED tolerance is left alone; whether
    Abaqus's own guess covers the gap is not something this can work out, and
    guessing wrong here would refuse a model that solves.
    """
    for i, inter in enumerate(entries):
        if "call" in inter or inter.get("type") != "tie":
            continue
        tolerance = inter.get("position_tolerance")
        if tolerance is None:
            continue
        r_main = _selector_radius(inter.get("main"))
        r_sec = _selector_radius(inter.get("secondary"))
        if r_main is None or r_sec is None:
            continue
        gap = abs(r_main - r_sec)
        if gap == 0.0 or float(tolerance) > gap:
            continue
        name = str(inter.get("name") or "interactions[%d]" % i)
        raise SpecError(
            "interaction %r ties a surface at r=%g to one at r=%g, so the two "
            "are %g apart everywhere, and its `position_tolerance` is %g. "
            "Nothing would be tied: Abaqus leaves nodes outside the tolerance "
            "untied, says so only as a .dat warning (WILL NOT BE TIED TO THE "
            "MASTER), and completes the job with the bolt out of the load "
            "path. Set `position_tolerance` above the gap plus the mesh's "
            "chord height (seed^2 / (8 r)) -- for this pair, above %g."
            % (name, r_main, r_sec, gap, float(tolerance), gap))


def _tie_call(name: str, inter: dict, main_set: str, sec_set: str) -> str:
    if inter.get("property"):
        raise SpecError(
            "interaction %r is a tie but carries a `property` block. A tie is a "
            "constraint, not a contact interaction — it has no friction and no "
            "normal behaviour, so those settings would be silently discarded."
            % name)

    tolerance = inter.get("position_tolerance")
    # positionToleranceMethod=COMPUTED lets Abaqus pick, and anything outside
    # the tolerance is left untied with only a warning in the .dat. Stating a
    # tolerance is therefore the only way to know the pair bound.
    if tolerance is None:
        tol_args = "positionToleranceMethod=COMPUTED,"
    else:
        tol_args = ("positionToleranceMethod=SPECIFIED, positionTolerance=%r,"
                    % float(tolerance))
    return ("_tie(m, %r, a.surfaces[%r], a.surfaces[%r],\n"
            "     %s adjust=%s, tieRotations=ON, thickness=ON)"
            % (name, main_set, sec_set, tol_args,
               "ON" if inter.get("adjust") else "OFF"))


def _contact_calls(name: str, inter: dict, main_set: str, sec_set: str,
                   explicit: bool = False) -> list[str]:
    prop = inter.get("property") or {}
    friction = float(prop.get("friction", 0.0) or 0.0)
    separation = prop.get("allow_separation", True)
    prop_name = name.upper() + "_PROP"

    lines = [
        "m.ContactProperty(%r)" % prop_name,
        "m.interactionProperties[%r].NormalBehavior(" % prop_name,
        "    pressureOverclosure=HARD, allowSeparation=%s,"
        % ("ON" if separation else "OFF"),
        "    constraintEnforcementMethod=DEFAULT)",
    ]
    if friction > 0.0:
        lines += [
            "m.interactionProperties[%r].TangentialBehavior(" % prop_name,
            "    formulation=PENALTY, directionality=ISOTROPIC,",
            "    slipRateDependency=OFF, pressureDependency=OFF,",
            "    temperatureDependency=OFF, dependencies=0,",
            "    table=((%r, ),), shearStressLimit=None," % friction,
            "    maximumElasticSlip=FRACTION, fraction=0.005,",
            "    elasticSlipStiffness=None)",
        ]
    else:
        # Spelled out rather than left to the default. FRICTIONLESS is what
        # Abaqus assumes when no tangential behaviour is defined, but a reader
        # of the deck cannot tell "frictionless on purpose" from "nobody
        # thought about friction", and those are different models.
        lines += [
            "m.interactionProperties[%r].TangentialBehavior(formulation=FRICTIONLESS)"
            % prop_name,
        ]
    sliding = ("SMALL" if str(inter.get("sliding", "small")) == "small"
               else "FINITE")
    if explicit:
        # Measured on Abaqus 2021, by making the call rather than by reading it:
        # SurfaceToSurfaceContactExp takes neither `thickness` nor
        # `adjustMethod`, which Std does -- and its own __doc__ lists
        # `masterNoThick`/`slaveNoThick` among the REQUIRED arguments, while the
        # kernel answers "keyword error on masterNoThick" to that spelling and
        # "keyword error on mainNoThick" to the other. The call below is exactly
        # the argument set that was measured to be accepted (probe_conwep/
        # probe_exp_kwargs.py), with nothing added on the strength of the
        # docstring.
        lines.append(
            "_contact_exp(m, %r, a.surfaces[%r], a.surfaces[%r],\n"
            "             createStepName='Initial', sliding=%s,\n"
            "             interactionProperty=%r,\n"
            "             mechanicalConstraint=KINEMATIC)"
            % (name, main_set, sec_set, sliding, prop_name))
        return lines
    lines.append(
        "_contact(m, %r, a.surfaces[%r], a.surfaces[%r],\n"
        "         createStepName='Initial', sliding=%s, thickness=ON,\n"
        "         interactionProperty=%r, adjustMethod=NONE,\n"
        "         initialClearance=OMIT, datumAxis=None, clearanceRegion=None)"
        % (name, main_set, sec_set, sliding, prop_name))
    return lines
