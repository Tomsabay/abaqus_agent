#!/usr/bin/env python3
"""Real-solver check for contour integrals: is the J right, and is a wrong one caught?

#70 closed seams and left a question it could not answer: a seam is checked by
a node count that moved, and a crack has no equivalent tell. A contour integral
produces a number for any crack you hand it. So before any of this could be
built, one thing had to be established -- WHAT WOULD A CRACK'S TRUTH LAYER BE?

The answer measured here has three parts, and the third was a surprise.

THE MODEL. Single-edge-notched plate under tension, the textbook case, so the
answer is known independently of Abaqus. W = 50, H = 100, a = 10, plane strain,
CPE8, seed 1.0, sigma = 100 MPa, E = 210 GPa, nu = 0.3:

    F   = 1.12 - 0.231(a/W) + 10.55(a/W)^2 - 21.72(a/W)^3 + 30.39(a/W)^4
    K_I = F * sigma * sqrt(pi*a)
    J   = K_I^2 (1 - nu^2) / E

Ends are loaded by traction with only two point restraints, because clamping
one would not be the boundary condition that formula assumes.

WHAT WAS MEASURED (Abaqus 2021, artifacts/probe_crack):

    correct      J = 2.4685 2.5013 2.5032 2.5033 2.5033 2.5033
                 outermost -2.12% from the handbook 2.5576.

    no seam      J = -1.4e-16 -3.8e-16 -2.1e-15 -1.6e-15 -4.2e-15 -1.3e-14.
                 The crack line was never separated, so the "crack" runs
                 through solid material. Job COMPLETED, zero warnings.
                 NOT clean zeros, which is the whole point: it is round-off
                 either side of nothing and every value is NEGATIVE, so an
                 `== 0.0` test lets them reach the sign check and reports the
                 missing seam as a reversed q vector. This gate is what caught
                 that, in the extractor and then again in itself.

    q reversed   J = -2.5033. Right magnitude, wrong sign. Job COMPLETED, zero
                 warnings -- AND its contours agree to 7.7e-04, exactly as well
                 as the correct model's. Path-independence would have passed
                 it. Only the sign catches it.

That third one is why the truth layer is three checks and not one. A check that
only tested convergence would be a check that says yes to a crack pointing the
wrong way, which is the shape this project exists to refuse.

AND THE OTHER HALF, ADDED BY #76. The three models above are built by a CAE
script of this gate's own. The last two items -- named, because the printed
list is eleven long -- build the SAME rig from a v2 spec and run it through the
real pipeline, because "the extractor can refuse a bad crack" and "a spec can
express a crack at all" are different claims and only the first was ever
measured. `spec_authored_j_matches_the_scripted_baseline` compares against THIS
GATE'S OWN scripted baseline rather than the handbook -- the handbook would not
notice a model that was merely close. `spec_authored_without_a_seam_is_still_refused`
removes the seam from the same spec and requires the refusal to still fire, so
reaching J through the dialect is not a way around the checks.

TWO things had to exist first, and neither was a limit of Abaqus. Parts were
hard-coded THREE_D, and a contour integral is normally done on a plane-strain
plate. And the crack line is one of the TWO edges the y=0 line becomes once the
tip is partitioned off, which no selector form could name -- `edge@box=` is
that form, and it is the same gap recorded against `cell@<plane>`.

A third change rode along and is deliberately NOT claimed as a blocker:
`assembly.operations` can now build a Set, which is what a named crack front
wants. Measured afterwards rather than assumed (artifacts/probe_ci_tuple_solve):
writing crackFront/crackTip as `{select:}` instead, which compiles to a tuple,
returns J = 2.503265619277954 -- the same number to every digit. The set form
buys a name, not the capability.

Exit codes: 0 = nothing failed (no Abaqus => "skipped", still 0);
            1 = at least one item ran and failed.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# importlib, because `post/__init__.py` re-exports the FUNCTION
# `extract_kpis`, so `from post import extract_kpis` binds that and not
# the module the private extractor lives in.
import importlib  # noqa: E402

from core.helpers import check_abaqus  # noqa: E402

extract_kpis = importlib.import_module("post.extract_kpis")
from tools.abaqus_cmd import detect_abaqus_release, get_abaqus_cmd  # noqa: E402

W, H, A = 50.0, 100.0, 10.0
E, NU, SIG = 210000.0, 0.3, 100.0
SEED = 1.0
CONTOURS = 6
# How far the outermost contour may sit from the handbook. The formula itself
# is a fit good to about 0.5%, the boundary condition is an idealisation, and
# 2.12% was measured -- so this is the band that says "the physics is right",
# not a tolerance anybody tuned until it passed.
HANDBOOK_BAND = 0.05

VARIANTS = ("v_baseline", "v_noseam", "v_backwards_q")


def handbook_j() -> float:
    r = A / W
    f = (1.12 - 0.231 * r + 10.55 * r ** 2 - 21.72 * r ** 3 + 30.39 * r ** 4)
    k = f * SIG * math.sqrt(math.pi * A)
    return k * k * (1 - NU * NU) / E


_BUILD = '''# -*- coding: utf-8 -*-
from abaqus import *
from abaqusConstants import *
import part, material, section, assembly, step, load, mesh
import interaction, job, connectorBehavior, regionToolset

W, H, A = %(W)r, %(H)r, %(A)r
E, NU, SIG, SEED = %(E)r, %(NU)r, %(SIG)r, %(SEED)r


def build(tag, seam=True, qdir=(1.0, 0.0, 0.0)):
    mname = 'M_' + tag
    m = mdb.Model(name=mname)
    s = m.ConstrainedSketch(name='p', sheetSize=400.0)
    s.rectangle(point1=(0.0, -H / 2), point2=(W, H / 2))
    p = m.Part(name='Plate', dimensionality=TWO_D_PLANAR, type=DEFORMABLE_BODY)
    p.BaseShell(sketch=s)
    d = p.DatumPlaneByPrincipalPlane(principalPlane=XZPLANE, offset=0.0)
    p.PartitionFaceByDatumPlane(datumPlane=p.datums[d.id], faces=p.faces)
    d2 = p.DatumPlaneByPrincipalPlane(principalPlane=YZPLANE, offset=A)
    p.PartitionFaceByDatumPlane(datumPlane=p.datums[d2.id], faces=p.faces)

    edges = p.edges.getByBoundingBox(-0.01, -0.01, -0.01, A + 0.01, 0.01, 0.01)
    p.Set(name='CRACKLINE', edges=edges)
    if seam:
        p.engineeringFeatures.assignSeam(regions=p.sets['CRACKLINE'])

    mat = m.Material(name='Steel')
    mat.Elastic(table=((E, NU), ))
    m.HomogeneousSolidSection(name='Sec', material='Steel', thickness=1.0)
    p.Set(name='ALLF', faces=p.faces)
    p.SectionAssignment(region=p.sets['ALLF'], sectionName='Sec')
    p.setElementType(regions=(p.faces, ),
                     elemTypes=(mesh.ElemType(elemCode=CPE8, elemLibrary=STANDARD),
                                mesh.ElemType(elemCode=CPE6M, elemLibrary=STANDARD)))
    p.seedPart(size=SEED)
    p.generateMesh()

    a = m.rootAssembly
    inst = a.Instance(name='P', part=p, dependent=ON)
    tip = inst.vertices.getByBoundingSphere(center=(A, 0.0, 0.0), radius=1e-4)
    a.Set(name='TIP', vertices=tip)

    m.StaticStep(name='Pull', previous='Initial')
    top = inst.edges.getByBoundingBox(-1, H / 2 - 0.01, -1, W + 1, H / 2 + 0.01, 1)
    bot = inst.edges.getByBoundingBox(-1, -H / 2 - 0.01, -1, W + 1, -H / 2 + 0.01, 1)
    a.Surface(name='TOP', side1Edges=top)
    a.Surface(name='BOT', side1Edges=bot)
    m.Pressure(name='PullTop', createStepName='Pull', region=a.surfaces['TOP'],
               magnitude=-SIG)
    m.Pressure(name='PullBot', createStepName='Pull', region=a.surfaces['BOT'],
               magnitude=-SIG)
    c1 = inst.vertices.getByBoundingSphere(center=(W, -H / 2, 0.0), radius=1e-4)
    a.Set(name='FIXY', vertices=c1)
    m.DisplacementBC(name='FixY', createStepName='Initial',
                     region=a.sets['FIXY'], u2=0.0)
    c2 = inst.vertices.getByBoundingSphere(center=(W, H / 2, 0.0), radius=1e-4)
    a.Set(name='FIXX', vertices=c2)
    m.DisplacementBC(name='FixX', createStepName='Initial',
                     region=a.sets['FIXX'], u1=0.0)

    q = (((A, 0.0, 0.0), (A + qdir[0], qdir[1], 0.0)), )
    a.engineeringFeatures.ContourIntegral(
        name='Crack', symmetric=OFF,
        crackFront=a.sets['TIP'], crackTip=a.sets['TIP'],
        extensionDirectionMethod=Q_VECTORS, qVectors=q,
        midNodePosition=0.25, collapsedElementAtTip=SINGLE_NODE)
    m.HistoryOutputRequest(name='J', createStepName='Pull',
                           contourIntegral='Crack', numberOfContours=%(N)d,
                           contourType=J_INTEGRAL, rebar=EXCLUDE)
    mdb.Job(name=tag, model=mname, numCpus=1).writeInput()


build('v_baseline')
build('v_noseam', seam=False)
build('v_backwards_q', qdir=(-1.0, 0.0, 0.0))
print('BUILD_DONE')
'''

_READ = '''# -*- coding: utf-8 -*-
from odbAccess import openOdb
import json

out = {}
for tag in %(tags)r:
    odb = openOdb(tag + '.odb')
    step = odb.steps['Pull']
    row = {}
    for rname in step.historyRegions.keys():
        hr = step.historyRegions[rname]
        for oname in hr.historyOutputs.keys():
            if 'J at' not in oname:
                continue
            row[oname] = float(hr.historyOutputs[oname].data[-1][1])
    out[tag] = row
    odb.close()
fh = open('j_all.json', 'w')
fh.write(json.dumps(out, indent=2, sort_keys=True))
fh.close()
print('READ_DONE')
'''


class _FakeHistoryOutput:
    def __init__(self, value):
        self.data = [(1.0, value)]


class _FakeStep:
    """The real ODB numbers, wrapped in the shape the extractor reads.

    The point of the gate is that the SHIPPED extractor refuses the SOLVED
    broken runs. Re-opening the odb inside the Abaqus runtime to call it there
    would need the whole subprocess round trip for three floats; this hands it
    the same values it would have read.
    """

    def __init__(self, row):
        outputs = dict((k, _FakeHistoryOutput(v)) for k, v in row.items())
        self.historyRegions = {"ElementSet  ALL ELEMENTS":
                               type("R", (), {"historyOutputs": outputs})()}


def _contours(row):
    keys = sorted(row, key=lambda k: int(k.rsplit("_", 1)[1]))
    return [row[k] for k in keys]


def _spread(values):
    outer = values[1:]
    mean = sum(outer) / float(len(outer))
    return (max(outer) - min(outer)) / abs(mean) if mean else float("inf")


def _fresh(work: Path) -> Path:
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    return work


def _run(work: Path, args, timeout=2400):
    return subprocess.run([get_abaqus_cmd()] + args, cwd=str(work),
                          stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, errors="replace", encoding="utf-8",
                          timeout=timeout)


def _spec(seam: bool = True) -> dict:
    """The SAME rig as `_BUILD` above, written in the v2 dialect instead.

    Same W/H/A, same seed, same CPE8, same pressure and the same two corner
    restraints -- so the J it produces is comparable to `v_baseline` number for
    number rather than merely "about right". That is the whole point of the
    item below: a spec-authored contour integral that lands within a fraction
    of a percent of the hand-written CAE script is evidence that the dialect
    expresses the same model, not a similar one.

    `seam=False` is the negative control. Everything else is identical, so what
    it proves is that the truth layer in `post/extract_kpis.py` still fires
    when the model arrives through the dialect: the J it produces is round-off,
    the job still reports COMPLETED, and the extractor has to refuse.
    """
    features = [
        {"op": "sketch", "id": "o", "plane": "XY",
         "profile": {"rect": {"corner1": [0.0, -H / 2], "corner2": [W, H / 2]}}},
        {"call": "BaseShell", "sketch": {"sketch": "o"}},
        {"call": "DatumPlaneByPrincipalPlane", "principalPlane": "XZPLANE",
         "offset": 0.0, "as": "mid"},
        {"call": "PartitionFaceByDatumPlane", "datumPlane": {"datum": "mid"},
         "faces": {"select": "face@all"}},
        {"call": "DatumPlaneByPrincipalPlane", "principalPlane": "YZPLANE",
         "offset": A, "as": "tipline"},
        {"call": "PartitionFaceByDatumPlane", "datumPlane": {"datum": "tipline"},
         "faces": {"select": "face@all"}},
    ]
    expect = {"area": W * H, "faces": 4}
    if seam:
        # `edge@box=` is what makes this writable at all. The y=0 line is TWO
        # edges after the x=A partition, and every other selector form names
        # both of them or none: a plane matches everything lying in it, `@all`
        # matches everything. Naming one of two was the gap recorded against
        # `cell@<plane>` when that form was refused.
        features.append({
            "call": "assignSeam",
            "target": {"attr": "engineeringFeatures"},
            "regions": {"set": "edge@box=0,0,0,%s,0,0" % A,
                        "name": "CRACKLINE", "expect": "=1"}})
        # 20, not 21: the crack TIP node is the one position on the line that
        # is not duplicated, because the seam terminates there. Measured on
        # Abaqus 2021 -- 41 nodes at 21 positions.
        expect["seams"] = [{"set": "CRACKLINE", "duplicated": 20}]

    return {
        "meta": {"abaqus_release": "2021", "model_name": "SENSpec",
                 "units": "mm_MPa_t",
                 "description": "single-edge-notch plate authored in the v2 "
                                "dialect%s" % ("" if seam else ", seam removed"),
                 "missing_questions": []},
        "material": {"name": "Steel", "E": E, "nu": NU},
        "parts": [{
            "name": "Plate",
            "dimensionality": "TWO_D_PLANAR",
            "features": features,
            "expect": expect,
            "section": {"type": "solid", "material": "Steel", "thickness": 1.0},
            "mesh": {"seed": SEED, "element": "CPE8"},
        }],
        "assembly": {
            "instances": [{"name": "P", "part": "Plate",
                           "translate": [0.0, 0.0, 0.0]}],
            "operations": [{
                "call": "ContourIntegral",
                "target": {"attr": "engineeringFeatures"},
                "name": {"literal": "Crack"},
                "symmetric": "OFF",
                # An assembly Set, not a part set: the crack is declared on
                # the instanced model. `assembly.operations` could not build
                # one before #76. That was not what made the contour integral
                # unwritable, though -- measured, `{select:}` compiles to a
                # tuple and returns the same J to every digit. The set form
                # buys a NAME, which `crackTip` reuses on the next line.
                "crackFront": {"set": "P:vertex@box=%s,0,0,%s,0,0" % (A, A),
                               "name": "TIP", "expect": "=1"},
                "crackTip": {"named_set": "TIP"},
                "extensionDirectionMethod": "Q_VECTORS",
                "qVectors": [[[A, 0.0, 0.0], [A + 1.0, 0.0, 0.0]]],
                "midNodePosition": 0.25,
                "collapsedElementAtTip": "SINGLE_NODE",
            }],
        },
        "steps": [{
            "name": "Pull", "type": "Static",
            "bcs": [
                {"name": "FixY", "type": "displacement", "u2": 0.0,
                 "region": "P:vertex@box=%s,%s,0,%s,%s,0" % (W, -H / 2, W, -H / 2)},
                {"name": "FixX", "type": "displacement", "u1": 0.0,
                 "region": "P:vertex@box=%s,%s,0,%s,%s,0" % (W, H / 2, W, H / 2)},
            ],
            "loads": [
                {"name": "Top", "type": "pressure", "value": -SIG,
                 "region": "P:edges@y=max"},
                {"name": "Bot", "type": "pressure", "value": -SIG,
                 "region": "P:edges@y=min"},
            ],
        }],
        "conditions": [{
            "call": "HistoryOutputRequest",
            "name": {"literal": "JOUT"},
            "createStepName": {"literal": "Pull"},
            "contourIntegral": {"literal": "Crack"},
            "numberOfContours": CONTOURS,
            "contourType": "J_INTEGRAL",
            "rebar": "EXCLUDE",
        }],
        "outputs": {"kpis": [{"name": "J_TIP", "type": "contour_integral_j",
                              "location": "Crack"}]},
    }


def _solve_spec(work, seam: bool = True) -> dict:
    """Run the dialect-authored model through the real pipeline."""
    import copy

    from agent.orchestrator import build_orchestrator

    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    return build_orchestrator(spec_dict=copy.deepcopy(_spec(seam=seam)),
                              workdir=work, expected_path=None,
                              runner_cfg=None).run()


def main() -> int:
    started = time.time()
    items = []

    def add(item_id, ok, detail, **extra):
        # `note`, not `detail`: collect_gate_evidence.py publishes by allowlist,
        # and `note` is already on it. Adding `detail` there would have
        # published every other gate's text as a side effect of shipping this
        # one -- which is the fail-open the allowlist exists to prevent.
        row = {"id": item_id, "status": "pass" if ok else "fail",
               "note": detail}
        row.update(extra)
        items.append(row)
        print("  %-4s %-32s %s" % ("PASS" if ok else "FAIL", item_id, detail))

    if not check_abaqus():
        print("SKIPPED: no Abaqus on this machine")
        print(json.dumps({"overall": "skipped",
                          "reason": "no Abaqus", "items": []},
                         ensure_ascii=False))
        return 0

    work = _fresh(ROOT / "artifacts" / "crack_check")
    (work / "build.py").write_text(
        _BUILD % {"W": W, "H": H, "A": A, "E": E, "NU": NU, "SIG": SIG,
                  "SEED": SEED, "N": CONTOURS},
        encoding="utf-8")
    built = _run(work, ["cae", "noGUI=build.py"])
    decks = [t for t in VARIANTS if (work / ("%s.inp" % t)).exists()]
    if len(decks) != len(VARIANTS):
        add("decks_written", False,
            "wrote %s of %s; stderr: %s"
            % (decks, list(VARIANTS), (built.stderr or "")[-400:]))
        print(json.dumps({"overall": "fail", "items": items},
                         ensure_ascii=False))
        return 1
    add("decks_written", True, "three decks: %s" % ", ".join(decks))

    # The card the whole thing hangs on. A deck without it solves happily and
    # produces no J at all, which would read as "no crack support" rather than
    # as a missing output request.
    deck = (work / "v_baseline.inp").read_text(encoding="utf-8", errors="replace")
    add("deck_carries_the_contour_card",
        "*Contour Integral" in deck,
        "`*Contour Integral` present in v_baseline.inp"
        if "*Contour Integral" in deck else "card missing from the deck")

    for tag in VARIANTS:
        _run(work, ["job=%s" % tag, "interactive", "cpus=1"])
    (work / "read.py").write_text(_READ % {"tags": list(VARIANTS)},
                                  encoding="utf-8")
    _run(work, ["python", "read.py"])
    jpath = work / "j_all.json"
    if not jpath.exists():
        add("j_read_back", False, "no j_all.json; the odbs were not readable")
        print(json.dumps({"overall": "fail", "items": items},
                         ensure_ascii=False))
        return 1
    data = json.loads(jpath.read_text(encoding="utf-8"))
    add("j_read_back", True,
        "read J from %d odb(s)" % len([t for t in VARIANTS if data.get(t)]))

    want = handbook_j()

    # 1. The physics. Everything below is about catching wrong answers, and
    #    none of it means anything unless the right answer is right.
    base = _contours(data["v_baseline"])
    err = (base[-1] - want) / want
    add("baseline_matches_the_handbook", abs(err) <= HANDBOOK_BAND,
        "J = %.4f vs handbook %.4f (%+.2f%%), contours %s"
        % (base[-1], want, 100 * err, " ".join("%.4f" % v for v in base)),
        measured_j=base[-1], handbook_j=want, error_fraction=err)

    add("baseline_is_path_independent", _spread(base) < 0.01,
        "contours 2..%d spread %.2e of their mean" % (len(base), _spread(base)),
        spread=_spread(base))

    # 2. The shipped extractor, on the real numbers, returning the real answer.
    got = extract_kpis._contour_integral_j(
        _FakeStep(data["v_baseline"]),
        {"name": "J_TIP", "type": "contour_integral_j"})
    add("extractor_returns_the_outermost_contour",
        abs(got - base[-1]) < 1e-9,
        "contour_integral_j -> %.6f, the outermost contour" % got)

    # 3. The two silent failures, each refused by the shipped extractor.
    noseam = _contours(data["v_noseam"])
    # Not `== 0.0`. The measured values are -1.4e-16 .. -1.3e-14: round-off
    # either side of nothing, and every one of them NEGATIVE. An equality test
    # here (and in the extractor, which is where it was first written) lets
    # them fall through to the sign check, and a missing seam gets reported as
    # a reversed q vector -- a confident wrong diagnosis. This gate caught that.
    all_zero = all(abs(v) <= 1e-12 for v in noseam)
    try:
        extract_kpis._contour_integral_j(
            _FakeStep(data["v_noseam"]),
            {"name": "J_TIP", "type": "contour_integral_j"})
        refused_zero = ""
    except ValueError as exc:
        refused_zero = str(exc)
    add("unseparated_crack_is_nothing_and_refused",
        all_zero and "SEPARATED" in refused_zero
        and "negative" not in refused_zero,
        "J = %s -- round-off, not a crack. Job COMPLETED with no warning; "
        "extractor refuses and names the missing SEAM rather than the sign, "
        "though every value is negative"
        % " ".join("%.2g" % v for v in noseam),
        contours=noseam)

    back = _contours(data["v_backwards_q"])
    try:
        extract_kpis._contour_integral_j(
            _FakeStep(data["v_backwards_q"]),
            {"name": "J_TIP", "type": "contour_integral_j"})
        refused_sign = ""
    except ValueError as exc:
        refused_sign = str(exc)
    add("reversed_q_is_negative_and_refused",
        all(v < 0 for v in back[1:]) and "negative" in refused_sign,
        "J = %.4f (right magnitude, wrong sign), job COMPLETED with no "
        "warning; extractor refuses on the sign" % back[-1],
        contours=back)

    # 4. The counterexample that decided the shape of the truth layer. If these
    #    two spreads were not equal, a convergence-only check would have been
    #    enough and this gate would be overbuilt. They are equal, so it is not.
    same = abs(_spread(back) - _spread(base)) < 1e-6
    add("path_independence_alone_would_have_passed_it", same,
        "the reversed-q run is as path-independent as the correct one "
        "(%.2e vs %.2e), so convergence cannot distinguish them -- the sign is "
        "the only tell" % (_spread(back), _spread(base)))

    # 5. The half this gate used to say it did not prove. Until #76 item 5 was
    #    a TRIP-WIRE -- "no shipped case authors a ContourIntegral, which is
    #    what makes that disclaimer accurate" -- because the dialect could not
    #    write one: parts were hard-coded THREE_D, and the crack line is one of
    #    the two edges the y=0 line becomes, which no selector form could name.
    #    Both are now writable, so the disclaimer is replaced by the
    #    measurement it was standing in for.
    spec_result = _solve_spec(work / "spec_authored")
    spec_j = (spec_result.get("kpis") or {}).get("J_TIP")
    spec_ok = (spec_result.get("status") == "COMPLETED"
               and isinstance(spec_j, (int, float))
               and abs(spec_j - base[-1]) / abs(base[-1]) < 1.0e-3)
    add("spec_authored_j_matches_the_scripted_baseline", spec_ok,
        "the v2 dialect authored the same rig and got J = %s against this "
        "gate's own CAE script at %s (status %s). Same model, not a similar "
        "one -- the comparison is against the scripted baseline rather than "
        "the handbook, because the handbook would not notice a model that was "
        "merely close." % (spec_j, base[-1], spec_result.get("status")),
        measured_j=spec_j, reference_j=base[-1])

    # 6. And the truth layer has to survive the change of route. Same spec,
    #    seam feature removed: the job still COMPLETES, J is round-off, and the
    #    extractor must refuse it -- reaching the number through the dialect
    #    must not be a way around the checks that made #75 worth doing.
    seamless = _solve_spec(work / "spec_authored_noseam", seam=False)
    missing = [m for m in (seamless.get("kpis_missing") or [])
               if m.get("name") == "J_TIP"]
    reason = missing[0]["reason"] if missing else ""
    add("spec_authored_without_a_seam_is_still_refused",
        seamless.get("status") == "COMPLETED" and bool(missing)
        and ("round-off" in reason or "seam" in reason.lower()
             or "negligible" in reason.lower()),
        "seam removed: job %s, J_TIP not delivered, extractor said %r"
        % (seamless.get("status"), reason[:200]),
        readback=reason[:300])

    failed = [i for i in items if i["status"] == "fail"]
    overall = "fail" if failed else "pass"
    elapsed = round(time.time() - started, 1)
    print("\nRESULT: %s (%d/%d) in %.1fs"
          % (overall.upper(), len(items) - len(failed), len(items), elapsed))
    print(json.dumps({"overall": overall, "seconds": elapsed,
                      "abaqus_release": detect_abaqus_release(),
                      "handbook_j": want, "items": items},
                     ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
