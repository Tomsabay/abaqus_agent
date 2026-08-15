import importlib
from pathlib import Path

import pytest
import yaml

from tools.errors import AbaqusAgentError, ErrorCode

build_model_module = importlib.import_module("runner.build_model")


def _write_custom_inp_spec(tmp_path, source_inp):
    spec = {
        "meta": {
            "model_name": "custom_model",
            "abaqus_release": "2024",
        },
        "geometry": {
            "type": "custom_inp",
            "inp_path": str(source_inp),
        },
        "material": {
            "name": "Steel",
            "E": 210000.0,
            "nu": 0.3,
        },
        "analysis": {
            "step_type": "Static",
        },
        "outputs": {
            "kpis": [],
        },
    }
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return spec_path


def test_build_model_custom_inp_copies_deck_without_running_cae(tmp_path, monkeypatch):
    source_inp = tmp_path / "source.inp"
    source_inp.write_text("*Heading\ncustom input deck\n", encoding="utf-8")
    spec_path = _write_custom_inp_spec(tmp_path, source_inp)
    workdir = tmp_path / "run"

    def fail_if_called(*args, **kwargs):
        raise AssertionError("custom_inp should not invoke Abaqus CAE noGUI")

    monkeypatch.setattr(build_model_module, "_run_cae_nougui", fail_if_called)

    result = build_model_module.build_model(spec_path, workdir)

    copied_inp = workdir / "custom_model.inp"
    script_path = workdir / "build_model_script.py"
    assert result["cached"] is False
    assert result["inp_path"] == copied_inp
    assert result["cae_path"] == workdir / "custom_model.cae"
    assert copied_inp.read_text(encoding="utf-8") == "*Heading\ncustom input deck\n"
    assert script_path.read_text(encoding="utf-8") == "# custom inp - no CAE script needed\n"


def test_build_model_foreign_inp_without_manifest_is_rebuilt(tmp_path, monkeypatch):
    """The inverse of the old test at this spot, which pinned the defect.

    It pre-placed a DIFFERENT deck in the workdir and asserted the stale copy
    survived (`cached deck` returned while the source said `source deck`).
    That is exactly the failure P2-d #4 exists to kill: reuse must be proven
    by a build fingerprint, and a deck with no manifest proves nothing.
    """
    source_inp = tmp_path / "source.inp"
    source_inp.write_text("*Heading\nsource deck\n", encoding="utf-8")
    spec_path = _write_custom_inp_spec(tmp_path, source_inp)
    workdir = tmp_path / "run"
    workdir.mkdir()
    cached_inp = workdir / "custom_model.inp"
    cached_inp.write_text("*Heading\ncached deck\n", encoding="utf-8")

    monkeypatch.setattr(
        build_model_module,
        "_run_cae_nougui",
        lambda *args, **kwargs: pytest.fail("custom_inp rebuild must not invoke CAE"),
    )

    result = build_model_module.build_model(spec_path, workdir)

    assert result["cached"] is False
    assert "指纹" in result["cache_reason"]
    assert cached_inp.read_text(encoding="utf-8") == "*Heading\nsource deck\n", (
        "the stale pre-placed deck must be replaced by the actual source")


def test_build_model_custom_inp_missing_source_raises_structured_error(tmp_path):
    missing_inp = tmp_path / "missing.inp"
    spec_path = _write_custom_inp_spec(tmp_path, missing_inp)

    with pytest.raises(AbaqusAgentError) as exc_info:
        build_model_module.build_model(spec_path, tmp_path / "run")

    assert exc_info.value.code == ErrorCode.FILE_NOT_FOUND
    assert "custom_inp source not found" in str(exc_info.value)
    # Windows paths are case-insensitive and resolve() canonicalizes on-disk case.
    assert str(missing_inp).lower() in str(exc_info.value).lower()


def test_plate_hole_forces_symmetry_bc_even_without_marker(tmp_path, monkeypatch):
    """plate_with_hole has no FIXED_END set — a plain fixed_face like 'x=0'
    must still generate the symmetry BC path, not a KeyError at CAE time."""
    source_spec = Path(__file__).parent.parent / "cases" / "plate_hole" / "spec.yaml"
    spec = yaml.safe_load(source_spec.read_text(encoding="utf-8"))
    spec["meta"]["model_name"] = "fake_plate_model"
    spec["bc_load"]["fixed_face"] = "x=0"
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    workdir = tmp_path / "run"

    def fake_run_cae(script_path, run_workdir, abaqus_release):
        script_text = script_path.read_text(encoding="utf-8")
        assert "XsymmBC(" in script_text
        assert "YsymmBC(" in script_text
        assert "sets['FIXED_END']" not in script_text
        (run_workdir / "fake_plate_model.inp").write_text("*Heading\n", encoding="utf-8")

    monkeypatch.setattr(build_model_module, "_run_cae_nougui", fake_run_cae)
    result = build_model_module.build_model(spec_path, workdir)
    assert result["inp_path"].exists()


def test_build_model_generated_script_handoff_with_fake_cae(tmp_path, monkeypatch):
    source_spec = Path(__file__).parent.parent / "cases" / "cantilever" / "spec.yaml"
    spec = yaml.safe_load(source_spec.read_text(encoding="utf-8"))
    spec["meta"]["model_name"] = "fake_cae_model"
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    workdir = tmp_path / "run"
    calls = []

    def fake_run_cae(script_path, run_workdir, abaqus_release):
        calls.append((script_path, run_workdir, abaqus_release))
        script_text = script_path.read_text(encoding="utf-8")
        assert "# AUTO-GENERATED by abaqus-agent build_model.py" in script_text
        assert "mdb.jobs['fake_cae_model'].writeInput" in script_text
        assert "mdb.models['fake_cae_model'].ConcentratedForce(" in script_text
        assert "cf2=-1.0" in script_text
        assert "mdb.models['fake_cae_model'].Pressure(" not in script_text
        # Tip node set is picked as nearest-node-to-face-center (seed-independent),
        # not a bounding box that requires a node exactly at (W/2, H/2).
        assert "abs(_c[2] - 100.0) <= 0.01" in script_text
        assert "(_c[0] - 10.0/2.0)**2" in script_text
        assert "sequenceFromLabels((_tip_best,))" in script_text
        assert "getByBoundingBox" not in script_text.split("generateMesh()")[1]
        (run_workdir / "fake_cae_model.inp").write_text(
            "*Heading\nfake generated deck\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(build_model_module, "_run_cae_nougui", fake_run_cae)

    result = build_model_module.build_model(spec_path, workdir)

    # Take the release from the spec we loaded rather than hardcoding a year —
    # a literal here breaks whenever the case is retargeted at a different
    # Abaqus, which is exactly what happened when the specs were corrected from
    # a claimed 2024 to the 2021 actually installed.
    assert calls == [(workdir / "build_model_script.py", workdir,
                      spec["meta"]["abaqus_release"])]
    assert result["cached"] is False
    assert result["inp_path"] == workdir / "fake_cae_model.inp"
    assert result["inp_path"].read_text(encoding="utf-8") == "*Heading\nfake generated deck\n"
    assert result["cae_path"] == workdir / "fake_cae_model.cae"


def test_build_model_static_pressure_keeps_the_sign_the_spec_asked_for(tmp_path):
    """The sign IS the direction: Abaqus pressure is positive INTO the surface,
    so a spec asking for -100 means tension. This test used to assert the
    abs()'d value, pinning the defect: plate_hole's tension became compression,
    and because Mises is magnitude-only it still landed on its expected value —
    only U_X_MAX gave it away, coming out exactly 0.0 (measured) instead of
    0.048. With the sign restored the same run measures 0.0501."""
    source_spec = Path(__file__).parent.parent / "cases" / "cantilever" / "spec.yaml"
    spec = yaml.safe_load(source_spec.read_text(encoding="utf-8"))
    spec["meta"]["model_name"] = "pressure_model"
    spec["bc_load"]["load_type"] = "pressure"
    script_path = tmp_path / "build_model_script.py"

    for value, expected in ((-100.0, "magnitude=-100.0"), (250.0, "magnitude=250.0")):
        spec["bc_load"]["value"] = value
        build_model_module._write_cae_script(spec, script_path, tmp_path)
        script_text = script_path.read_text(encoding="utf-8")
        assert "mdb.models['pressure_model'].Pressure(" in script_text
        assert expected in script_text, (
            "pressure %s must reach the deck as %s" % (value, expected))
        assert "mdb.models['pressure_model'].ConcentratedForce(" not in script_text
