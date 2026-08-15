# -*- coding: utf-8 -*-
"""
export_odb_mesh.py
------------------
Tool: export_odb_mesh(odb_path) -> {mesh_file}

Exports the exterior surface mesh + nodal fields from an .odb as a compact
JSON the browser viewport renders with three.js:

  {
    "format": "abaqus-agent-mesh/2",
    "nodes": [x,y,z, ...],                 # flat, used nodes only
    "tris": [i,j,k, ...],                  # flat, 0-based into nodes
    "fields": {"mises": {"values": [...], "min": m, "max": M}, "u_mag": {...}},
    "displacement": [ux,uy,uz, ...],       # flat, same node order
    "instances": [{"name","tri_start","tri_count","node_start","node_count"}],
    "is_modal": false, "mode": null, "frequency": null,
    "bbox": [[minx,miny,minz],[maxx,maxy,maxz]]
  }

Designed to run under: abaqus python post/export_odb_mesh.py -- <odb> <out.json>
The face-topology helpers are pure Python and unit-tested without Abaqus.

A NODE LABEL IS NOT A KEY. Every part instance in an ODB numbers its nodes
from 1, so labels collide across instances, and /1 of this format keyed
everything by the bare label. Measured on the bearing-block acceptance ODB
(3 instances, 57030 nodes): only 37622 distinct labels, so 19408 nodes were
unreachable -- Housing, written last, overwrote every coordinate Bushing and
Cap had. Worse than the overwrite, `exterior_faces` counts a face by its
sorted node labels, so two instances' faces collided into one key and BOTH
were dropped as interior: 10590 real exterior faces, of which the bare-label
version found 3928. Everything here is therefore keyed by the pair
(instance name, node label), which the field values supply directly --
measured on the same ODB, all 57030 U values carry `.instance` and none is
None.

NAMES IN `instances` ARE THE ODB'S, NOT THE SPEC'S. Measured: the ODB answers
BUSHING / CAP / HOUSING while the preview tree carries Bushing / Cap /
Housing. The two name spaces are not comparable without folding case, and
nothing here folds it -- inventing a mapping would be a guess about which end
is authoritative. Anything correlating this array with the model tree has to
say so explicitly.
"""

from __future__ import print_function

import json
import sys

MAX_ELEMENTS = 300000

# Corner-face templates by element family (corner nodes only; midside ignored)
_HEX_FACES = ((0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
              (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0))
_TET_FACES = ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3))
_WEDGE_FACES = ((0, 2, 1), (3, 4, 5), (0, 3, 5, 2), (0, 1, 4, 3), (1, 2, 5, 4))


def element_faces(el_type, connectivity):
    """Return corner-node faces for one element (node labels, not indices).

    Solid families emit their boundary faces; shells/2D elements are their own
    face. Unknown types return [] rather than guessing.
    """
    t = str(el_type).upper()
    n = list(connectivity)
    if t.startswith("C3D8") or t.startswith("C3D20"):
        return [tuple(n[i] for i in face) for face in _HEX_FACES]
    if t.startswith("C3D4") or t.startswith("C3D10"):
        return [tuple(n[i] for i in face) for face in _TET_FACES]
    if t.startswith("C3D6") or t.startswith("C3D15"):
        return [tuple(n[i] for i in face) for face in _WEDGE_FACES]
    if t.startswith("S4") or t.startswith("CPS4") or t.startswith("CPE4") \
            or t.startswith("M3D4") or t.startswith("CAX4"):
        return [tuple(n[:4])]
    if t.startswith("S3") or t.startswith("CPS3") or t.startswith("CPE3") \
            or t.startswith("M3D3") or t.startswith("CAX3"):
        return [tuple(n[:3])]
    return []


def exterior_faces(all_faces):
    """Faces whose node set appears exactly once are on the exterior.

    Shell/2D faces (from single-face elements) always appear once and are
    therefore kept, which is exactly what we want.
    """
    counts = {}
    for face in all_faces:
        key = tuple(sorted(face))
        counts[key] = counts.get(key, 0) + 1
    return [face for face in all_faces if counts[tuple(sorted(face))] == 1]


def triangulate(face):
    """Fan-triangulate a 3/4-node face into triangles."""
    if len(face) == 3:
        return [face]
    if len(face) == 4:
        return [(face[0], face[1], face[2]), (face[0], face[2], face[3])]
    return []


def build_surface(node_coords, elements):
    """Pure assembly: (label->xyz, [(el_type, connectivity), ...]) ->
    (flat_nodes, flat_tris, ordered_labels).

    Only nodes referenced by exterior triangles are emitted; indices are
    remapped to that compact order.
    """
    faces = []
    for el_type, conn in elements:
        faces.extend(element_faces(el_type, conn))
    tris = []
    for face in exterior_faces(faces):
        tris.extend(triangulate(face))

    label_to_index = {}
    ordered_labels = []
    flat_tris = []
    for tri in tris:
        for label in tri:
            if label not in label_to_index:
                label_to_index[label] = len(ordered_labels)
                ordered_labels.append(label)
            flat_tris.append(label_to_index[label])

    flat_nodes = []
    for label in ordered_labels:
        xyz = node_coords[label]
        flat_nodes.extend([float(xyz[0]), float(xyz[1]),
                           float(xyz[2]) if len(xyz) > 2 else 0.0])
    return flat_nodes, flat_tris, ordered_labels


def label_scope(label):
    """Instance name of a scoped label, or None for a bare one."""
    if isinstance(label, tuple) and len(label) == 2:
        return label[0]
    return None


def group_by_instance(flat_tris, ordered_labels):
    """Per-instance triangle/node ranges over the flat arrays.

    Returns {"groups": [...], "contiguous": bool, "cross_instance_tris": int}.

    Triangles come out grouped by instance because the exporter appends
    elements instance by instance and `exterior_faces` preserves that order --
    but "come out grouped" is a property of code somebody may change, so it is
    verified here rather than assumed. If it fails, no ranges are emitted: a
    wrong range draws the wrong part in the wrong colour, which is the class of
    bug this whole change exists to remove.

    `cross_instance_tris` must be 0. A triangle whose three nodes do not agree
    on an instance can only come from a face built out of colliding labels,
    i.e. the /1 bug returning.

    Bare (unscoped) labels report no grouping instead of inventing one.
    """
    scopes = []
    for label in ordered_labels:
        scopes.append(label_scope(label))
    empty = {"groups": [], "contiguous": True, "cross_instance_tris": 0}
    if not scopes or None in scopes:
        return empty

    cross = 0
    owners = []
    for i in range(0, len(flat_tris) - 2, 3):
        a = scopes[flat_tris[i]]
        b = scopes[flat_tris[i + 1]]
        c = scopes[flat_tris[i + 2]]
        if a != b or b != c:
            cross += 1
            owners.append(None)
        else:
            owners.append(a)

    runs = []
    for index in range(len(owners)):
        owner = owners[index]
        if runs and runs[len(runs) - 1][0] == owner:
            runs[len(runs) - 1][2] += 1
        else:
            runs.append([owner, index, 1])

    seen = {}
    contiguous = True
    for run in runs:
        if run[0] in seen:
            contiguous = False
        seen[run[0]] = True
    if cross or not contiguous:
        return {"groups": [], "contiguous": contiguous,
                "cross_instance_tris": cross}

    groups = []
    for owner, tri_start, tri_count in runs:
        lo = None
        hi = None
        for i in range(tri_start * 3, (tri_start + tri_count) * 3):
            idx = flat_tris[i]
            if lo is None or idx < lo:
                lo = idx
            if hi is None or idx > hi:
                hi = idx
        groups.append({
            "name": owner,
            "tri_start": tri_start,
            "tri_count": tri_count,
            "node_start": lo if lo is not None else 0,
            "node_count": (hi - lo + 1) if lo is not None else 0,
        })
    return {"groups": groups, "contiguous": True, "cross_instance_tris": 0}


def scope_instance_geometry(instance_rows, max_elements=MAX_ELEMENTS):
    """Rows of (instance name, nodes, elements) -> (node_coords, elements).

    Nodes duck-type the ODB's: `.label` and `.coordinates`. Elements: `.type`
    and `.connectivity`. Keeping this out of `_inner_main` is the whole point --
    the ODB walk is where a bare label was used as a key, and a function that
    only runs inside `abaqus python` can never be caught by the test suite.
    With this split a fake instance whose labels start at 1, exactly as a real
    one's do, is enough.

    Raises ValueError past `max_elements`, carrying the count, so the caller
    can report the same sentence it always did.
    """
    node_coords = {}
    elements = []
    total = 0
    for name, nodes, els in instance_rows:
        for node in nodes:
            node_coords[(name, node.label)] = node.coordinates
        # Count before materialising. The cap exists so an oversized model is
        # refused instead of being built, and a cap that only fires after the
        # elements are already in the list has spent exactly what it was there
        # to save.
        try:
            count = len(els)
        except TypeError:
            els = list(els)
            count = len(els)
        total += count
        if total > max_elements:
            raise ValueError("mesh too large: %d elements > %d"
                             % (total, max_elements))
        for el in els:
            elements.append((el.type, [(name, label) for label in el.connectivity]))
    return node_coords, elements


def pack_field(per_label, ordered_labels):
    """Map {label: value} onto the ordered node list; None where missing."""
    values = []
    vmin = None
    vmax = None
    for label in ordered_labels:
        v = per_label.get(label)
        if v is None:
            values.append(0.0)
            continue
        v = float(v)
        values.append(v)
        if vmin is None or v < vmin:
            vmin = v
        if vmax is None or v > vmax:
            vmax = v
    return {"values": values, "min": vmin or 0.0, "max": vmax or 0.0}


# ---------------------------------------------------------------------------
# Outer-agent API (subprocess caller)
# ---------------------------------------------------------------------------

def export_odb_mesh(odb_path, workdir=None, timeout=300):
    """Invoke 'abaqus python' to export the surface mesh JSON. Best-effort:
    returns {"mesh_file": str|None, "errors": [...]}."""
    import subprocess
    from pathlib import Path

    odb_path = Path(odb_path).resolve()
    workdir = Path(workdir) if workdir else odb_path.parent
    out_file = workdir / "mesh.json"
    this_script = Path(__file__).resolve()

    from tools.abaqus_cmd import get_abaqus_cmd
    try:
        cmd = [get_abaqus_cmd(), "python", str(this_script),
               "--", str(odb_path), str(out_file)]
    except Exception as e:
        return {"mesh_file": None, "errors": [str(e)]}

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(workdir),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError:
        return {"mesh_file": None, "errors": ["'abaqus' not found in PATH"]}
    except subprocess.TimeoutExpired:
        return {"mesh_file": None, "errors": ["mesh export timed out after %ss" % timeout]}

    if out_file.exists():
        return {"mesh_file": str(out_file), "errors": []}
    return {"mesh_file": None,
            "errors": [(proc.stderr or proc.stdout or "no mesh.json produced")[-1500:]]}


# ---------------------------------------------------------------------------
# Abaqus-runtime inner script (Py2.7: no f-strings, no pathlib)
# ---------------------------------------------------------------------------

def _pick_frame(step):
    """Last frame for static/dynamic; first real mode for frequency steps."""
    frames = step.frames
    for frame in frames:
        if getattr(frame, "mode", None) == 1:
            return frame, True
    return frames[len(frames) - 1], False


def _value_key(v):
    """(instance name, node label) for a field value, or None if unattributable.

    A value with no instance belongs to the root assembly and matches no
    instance node, so it is dropped by the caller and counted -- guessing an
    instance for it would put a number on the wrong part.
    """
    inst = getattr(v, "instance", None)
    if inst is None:
        return None
    return (inst.name, v.nodeLabel)


def _collect_nodal_u(frame):
    u_mag = {}
    disp = {}
    unscoped = 0
    try:
        field = frame.fieldOutputs["U"]
    except Exception:
        return u_mag, disp, unscoped
    for v in field.values:
        key = _value_key(v)
        if key is None:
            unscoped += 1
            continue
        data = v.data
        ux = float(data[0])
        uy = float(data[1]) if len(data) > 1 else 0.0
        uz = float(data[2]) if len(data) > 2 else 0.0
        disp[key] = (ux, uy, uz)
        u_mag[key] = (ux * ux + uy * uy + uz * uz) ** 0.5
    return u_mag, disp, unscoped


def _collect_nodal_mises(frame):
    """Average ELEMENT_NODAL Mises per (instance, node label)."""
    unscoped = 0
    try:
        from abaqusConstants import ELEMENT_NODAL
        field = frame.fieldOutputs["S"].getSubset(position=ELEMENT_NODAL)
    except Exception:
        return {}, unscoped
    sums = {}
    counts = {}
    for v in field.values:
        key = _value_key(v)
        if key is None:
            unscoped += 1
            continue
        sums[key] = sums.get(key, 0.0) + float(v.mises)
        counts[key] = counts.get(key, 0) + 1
    out = {}
    for key in sums:
        out[key] = sums[key] / counts[key]
    return out, unscoped


def _inner_main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    if len(args) < 2:
        print("Usage: abaqus python export_odb_mesh.py -- <odb> <out.json>")
        sys.exit(1)
    odb_path, out_path = args[0], args[1]

    import odbAccess
    try:
        odb = odbAccess.openOdb(path=odb_path, readOnly=True)
    except Exception:
        upgraded = odb_path.replace(".odb", "_upgraded.odb")
        odbAccess.upgradeOdb(existingOdbPath=odb_path, upgradedOdbPath=upgraded)
        odb = odbAccess.openOdb(path=upgraded, readOnly=True)

    # Keys are (instance name, node label) throughout -- see the module
    # docstring for the measurement that forced it.
    rows = []
    for inst_name in odb.rootAssembly.instances.keys():
        inst = odb.rootAssembly.instances[inst_name]
        rows.append((inst_name, inst.nodes, inst.elements))
    try:
        node_coords, elements = scope_instance_geometry(rows)
    except ValueError as exc:
        print(str(exc))
        sys.exit(2)

    step_names = list(odb.steps.keys())
    step = odb.steps[step_names[len(step_names) - 1]]
    frame, is_modal = _pick_frame(step)

    flat_nodes, flat_tris, ordered_labels = build_surface(node_coords, elements)

    u_mag, disp, u_unscoped = _collect_nodal_u(frame)
    fields = {}
    if u_mag:
        fields["u_mag"] = pack_field(u_mag, ordered_labels)
    mises, s_unscoped = _collect_nodal_mises(frame)
    if mises:
        fields["mises"] = pack_field(mises, ordered_labels)

    flat_disp = []
    for label in ordered_labels:
        d = disp.get(label, (0.0, 0.0, 0.0))
        flat_disp.extend([d[0], d[1], d[2]])

    grouping = group_by_instance(flat_tris, ordered_labels)

    xs = flat_nodes[0::3]
    ys = flat_nodes[1::3]
    zs = flat_nodes[2::3]
    mesh = {
        "format": "abaqus-agent-mesh/2",
        "step": step_names[len(step_names) - 1],
        "is_modal": bool(is_modal),
        "mode": getattr(frame, "mode", None) if is_modal else None,
        "frequency": getattr(frame, "frequency", None) if is_modal else None,
        "node_count": len(ordered_labels),
        "tri_count": len(flat_tris) // 3,
        "nodes": flat_nodes,
        "tris": flat_tris,
        "fields": fields,
        "displacement": flat_disp,
        "instances": grouping["groups"],
        # Self-checks travel with the data. Non-zero means the label scoping
        # broke somewhere upstream, and a reader should say so rather than
        # draw a confident picture of the wrong assembly.
        "cross_instance_tris": grouping["cross_instance_tris"],
        "unscoped_field_values": u_unscoped + s_unscoped,
        "bbox": [[min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]] if xs else [[0, 0, 0], [0, 0, 0]],
    }
    with open(out_path, "w") as f:
        json.dump(mesh, f, separators=(",", ":"))
    print("MESH_WRITTEN: %s (%d nodes, %d tris, %d instances, %d cross, %d unscoped)"
          % (out_path, mesh["node_count"], mesh["tri_count"],
             len(mesh["instances"]), mesh["cross_instance_tris"],
             mesh["unscoped_field_values"]))
    odb.close()


if __name__ == "__main__":
    _inner_main()
