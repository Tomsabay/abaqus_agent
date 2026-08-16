import importlib
from pathlib import Path

import pytest
import yaml

from tools.errors import AbaqusAgentError, ErrorCode

build_model_module = importlib.import_module("runner.build_model")


def _write_custom_inp_spec(tmp_path, source_inp):
    """A deck spec: a finished .inp handed over as it stands.

    Nothing here describes a model. The deck already carries its own parts,
    steps, boundary conditions and loads, so the spec is meta / material /
    outputs and the handover itself.
    """
    spec = {
        "meta": {
            "model_name": "custom_model",
            "abaqus_release": "2024",
        },
        "deck": {
            "file": str(source_inp),
        },
        "material": {
            "name": "Steel",
            "E": 210000.0,
            "nu": 0.3,
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
    # A missing deck is a missing FILE, not a broken build: the path is
    # resolved and refused in one place, before anything is generated or run.
    assert "deck source not found" in str(exc_info.value)
    # Windows paths are case-insensitive and resolve() canonicalizes on-disk case.
    assert str(missing_inp).lower() in str(exc_info.value).lower()


def test_build_model_static_pressure_keeps_the_sign_the_spec_asked_for(tmp_path):
    """The sign IS the direction: Abaqus pressure is positive INTO the surface,
    so a spec asking for -100 means tension. This test used to assert the
    abs()'d value, pinning the defect: plate_hole's tension became compression,
    and because Mises is magnitude-only it still landed on its expected value —
    only U_X_MAX gave it away, coming out exactly 0.0 (measured) instead of
    0.048. With the sign restored the same run measures 0.0501.

    Read off the shipped plate_hole spec rather than a hand-written one,
    because that case is the one that depends on this: its 100 MPa tension is
    written `magnitude: -100.0`, and an abs() anywhere between the spec and the
    dispatched call would silently turn it back into compression.
    """
    source_spec = Path(__file__).parent.parent / "cases" / "plate_hole" / "spec.yaml"
    spec = yaml.safe_load(source_spec.read_text(encoding="utf-8"))
    spec["meta"]["model_name"] = "pressure_model"
    pressures = [c for c in spec["conditions"] if c.get("call") == "Pressure"]
    assert len(pressures) == 1, "plate_hole is the pressure case; it must carry one"
    script_path = tmp_path / "build_model_script.py"

    for value, expected in ((-100.0, "'magnitude': -100.0"),
                            (250.0, "'magnitude': 250.0")):
        pressures[0]["magnitude"] = value
        build_model_module._write_cae_script(spec, script_path, tmp_path,
                                             source_spec)
        script_text = script_path.read_text(encoding="utf-8")
        # The dispatched form: the model the call lands on is `m`, bound once
        # in the preamble to mdb.models[MODEL].
        assert "MODEL = 'pressure_model'" in script_text
        assert "_gcall(m, 'Pressure'" in script_text
        assert expected in script_text, (
            "pressure %s must reach the deck as %s" % (value, expected))
        assert "ConcentratedForce" not in script_text
