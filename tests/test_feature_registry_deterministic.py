"""A capability must not depend on what the process happened to import first.

Measured before this was fixed, in a cold interpreter:

    get_geometry_generator('shell_plate')                  -> None
    get_step_generator('Coupled_Temperature_Displacement') -> None
    import features.coupling.coupled_materials   # runner/build_model.py does
    get_step_generator('Coupled_Temperature_Displacement') -> <function ...>

So four geometry types listed in schema/spec_schema.json could never be built
(nothing imported ``features.geometry`` at all), and a coupled step worked or
not depending on whether the same process had already built an ordinary model
— because build_model.py imports ``features.coupling.coupled_materials``
*after* the step dispatch that needs it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# The four the schema promises but the base pipeline does not implement.
SCHEMA_FEATURE_GEOMETRIES = (
    "shell_plate", "beam_frame", "composite_plate", "cohesive_layer",
)


def _cold_interpreter(snippet: str) -> dict:
    """Run in a FRESH process — an in-process test cannot see this defect,
    because by then pytest has already imported half the tree."""
    proc = subprocess.run(
        [sys.executable, "-c", snippet],
        cwd=str(ROOT), capture_output=True, text=True,
        errors="replace", timeout=120, stdin=subprocess.DEVNULL,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_feature_geometries_resolve_in_a_cold_process():
    probe = (
        "import json;"
        "from features.feature_registry import get_geometry_generator as g;"
        "print(json.dumps({n: bool(g(n)) for n in %r}))" % (SCHEMA_FEATURE_GEOMETRIES,)
    )
    resolved = _cold_interpreter(probe)
    missing = [n for n, ok in resolved.items() if not ok]
    assert not missing, (
        "schema/spec_schema.json offers these geometry types but a cold "
        "process cannot build them: %s" % missing)


def test_coupled_step_resolves_without_a_prior_ordinary_build():
    probe = (
        "import json;"
        "from features.feature_registry import get_step_generator as s;"
        "print(json.dumps({'coupled': bool(s('Coupled_Temperature_Displacement')),"
        " 'thermal_electrical': bool(s('Coupled_Thermal_Electrical'))}))"
    )
    resolved = _cold_interpreter(probe)
    assert resolved["coupled"], (
        "a coupled step must not depend on an unrelated earlier import")
    assert resolved["thermal_electrical"]


def test_every_schema_geometry_is_actually_buildable():
    """The schema enum is a promise. Nothing in it may be unbuildable."""
    schema = json.loads((ROOT / "schema" / "spec_schema.json").read_text(encoding="utf-8"))
    offered = schema["properties"]["geometry"]["properties"]["type"]["enum"]

    probe = (
        "import json;"
        "from features.feature_registry import get_geometry_generator as g;"
        "print(json.dumps({n: bool(g(n)) for n in %r}))" % (offered,)
    )
    from_registry = _cold_interpreter(probe)

    # These are implemented directly in runner/build_model.py rather than via
    # the registry, so they legitimately answer None there.
    builtin = {"cantilever_block", "plate_with_hole", "axisymmetric_disk",
               "custom_inp", "square_plate"}
    unbuildable = [n for n in offered
                   if n not in builtin and not from_registry.get(n)]
    assert not unbuildable, (
        "schema offers geometry types no code can build: %s" % unbuildable)


def test_import_failures_are_reported_not_swallowed():
    from features.feature_registry import list_capabilities, load_failures

    assert load_failures() == {}, (
        "a feature module shipped in this tree failed to import: %s"
        % load_failures())
    caps = list_capabilities()
    assert "unavailable_modules" not in caps
    for name in SCHEMA_FEATURE_GEOMETRIES:
        assert name in caps["geometry_types"]


def test_a_broken_module_surfaces_as_a_named_failure(monkeypatch):
    """The other half of the contract: 'unsupported' and 'broken install'
    must stay distinguishable."""
    import importlib

    import features.feature_registry as reg

    monkeypatch.setattr(reg, "_loaded", False)
    monkeypatch.setattr(reg, "_load_failures", {})
    monkeypatch.setattr(reg, "_REGISTERING_PACKAGES", ("features.geometry", "features.no_such_pkg"))

    reg._ensure_loaded()

    failures = reg.load_failures()
    assert "features.no_such_pkg" in failures
    assert "ModuleNotFoundError" in failures["features.no_such_pkg"]
    # A broken sibling must not take the working ones down with it.
    assert reg.get_geometry_generator("shell_plate") is not None
    importlib.invalidate_caches()


@pytest.mark.parametrize("geo", SCHEMA_FEATURE_GEOMETRIES)
def test_generators_are_callable_and_emit_cae_python(geo):
    from features.feature_registry import get_geometry_generator

    gen = get_geometry_generator(geo)
    assert gen is not None
    code = gen({"L": 100.0, "W": 20.0, "H": 10.0, "R": 5.0, "thickness": 2.0},
               "probe_model")
    assert isinstance(code, str) and code.strip(), (
        "%s registered a generator that emits nothing" % geo)
