"""A KPI whose `location` names a surface: refused where it can be explained.

Found while building the gate for #67. `_resolve_region` searches `surfaces`
alongside the node and element sets and returns whatever it finds first, so a
`location` naming a surface resolves happily — and then `getSubset` rejects it:

    Surface based region for getSubset is not supported

The KPI then vanishes from `result["kpis"]` entirely. The error is recorded in
`stages.extract_kpis.errors`, the top level still reports COMPLETED, and the
number the user asked for is simply absent from a run that says it succeeded.
That is the shape this project keeps refusing, and it is worth being precise
about which half this file fixes:

  (a) `_resolve_region` must not offer a surface as a usable region. It is not
      one, on any ODB, for any field. Behaviour-preserving in the sense that
      nothing that used to work stops working — the surface path could only
      ever end in that exception — and the message moves from the Abaqus kernel
      to a place that can say what to do instead. THIS FILE.

  (b) whether a KPI that fails to extract should mark the whole run FAILED is a
      separate decision, because it changes the verdict of every shipped case
      and every frozen baseline. Not decided here.

Surfaces are still searched, and that is the point: "not found" would send the
author looking for a typo in a name that is right. What is wrong is the kind of
object, and the refusal has to say so.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

extract = importlib.import_module("post.extract_kpis")


class _Region(object):
    def __init__(self, name):
        self.name = name


def _odb(node_sets=(), element_sets=(), surfaces=(), inst_surfaces=()):
    """An ODB shaped like the real one: sets on the instance, not the assembly."""
    instance = SimpleNamespace(
        nodeSets=dict((n, _Region(n)) for n in node_sets),
        elementSets=dict((n, _Region(n)) for n in element_sets),
        surfaces=dict((n, _Region(n)) for n in inst_surfaces))
    assembly = SimpleNamespace(
        nodeSets={}, elementSets={},
        surfaces=dict((n, _Region(n)) for n in surfaces),
        instances={"PART-1-1": instance})
    return SimpleNamespace(rootAssembly=assembly)


def test_a_surface_is_refused_and_the_message_says_it_is_a_surface():
    odb = _odb(element_sets=["PLATE"], inst_surfaces=["CONTACT_TOP"])
    with pytest.raises(KeyError) as caught:
        extract._resolve_region(odb, "CONTACT_TOP", "element")
    message = str(caught.value)
    assert "surface" in message.lower()
    # Not "not found": the name is right and hunting for a typo in it is
    # exactly the wrong thing to send someone off to do.
    assert "not found" not in message.lower()
    # And it has to say what to do instead.
    assert "set" in message.lower()


def test_the_refusal_names_the_sets_that_would_have_worked():
    odb = _odb(element_sets=["PLATE", "HOLEWALL"], inst_surfaces=["CONTACT_TOP"])
    with pytest.raises(KeyError) as caught:
        extract._resolve_region(odb, "CONTACT_TOP", "element")
    message = str(caught.value)
    assert "PLATE" in message and "HOLEWALL" in message


def test_a_set_is_still_resolved_when_a_surface_shares_its_name():
    """Abaqus allows both, and the set is the one that can be subset."""
    odb = _odb(element_sets=["TOP"], inst_surfaces=["TOP"])
    region = extract._resolve_region(odb, "TOP", "element")
    assert isinstance(region, _Region)
    # Resolved off elementSets, which is what getSubset accepts.
    assert region is odb.rootAssembly.instances["PART-1-1"].elementSets["TOP"]


def test_a_name_that_is_neither_still_says_not_found():
    """The pre-existing refusal is unchanged for the case it was written for."""
    odb = _odb(element_sets=["PLATE"], inst_surfaces=["CONTACT_TOP"])
    with pytest.raises(KeyError) as caught:
        extract._resolve_region(odb, "NOSUCHTHING", "element")
    assert "not found" in str(caught.value).lower()


def test_whole_model_is_unaffected():
    odb = _odb(inst_surfaces=["CONTACT_TOP"])
    assert extract._resolve_region(odb, "whole_model", "element") is None
    assert extract._resolve_region(odb, "", "element") is None


def test_an_assembly_level_surface_is_refused_the_same_way():
    """Surfaces live in both places, and only one of them was reachable in the
    bug report."""
    odb = _odb(element_sets=["PLATE"], surfaces=["ASM_SURF"])
    with pytest.raises(KeyError) as caught:
        extract._resolve_region(odb, "ASM_SURF", "element")
    assert "surface" in str(caught.value).lower()


def test_the_node_preference_path_refuses_surfaces_too():
    """`preferred` reorders the search; it must not reopen the surface route."""
    odb = _odb(node_sets=["TIP"], inst_surfaces=["CONTACT_TOP"])
    with pytest.raises(KeyError) as caught:
        extract._resolve_region(odb, "CONTACT_TOP", "node")
    assert "surface" in str(caught.value).lower()
