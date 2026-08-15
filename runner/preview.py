"""The JSON the 3D preview reads, emitted as py2.7 that dumps it from the kernel.

Distinct from everything else in the generator: the deck emitters produce the
model Abaqus will solve, and this produces a description of that model for the
browser -- node coordinates, region names, the surfaces an interaction pairs,
which conditions belong to which step. Nothing here can change what gets
solved, which is why it can live in its own file without the deck ever
noticing.

It was 589 lines at the tail of build_v2.py. The caps at the top are the whole
safety story: a preview that tries to serialise a 2-million-element assembly
hangs the browser rather than failing, so the payload is bounded before it is
built, not after.
"""

from __future__ import annotations

import re

from runner.spec_base import _is_generic

# Node/element ceiling for the preview dump. Above it the dump is skipped
# entirely rather than truncated: half an assembly drawn without saying so is
# a wrong picture, and the .inp fallback can still produce something honest.
PREVIEW_ELEMENT_CAP = 200000

# Ceilings for the named-region walk. A tie surface on a preview mesh is a few
# hundred nodes and a deck names a handful of regions, so neither of these is
# reachable by anything this generator writes. They exist because `_gset` builds
# whatever the spec selects, and a set of the whole model would make the preview
# dump the largest file in the run directory. Both report themselves in the
# payload: a region that was cut short says so rather than reading as complete.
PREVIEW_REGION_CAP = 200

PREVIEW_REGION_NODE_CAP = 20000

# Ceiling for the geometric-face walk (the viewport's face-level pick). Way
# above anything this generator has built — bearing_block is ~50 faces — and
# a dump that hits it says how many faces it dropped rather than shipping a
# model where some faces silently cannot be clicked.
PREVIEW_FACE_CAP = 512

# What `_generic_call` skips when it compiles keywords, so the region-name
# re-derivation below walks exactly the keys the call itself walks.
_PREVIEW_RESERVED = ("call", "as", "creates", "target", "expect")

# The BC shorthand's `type:` and the Abaqus method `_bc` turns it into. Written
# out rather than inferred: a tree row that names a call the deck does not make
# is worse than a row that says nothing.
_PREVIEW_BC_CALLS = {
    "encastre": "EncastreBC",
    "pinned": "PinnedBC",
    "symmetry_x": "XsymmBC",
    "symmetry_y": "YsymmBC",
    "symmetry_z": "ZsymmBC",
    "displacement": "DisplacementBC",
}

def _preview_plain(value):
    """The string a spec wrote, whether it wrote it bare or as {literal: ...}."""
    if isinstance(value, dict) and "literal" in value:
        value = value["literal"]
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    return str(value)

def _preview_region_names(where: str, entry: dict, form: str) -> list[str]:
    """The names `_arg_surface` / `_arg_set` will give this call's regions.

    A re-derivation of naming that lives in `_arg_surface`, and it is only
    allowed to be one because the answer is checked against the finished
    assembly before it is published: the emitted dump keeps a name only when
    `a.surfaces` / `a.sets` really holds it, and reports the rest in `degraded`.
    Drift here therefore costs a missing tree row, never a row pointing at
    geometry the model has not got.

    Walks the same keys `_generic_call` compiles, and recurses into lists the
    same way `_arg_expr` does. It does not descend into `new:`, because
    `_arg_mapping` does not pass the surface/set collectors down that branch --
    a nested constructor cannot create an assembly region.
    """
    found: list[str] = []

    def walk(key, value):
        if isinstance(value, (list, tuple)):
            for item in value:
                walk(key, item)
            return
        if not isinstance(value, dict) or form not in value:
            return
        name = str(value.get("name") or "%s_%s" % (
            re.sub(r"[^A-Za-z0-9]+", "_", where).strip("_"), key)).upper()
        if name not in found:
            found.append(name)

    for key in sorted(entry):
        if key in _PREVIEW_RESERVED:
            continue
        walk(str(key), entry[key])
    return found

def _preview_interactions(spec: dict, degraded: list) -> list[dict]:
    """One row per declared interaction: what it is, and what it joined."""
    rows = []
    for index, inter in enumerate(spec.get("interactions", []) or []):
        where = "interaction %d" % (index + 1)
        if "call" not in inter:
            name = str(inter.get("name") or "Interaction-%d" % (index + 1))
            rows.append({
                "name": name,
                "kind": str(inter.get("type") or ""),
                "call": "Tie" if inter.get("type") == "tie"
                        else "SurfaceToSurfaceContactStd",
                "surfaces": [name.upper() + "_MAIN", name.upper() + "_SEC"],
            })
            continue

        call = str(inter["call"])
        surfaces = _preview_region_names(where, inter, "surface")
        gap = (inter.get("expect") or {}).get("gap") or {}
        stated = gap.get("between") if isinstance(gap, dict) else None
        if isinstance(stated, list) and len(stated) == 2:
            # `between:` names the pair outright, and it is the pair
            # `_expect_gap` measures — so it beats anything derived from the
            # keyword order.
            surfaces = [str(item).upper() for item in stated]
        elif gap and len(surfaces) != 2:
            degraded.append(
                "%s 声明了 expect.gap，但预览这一侧只认出 %d 个面名，"
                "模型树里这条交互点不出接触面"
                % (_preview_plain(inter.get("name")) or where, len(surfaces)))
        rows.append({"name": _preview_plain(inter.get("name")) or where,
                     "kind": call, "call": call, "surfaces": surfaces})
    return rows

def _preview_conditions(spec: dict, degraded: list) -> list[dict]:
    """One row per BC / load / field, from both forms the spec may use."""
    rows = []
    for index, entry in enumerate(spec.get("conditions", []) or []):
        where = "condition %d" % (index + 1)
        call = str(entry.get("call") or "")
        rows.append({
            "name": _preview_plain(entry.get("name")) or where,
            "call": call,
            "step": _preview_plain(entry.get("createStepName")),
            "sets": _preview_region_names(where, entry, "set"),
            "surfaces": _preview_region_names(where, entry, "surface"),
        })
    rows.extend(_preview_step_conditions(spec, degraded))
    return rows

def _preview_step_conditions(spec: dict, degraded: list) -> list[dict]:
    """The `steps[].bcs` / `steps[].loads` shorthand, which is conditions too.

    Left out, the tree would show a two-plate tie deck as having no boundary
    conditions at all -- every case in this repo that uses the shorthand writes
    every one of its BCs there. A name that reappears in a later step is ONE
    Abaqus object whose values change (see `_reuse_check`), so it contributes
    one row, not two.
    """
    rows: list[dict] = []
    seen_bcs: set = set()
    seen_loads: set = set()
    for step_spec in spec.get("steps") or []:
        if _is_generic(step_spec):
            continue
        step_name = str(step_spec.get("name") or "?")
        for index, bc in enumerate(step_spec.get("bcs", []) or []):
            name = str(bc.get("name") or "BC-%d" % (index + 1))
            if name in seen_bcs:
                continue
            seen_bcs.add(name)
            kind = str(bc.get("type") or "")
            call = _PREVIEW_BC_CALLS.get(kind)
            if call is None:
                degraded.append(
                    "边界条件 %s 的 type=%s 这一侧不认识，模型树只显示名字和区域"
                    % (name, kind or "?"))
            rows.append({
                "name": name, "call": call or "",
                # Every BC but a displacement is created in Initial; see `_bc`
                # on why an unrestrained Initial step reads as a singularity
                # rather than as the missing BC it is.
                "step": step_name if kind == "displacement" else "Initial",
                "sets": ["BC_%s" % name.upper()], "surfaces": []})
        for index, load in enumerate(step_spec.get("loads", []) or []):
            name = str(load.get("name") or "Load-%d" % (index + 1))
            if name in seen_loads:
                continue
            seen_loads.add(name)
            pressure = str(load.get("type") or "") == "pressure"
            region = "LOAD_%s" % name.upper()
            rows.append({
                "name": name,
                "call": "Pressure" if pressure else "ConcentratedForce",
                "step": step_name,
                # A pressure acts on a SURFACE and a concentrated force on a
                # SET; `_load` builds one or the other under the same name.
                "sets": [] if pressure else [region],
                "surfaces": [region] if pressure else []})
    return rows

def _preview_assembly_facts(spec: dict) -> dict:
    """What the spec declared, as the model tree wants to show it.

    Read off the spec rather than off the finished model because the finished
    model does not answer the question in a form that can be trusted: a Region
    read back from `m.loads[...]` does not carry the name of the set it was
    built from, and guessing one is exactly the confidently-wrong answer this
    payload exists to avoid. What the spec cannot say -- an upper bound on how
    far apart a pair ended up -- is measured in the kernel instead. A bound and
    not the separation: `_surface_gap` is node-to-node and Abaqus ties
    node-to-surface, and bearing_block's BoreTie reads 2.389 across a pair of
    coincident cylinders it bonds under a tolerance of 0.05. See
    post/parse_inp._overlay_interactions, which carries that number out.
    """
    degraded: list[str] = []
    return {"interactions": _preview_interactions(spec, degraded),
            "conditions": _preview_conditions(spec, degraded),
            "degraded": degraded}

def _preview_dump(spec: dict, model: str) -> str:
    """Dump the assembly for the 3D preview: meshes, regions, and what joins them.

    The instance meshes come from CAE rather than from the .inp text, where an
    *Instance carries a translation line and a rotation line and the order they
    compose in is exactly the sort of thing that produces a confident, wrong
    picture. CAE already knows the answer, so it is asked instead of guessed.

    post/parse_inp.py still learns the transform, because a user-supplied
    custom_inp deck arrives with no CAE session attached — but this dump is the
    reference the parser is checked against.

    The named regions are asked for the same way and for the same reason. The
    front end has to draw a model tree and show which faces a tie or a contact
    pair joined, and neither is derivable from triangles alone.

    Best effort throughout, in the same way the mesh dump already is: a preview
    that cannot be built must not fail a build. Unlike the mesh dump, what it
    could not collect is written into the payload as `degraded` — a preview that
    quietly shows three of a model's five surfaces reads as a model with three.
    """
    import json

    return """
# --- Preview dump (best effort; never fails the build) ----------------------
try:
    import json as _pv_json
    _pv_degraded = []

    def _pv_txt(_pv_value):
        \"\"\"Anything -> text, without assuming which Python the kernel is.

        The 2021 kernel is Python 2.7 and the 2024 kernel is 3.10, and this file
        has to read the same in both. `str()` on a Chinese message is a
        UnicodeEncodeError in one of them.\"\"\"
        try:
            if isinstance(_pv_value, bytes):
                return _pv_value.decode('utf-8', 'replace')
            return u'' + _pv_value
        except Exception:
            pass
        try:
            return repr(_pv_value).decode('utf-8', 'replace')
        except Exception:
            return repr(_pv_value)

    def _pv_key(_pv_value):
        \"\"\"A name in the type an Abaqus repository is keyed by.

        Region names arrive from the JSON literal below as text, and on 2.7
        text is `unicode` while `a.surfaces` is keyed by `str`. Every one of
        them is an identifier Abaqus accepted, so this cannot lose anything;
        anything that somehow will not convert is left alone and simply fails
        the membership test below, which is the safe direction.\"\"\"
        try:
            return str(_pv_value)
        except Exception:
            return _pv_value

    _pv_instances = []
    _pv_total = 0
    _pv_truncated = False
    for _pv_name in sorted(a.instances.keys()):
        _pv_inst = a.instances[_pv_name]
        _pv_total = _pv_total + len(_pv_inst.elements)
        if _pv_total > %(element_cap)d:
            _pv_truncated = True
            break
        # connectivity holds 0-based INDICES into this instance's node array,
        # not labels, so an index->label table is needed to emit label-keyed
        # connectivity the way post/export_odb_mesh expects it.
        _pv_index_to_label = [int(_n.label) for _n in _pv_inst.nodes]
        _pv_nodes = []
        for _pv_i, _pv_n in enumerate(_pv_inst.nodes):
            _pv_c = _pv_n.coordinates
            _pv_nodes.append((_pv_index_to_label[_pv_i], float(_pv_c[0]),
                              float(_pv_c[1]), float(_pv_c[2])))
        _pv_elems = []
        for _pv_el in _pv_inst.elements:
            _pv_elems.append((str(_pv_el.type),
                              [_pv_index_to_label[int(_pv_c)]
                               for _pv_c in _pv_el.connectivity]))
        # Geometric faces, for the viewport's face-level pick. One row per CAE
        # face that has mesh nodes on it -- the preview draws the mesh, so a
        # face nothing is meshed on cannot be clicked and is not shipped.
        # Every number here is MEASURED off the instance in assembly space:
        # the bbox is exactly what a `face@box=` selector resolves against
        # (an instance reports its box in assembly space -- measured, see
        # core/selectors.py). radius/normal are probed the way the selector
        # runtime does: getRadius() raising IS the "not cylindrical" answer.
        _pv_faces = []
        _pv_faces_dropped = 0
        try:
            _pv_face_seq = _pv_inst.faces
            _pv_face_count = len(_pv_face_seq)
        except Exception:
            _pv_face_seq = None
            _pv_face_count = 0
        for _pv_fi in range(_pv_face_count):
            if len(_pv_faces) >= %(face_cap)d:
                _pv_faces_dropped = _pv_faces_dropped + (
                    _pv_face_count - _pv_fi)
                break
            try:
                _pv_face = _pv_face_seq[_pv_fi]
                _pv_fnodes = _pv_face.getNodes()
            except Exception:
                _pv_faces_dropped = _pv_faces_dropped + 1
                continue
            if not _pv_fnodes:
                continue
            _pv_flabels = []
            for _pv_n in _pv_fnodes:
                if len(_pv_flabels) >= %(node_cap)d:
                    break
                _pv_flabels.append(int(_pv_n.label))
            _pv_frow = {'face': _pv_fi,
                        'node_labels': _pv_flabels,
                        'node_total': len(_pv_fnodes),
                        'capped': len(_pv_fnodes) > len(_pv_flabels)}
            try:
                _pv_fb = _pv_face_seq[_pv_fi:_pv_fi + 1].getBoundingBox()
                _pv_frow['bbox'] = [
                    [float(_pv_fb['low'][0]), float(_pv_fb['low'][1]),
                     float(_pv_fb['low'][2])],
                    [float(_pv_fb['high'][0]), float(_pv_fb['high'][1]),
                     float(_pv_fb['high'][2])]]
            except Exception:
                # Without a measured bbox no selector can be generated from
                # this face; ship it without one and parse_inp drops it with
                # a count instead of a guess.
                pass
            try:
                _pv_frow['radius'] = float(_pv_face.getRadius())
            except Exception:
                pass
            try:
                _pv_fn = _pv_face.getNormal()
                _pv_frow['normal'] = [float(_pv_fn[0]), float(_pv_fn[1]),
                                      float(_pv_fn[2])]
            except Exception:
                pass
            try:
                _pv_frow['area'] = float(_pv_face.getSize(printResults=False))
            except Exception:
                pass
            _pv_faces.append(_pv_frow)
        _pv_instances.append({'name': str(_pv_name),
                              'part': str(_pv_inst.partName),
                              'nodes': _pv_nodes,
                              'elements': _pv_elems,
                              'faces': _pv_faces,
                              'faces_dropped': _pv_faces_dropped})
    if _pv_truncated:
        _pv_instances = []

    # Label -> owning instance, for the case where a node cannot say which
    # instance it is on. Only usable when exactly one instance holds every
    # label of a region: two instances of one part both number their nodes
    # from 1, so a match against several is not an answer, it is a coin toss.
    _pv_owner_labels = []
    for _pv_inst_row in _pv_instances:
        _pv_owned = {}
        for _pv_row in _pv_inst_row['nodes']:
            _pv_owned[_pv_row[0]] = 1
        _pv_owner_labels.append((_pv_inst_row['name'], _pv_owned))

    def _pv_collect(_pv_holder, _pv_rname, _pv_what):
        \"\"\"One assembly surface or set: whose it is, and which nodes it holds.

        Node LABELS, not indices. post/parse_inp.py rebuilds the preview node
        order itself (build_surface renumbers into a compact per-part order),
        so an index emitted here would be an index into a different array than
        the one the viewport ends up drawing.\"\"\"
        try:
            _pv_ns = _pv_holder.nodes
            _pv_count = len(_pv_ns)
        except Exception as _pv_ex:
            _pv_degraded.append(_pv_what + u' ' + _pv_txt(_pv_rname)
                                + u' 读不到节点，模型树里点不开它：'
                                + _pv_txt(_pv_ex))
            return None
        _pv_labels = []
        _pv_owners = {}
        _pv_asked = True
        for _pv_n in _pv_ns:
            if len(_pv_labels) >= %(node_cap)d:
                break
            _pv_labels.append(int(_pv_n.label))
            if _pv_asked:
                try:
                    _pv_iname = _pv_n.instanceName
                except Exception:
                    _pv_iname = None
                # Empty is an answer Abaqus really gives -- a node of an orphan
                # mesh carried on the assembly belongs to no instance -- and
                # str() would turn it into an owner called 'None' that every
                # later lookup would then miss without saying why.
                if _pv_iname:
                    _pv_owners[str(_pv_iname)] = 1
                else:
                    _pv_asked = False
        _pv_capped = _pv_count > len(_pv_labels)
        _pv_owner = ''
        if not _pv_labels:
            # Not the same as "could not attribute it": the region exists and
            # holds nothing. A part that has not been meshed yet gives exactly
            # this, and it is also what an over-narrow selector gives.
            _pv_degraded.append(
                _pv_what + u' ' + _pv_txt(_pv_rname)
                + u' 一个节点都没有（部件可能还没划网格），模型树里点不出它')
            return {'name': _pv_rname, 'instance': '', 'node_labels': [],
                    'node_total': _pv_count, 'capped': False}
        if _pv_asked and len(_pv_owners) == 1:
            _pv_owner = list(_pv_owners.keys())[0]
        elif _pv_asked and len(_pv_owners) > 1:
            _pv_degraded.append(
                _pv_what + u' ' + _pv_txt(_pv_rname)
                + u' 横跨多个实例，预览按单个实例画，所以不画它')
        else:
            _pv_hits = []
            for _pv_iname, _pv_owned in _pv_owner_labels:
                _pv_all = True
                for _pv_l in _pv_labels:
                    if _pv_l not in _pv_owned:
                        _pv_all = False
                        break
                if _pv_all:
                    _pv_hits.append(_pv_iname)
            if len(_pv_hits) == 1:
                _pv_owner = _pv_hits[0]
            else:
                _pv_degraded.append(
                    _pv_what + u' ' + _pv_txt(_pv_rname)
                    + u' 认不出属于哪个实例（节点号在多个实例里都存在），'
                    + u'不猜，模型树里这一项没有高亮')
        if _pv_capped:
            _pv_degraded.append(
                _pv_what + u' ' + _pv_txt(_pv_rname) + u' 有 '
                + _pv_txt(_pv_count) + u' 个节点，预览只收了前 '
                + _pv_txt(len(_pv_labels)) + u' 个，高亮是不完整的')
        return {'name': _pv_rname, 'instance': _pv_owner,
                'node_labels': _pv_labels, 'node_total': _pv_count,
                'capped': _pv_capped}

    _pv_all_surfaces = sorted(a.surfaces.keys())
    _pv_all_sets = sorted(a.sets.keys())
    _pv_surfaces = []
    _pv_sets = []
    for _pv_names, _pv_repo, _pv_into, _pv_what in (
            (_pv_all_surfaces, a.surfaces, _pv_surfaces, u'面'),
            (_pv_all_sets, a.sets, _pv_sets, u'集合')):
        if len(_pv_names) > %(region_cap)d:
            _pv_degraded.append(
                u'装配有 ' + _pv_txt(len(_pv_names)) + u' 个' + _pv_what
                + u'，预览只收了前 ' + _pv_txt(%(region_cap)d) + u' 个')
            _pv_names = _pv_names[:%(region_cap)d]
        for _pv_rname in _pv_names:
            _pv_got = _pv_collect(_pv_repo[_pv_rname], _pv_rname, _pv_what)
            if _pv_got is not None:
                _pv_into.append(_pv_got)

    # What the spec declared, compiled on the host side. The names in it are a
    # re-derivation of the ones `_gsurface` / `_gset` used, so every one is
    # checked against the assembly before it goes out: a tree row that points
    # at a surface the model has not got is the wrong answer, an absent row
    # with a line in `degraded` is a correct one.
    _pv_facts = _pv_json.loads(%(facts)s)
    _pv_interactions = []
    for _pv_it in _pv_facts.get('interactions') or []:
        _pv_kept = []
        for _pv_sname in _pv_it.get('surfaces') or []:
            if _pv_key(_pv_sname) in _pv_all_surfaces:
                _pv_kept.append(_pv_key(_pv_sname))
            else:
                _pv_degraded.append(
                    u'交互 ' + _pv_txt(_pv_it.get('name')) + u' 用到的面 '
                    + _pv_txt(_pv_sname) + u' 在装配里找不到，'
                    + u'模型树里这条交互不带接触面')
        _pv_row = {'name': _pv_it.get('name'), 'kind': _pv_it.get('kind'),
                   'call': _pv_it.get('call'), 'surfaces': _pv_kept,
                   'gap': None, 'gap_nodes': None}
        if len(_pv_kept) == 2:
            # The same measurement `_expect_gap` takes, taken again rather than
            # cached: a pair that stated no `expect.gap` never had one taken,
            # and the measured 9 ms for 156x156 nodes is not worth a second
            # code path to save.
            try:
                _pv_gap = _surface_gap(a, _pv_kept[0], _pv_kept[1])
                if not _pv_gap['empty']:
                    _pv_row['gap'] = float(_pv_gap['worst'])
                    _pv_row['gap_nodes'] = [int(_pv_gap['n_main']),
                                            int(_pv_gap['n_sec'])]
                else:
                    _pv_degraded.append(
                        u'交互 ' + _pv_txt(_pv_it.get('name'))
                        + u' 的两个面里有一个没有节点，间隙量不出来')
            except Exception as _pv_ex:
                _pv_degraded.append(
                    u'交互 ' + _pv_txt(_pv_it.get('name'))
                    + u' 的间隙没量成：' + _pv_txt(_pv_ex))
        _pv_interactions.append(_pv_row)

    _pv_conditions = []
    for _pv_cd in _pv_facts.get('conditions') or []:
        _pv_row = {'name': _pv_cd.get('name'), 'call': _pv_cd.get('call'),
                   'step': _pv_cd.get('step'), 'sets': [], 'surfaces': []}
        for _pv_which, _pv_known in (('sets', _pv_all_sets),
                                     ('surfaces', _pv_all_surfaces)):
            for _pv_rname in _pv_cd.get(_pv_which) or []:
                if _pv_key(_pv_rname) in _pv_known:
                    _pv_row[_pv_which].append(_pv_key(_pv_rname))
                else:
                    _pv_degraded.append(
                        u'条件 ' + _pv_txt(_pv_cd.get('name')) + u' 用到的区域 '
                        + _pv_txt(_pv_rname) + u' 在装配里找不到，'
                        + u'模型树里这条点不出区域')
        _pv_conditions.append(_pv_row)

    # Section and material per instance, so the tree can label a part without
    # a second trip into CAE. Read off the PART: a section is assigned there,
    # and two instances of one part share the assignment.
    _pv_sections = []
    for _pv_name in sorted(a.instances.keys()):
        _pv_row = {'instance': _pv_name, 'part': '',
                   'sections': [], 'materials': []}
        try:
            _pv_pname = str(a.instances[_pv_name].partName)
            _pv_row['part'] = _pv_pname
            for _pv_sa in m.parts[_pv_pname].sectionAssignments:
                _pv_sname = _pv_sa.sectionName
                if _pv_sname not in _pv_row['sections']:
                    _pv_row['sections'].append(_pv_sname)
                try:
                    # Not every section has one: a ConnectorSection carries
                    # behaviour and a composite layup carries a list.
                    _pv_mname = m.sections[_pv_sname].material
                except Exception:
                    _pv_mname = None
                if _pv_mname and _pv_mname not in _pv_row['materials']:
                    _pv_row['materials'].append(_pv_mname)
        except Exception as _pv_ex:
            _pv_degraded.append(u'实例 ' + _pv_txt(_pv_name)
                                + u' 的截面/材料没读到：' + _pv_txt(_pv_ex))
        _pv_sections.append(_pv_row)

    _pv_degraded.extend(_pv_facts.get('degraded') or [])
    # 'format' is deliberately NOT bumped: runner/build_model.py routes this
    # file on an exact string match, so a new value there would stop the
    # preview being generated at all rather than upgrade it. The schema
    # version is 'assembly_dump', and post/parse_inp.py reads a dump without
    # that key as the old, mesh-only shape.
    _pv_payload = {'format': 'abaqus-agent-preview/instances',
                   'assembly_dump': 1,
                   'space': 'assembly',
                   'truncated': _pv_truncated,
                   'element_cap': %(element_cap)d,
                   'region_cap': %(region_cap)d,
                   'region_node_cap': %(node_cap)d,
                   'instances': _pv_instances,
                   'surfaces': _pv_surfaces,
                   'sets': _pv_sets,
                   'interactions': _pv_interactions,
                   'conditions': _pv_conditions,
                   'sections': _pv_sections,
                   'degraded': _pv_degraded}
    _pv_f = open(os.path.join(workdir, 'preview_raw.json'), 'w')
    try:
        _pv_json.dump(_pv_payload, _pv_f)
    finally:
        _pv_f.close()
    print('PREVIEW_DUMPED: instances=' + str(len(_pv_instances))
          + ' truncated=' + str(_pv_truncated)
          + ' surfaces=' + str(len(_pv_surfaces))
          + ' sets=' + str(len(_pv_sets))
          + ' interactions=' + str(len(_pv_interactions))
          + ' conditions=' + str(len(_pv_conditions))
          + ' degraded=' + str(len(_pv_degraded)))
except Exception as _pv_e:
    print('PREVIEW_DUMP_FAILED: ' + str(_pv_e))
""" % {"element_cap": PREVIEW_ELEMENT_CAP,
       "region_cap": PREVIEW_REGION_CAP,
       "node_cap": PREVIEW_REGION_NODE_CAP,
       "face_cap": PREVIEW_FACE_CAP,
       # Embedded as JSON rather than as a repr: `ensure_ascii` keeps the
       # literal pure ASCII, which is the only form a py2.7 and a py3.10 kernel
       # read identically. A py3 repr of a Chinese string is not.
       "facts": repr(json.dumps(_preview_assembly_facts(spec),
                                ensure_ascii=True, sort_keys=True))}
