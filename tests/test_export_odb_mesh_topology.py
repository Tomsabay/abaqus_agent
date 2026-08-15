"""Pure-python topology tests for the ODB mesh exporter (no Abaqus needed)."""

from __future__ import annotations

from post.export_odb_mesh import (
    build_surface,
    element_faces,
    exterior_faces,
    group_by_instance,
    label_scope,
    pack_field,
    scope_instance_geometry,
    triangulate,
)

import pytest

# A unit hex: nodes 1..8, bottom 1-4, top 5-8
HEX_CONN = (1, 2, 3, 4, 5, 6, 7, 8)
HEX_COORDS = {
    1: (0, 0, 0), 2: (1, 0, 0), 3: (1, 1, 0), 4: (0, 1, 0),
    5: (0, 0, 1), 6: (1, 0, 1), 7: (1, 1, 1), 8: (0, 1, 1),
}


def test_hex_element_has_six_quad_faces():
    faces = element_faces("C3D8I", HEX_CONN)
    assert len(faces) == 6
    assert all(len(f) == 4 for f in faces)
    # C3D20R uses corner nodes only — same six faces
    faces20 = element_faces("C3D20R", HEX_CONN + tuple(range(9, 21)))
    assert faces20 == faces


def test_shell_and_2d_elements_are_their_own_face():
    assert element_faces("CPS4", (1, 2, 3, 4)) == [(1, 2, 3, 4)]
    assert element_faces("S3R", (1, 2, 3)) == [(1, 2, 3)]
    assert element_faces("UNKNOWN99", (1, 2, 3)) == []


def test_single_hex_surface_is_twelve_tris():
    flat_nodes, flat_tris, labels = build_surface(HEX_COORDS, [("C3D8", HEX_CONN)])
    assert len(labels) == 8
    assert len(flat_nodes) == 24
    assert len(flat_tris) == 12 * 3


def test_shared_face_removed_between_stacked_hexes():
    coords = dict(HEX_COORDS)
    for i, (x, y) in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)], start=9):
        coords[i] = (x, y, 2)
    two_hexes = [("C3D8", HEX_CONN), ("C3D8", (5, 6, 7, 8, 9, 10, 11, 12))]
    _, flat_tris, labels = build_surface(coords, two_hexes)
    # 12 exterior quads (2×6 - 2 shared) -> 20 tris; all 12 nodes on surface
    assert len(flat_tris) == 20 * 3
    assert len(labels) == 12


def test_exterior_keeps_single_and_drops_paired():
    faces = [(1, 2, 3, 4), (4, 3, 2, 1), (5, 6, 7)]
    assert exterior_faces(faces) == [(5, 6, 7)]


def test_triangulate_quad_fan():
    assert triangulate((1, 2, 3, 4)) == [(1, 2, 3), (1, 3, 4)]
    assert triangulate((1, 2, 3)) == [(1, 2, 3)]


def test_pack_field_min_max_and_missing():
    packed = pack_field({1: 5.0, 3: -2.0}, [1, 2, 3])
    assert packed["values"] == [5.0, 0.0, -2.0]
    assert packed["min"] == -2.0
    assert packed["max"] == 5.0


# ---------------------------------------------------------------------------
# Two instances that reuse node labels.
#
# Every fixture above lives in ONE label space, which is why the bug below
# shipped: a label was assumed to be a key. In a real ODB each part instance
# numbers its nodes from 1, so it is not. Measured on the bearing-block
# acceptance ODB: 57030 nodes, 37622 distinct labels, and 6662 of 10590 real
# exterior faces deleted as if they were interior.
# ---------------------------------------------------------------------------

def _hex_at(z0):
    """A unit hex lifted to z0, labelled 1..8 -- as every instance labels it."""
    return {
        1: (0, 0, z0), 2: (1, 0, z0), 3: (1, 1, z0), 4: (0, 1, z0),
        5: (0, 0, z0 + 1), 6: (1, 0, z0 + 1), 7: (1, 1, z0 + 1), 8: (0, 1, z0 + 1),
    }


def _two_instances():
    """Two separated hexes in two instances, both labelled 1..8."""
    coords = {}
    for label, xyz in _hex_at(0).items():
        coords[("A", label)] = xyz
    for label, xyz in _hex_at(10).items():
        coords[("B", label)] = xyz
    elements = [
        ("C3D8", [("A", n) for n in HEX_CONN]),
        ("C3D8", [("B", n) for n in HEX_CONN]),
    ]
    return coords, elements


def test_reused_labels_in_two_instances_keep_both_surfaces():
    coords, elements = _two_instances()
    flat_nodes, flat_tris, labels = build_surface(coords, elements)
    assert len(flat_tris) == 24 * 3          # two closed boxes, nothing shared
    assert len(labels) == 16                 # 8 nodes each, none conflated
    zs = flat_nodes[2::3]
    assert min(zs) == 0 and max(zs) == 11    # both instances present in space


def test_bare_labels_would_have_deleted_the_whole_surface():
    """The counterexample, kept as a test because it is what actually happened.

    Drop the instance scope and the two hexes become one: every face pairs
    with its twin in the other instance and `exterior_faces` calls all twelve
    interior. The surface does not degrade, it vanishes -- which is why the
    exporter must never key by a bare label again.
    """
    _, flat_tris, labels = build_surface(
        _hex_at(0), [("C3D8", HEX_CONN), ("C3D8", HEX_CONN)])
    assert flat_tris == []
    assert labels == []


def test_group_by_instance_gives_contiguous_ranges():
    coords, elements = _two_instances()
    _, flat_tris, labels = build_surface(coords, elements)
    grouping = group_by_instance(flat_tris, labels)
    assert grouping["cross_instance_tris"] == 0
    assert grouping["contiguous"] is True
    assert [g["name"] for g in grouping["groups"]] == ["A", "B"]
    assert [(g["tri_start"], g["tri_count"]) for g in grouping["groups"]] \
        == [(0, 12), (12, 12)]
    assert [(g["node_start"], g["node_count"]) for g in grouping["groups"]] \
        == [(0, 8), (8, 8)]


def test_group_by_instance_says_nothing_when_labels_are_bare():
    _, flat_tris, labels = build_surface(HEX_COORDS, [("C3D8", HEX_CONN)])
    grouping = group_by_instance(flat_tris, labels)
    assert grouping["groups"] == []
    assert grouping["cross_instance_tris"] == 0


def test_group_by_instance_refuses_to_draw_a_cross_instance_triangle():
    """One triangle spanning two instances withdraws the ranges entirely.

    Such a triangle cannot exist once labels are scoped, so if one appears the
    scoping broke upstream and the honest answer is no grouping plus a count,
    not ranges that happen to look plausible.
    """
    labels = [("A", 1), ("A", 2), ("B", 1)]
    grouping = group_by_instance([0, 1, 2], labels)
    assert grouping["cross_instance_tris"] == 1
    assert grouping["groups"] == []


def test_label_scope_reads_the_pair_and_nothing_else():
    assert label_scope(("HOUSING", 7)) == "HOUSING"
    assert label_scope(7) is None


class _FakeNode(object):
    def __init__(self, label, coordinates):
        self.label = label
        self.coordinates = coordinates


class _FakeElement(object):
    def __init__(self, el_type, connectivity):
        self.type = el_type
        self.connectivity = connectivity


def _fake_instance(name, z0):
    """An ODB instance stands in with two attributes; both start at label 1."""
    coords = _hex_at(z0)
    nodes = [_FakeNode(label, coords[label]) for label in sorted(coords)]
    return (name, nodes, [_FakeElement("C3D8", HEX_CONN)])


def test_the_odb_walk_scopes_labels_by_instance():
    """The test that would have caught the shipped bug.

    Two instances, both numbering their nodes 1..8 exactly as Abaqus does.
    Keyed by the bare label the second instance overwrites the first and the
    model loses half its nodes; keyed by the pair, all sixteen survive and each
    element's connectivity still points at its own instance.
    """
    node_coords, elements = scope_instance_geometry(
        [_fake_instance("A", 0), _fake_instance("B", 10)])

    assert len(node_coords) == 16
    assert node_coords[("A", 1)] == (0, 0, 0)
    assert node_coords[("B", 1)] == (0, 0, 10)   # not overwritten by A's
    assert [el_type for el_type, _ in elements] == ["C3D8", "C3D8"]
    assert all(label_scope(label) == "A" for label in elements[0][1])
    assert all(label_scope(label) == "B" for label in elements[1][1])


def test_the_odb_walk_refuses_a_mesh_past_the_cap():
    with pytest.raises(ValueError) as excinfo:
        scope_instance_geometry(
            [_fake_instance("A", 0), _fake_instance("B", 10)], max_elements=1)
    assert "mesh too large: 2 elements > 1" in str(excinfo.value)


class _CountingElements(object):
    """Knows its length without being walked, and remembers if it was."""

    def __init__(self, elements):
        self._elements = elements
        self.iterated = 0

    def __len__(self):
        return len(self._elements)

    def __iter__(self):
        self.iterated += 1
        return iter(self._elements)


def test_the_cap_refuses_before_it_builds():
    """The cap must cost nothing, or it is not a cap.

    An oversized model is refused so that it is never assembled in memory. A
    check that runs after the elements are already in the list has spent
    exactly what it existed to save -- so this asserts the sequence was never
    walked, not merely that the error was raised.
    """
    big = _CountingElements([_FakeElement("C3D8", HEX_CONN)] * 10000)
    coords = _hex_at(0)
    nodes = [_FakeNode(label, coords[label]) for label in sorted(coords)]

    with pytest.raises(ValueError) as excinfo:
        scope_instance_geometry([("A", nodes, big)], max_elements=5)

    assert "mesh too large: 10000 elements > 5" in str(excinfo.value)
    assert big.iterated == 0


def test_pack_field_keys_on_the_instance_label_pair():
    packed = pack_field({("A", 1): 5.0, ("B", 1): -2.0},
                        [("A", 1), ("A", 2), ("B", 1)])
    assert packed["values"] == [5.0, 0.0, -2.0]
    assert packed["min"] == -2.0 and packed["max"] == 5.0
