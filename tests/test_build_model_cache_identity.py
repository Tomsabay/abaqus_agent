"""P2-d #4: deck reuse must be proven by a build fingerprint, never assumed
from file existence.

Reproduced defect these tests pin: edit a handed-over deck source (100N ->
900N), rerun, the old branch saw custom_model.inp on disk and returned
cached=True — the solver then ran the 100N deck with fresh timestamps and stale
physics.

All tests are hermetic: CAE is faked, detect_abaqus_release is pinned, no
solver is touched.
"""

import importlib
import json

import pytest
import yaml

import tools.abaqus_cmd as abaqus_cmd_module

build_model_module = importlib.import_module("runner.build_model")
build_v2_module = importlib.import_module("runner.build_v2")


@pytest.fixture(autouse=True)
def _pin_release(monkeypatch):
    """Fingerprints include the probed solver release; pin it so tests never
    depend on what this machine has installed (or on the probe's cache)."""
    monkeypatch.setattr(
        abaqus_cmd_module, "detect_abaqus_release",
        lambda timeout=90.0, force=False: "2021")


def _write_custom_spec(tmp_path, source_inp, name="spec.yaml"):
    """A deck spec: a finished .inp handed over as it stands.

    It carries meta / material / outputs and nothing that would describe a
    model — the deck already contains its own parts, steps and loads.
    """
    spec = {
        "meta": {"model_name": "custom_model", "abaqus_release": "2021"},
        "deck": {"file": str(source_inp)},
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
        "outputs": {"kpis": []},
    }
    spec_path = tmp_path / name
    spec_path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return spec_path


def _write_cae_spec(tmp_path, load_value=-100.0, name="spec.yaml"):
    """An assembly-dialect spec, which is what the CAE path compiles.

    `load_value` is the tip force, and it is the knob these tests turn to make
    two specs differ: it reaches the deck as `cf2`, so a changed value changes
    the emitted script and therefore the build fingerprint.
    """
    spec = {
        "meta": {"model_name": "cae_model", "abaqus_release": "2021",
                 "units": "mm_MPa_t"},
        "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
        "parts": [{
            "name": "Beam",
            "features": [
                {"op": "sketch", "id": "profile", "plane": "XY",
                 "profile": {"rect": {"corner1": [0.0, 0.0],
                                      "corner2": [10.0, 10.0]}}},
                {"op": "extrude", "sketch": "profile", "depth": 100.0},
            ],
            "section": {"type": "solid", "material": "Steel"},
            "mesh": {"seed": 5.0, "element": "C3D8I"},
        }],
        "assembly": {"instances": [
            {"name": "Beam-1", "part": "Beam", "translate": [0.0, 0.0, 0.0]}]},
        "steps": [{"call": "StaticStep", "name": {"literal": "Step-1"},
                   "previous": {"literal": "Initial"}}],
        "conditions": [
            {"call": "EncastreBC", "name": {"literal": "Fixed"},
             "createStepName": {"literal": "Initial"},
             "region": {"set": "Beam-1:face@z=min", "name": "FIXED_END",
                        "expect": "=1"}},
            {"call": "ConcentratedForce", "name": {"literal": "Tip"},
             "createStepName": {"literal": "Step-1"},
             "region": {"set": "Beam-1:node@box=4.9,4.9,99.9,5.1,5.1,100.1",
                        "name": "TIP_NODES", "expect": "=1"},
             "cf2": load_value, "expect": {"points": 1}},
        ],
        "outputs": {"kpis": []},
    }
    spec_path = tmp_path / name
    spec_path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return spec_path


def _fake_cae(monkeypatch, deck_text="*Heading\ngenerated deck\n"):
    """Stand in for `abaqus cae noGUI=`, recording the whole handoff.

    The triple is kept, not just the count: which script was handed over, into
    which directory, and at which release, is the contract build_model has with
    CAE. It used to be asserted by a test of the deleted v1 generator, which
    checked it alongside that generator's emitted text.
    """
    calls = []

    def fake_run(script_path, run_workdir, abaqus_release):
        calls.append((script_path, run_workdir, abaqus_release))
        (run_workdir / "cae_model.inp").write_text(deck_text, encoding="utf-8")

    monkeypatch.setattr(build_model_module, "_run_cae_nougui", fake_run)
    return calls


def _forbid_cae(monkeypatch):
    monkeypatch.setattr(
        build_model_module, "_run_cae_nougui",
        lambda *a, **k: pytest.fail("cache hit must not invoke CAE"))


# ---------------------------------------------------------------------------
# handed-over deck identity
# ---------------------------------------------------------------------------

def test_source_change_forces_rebuild_and_copies_new_deck(tmp_path, monkeypatch):
    """The reproduced defect, verbatim: change the source, rerun, the solver
    must get the NEW deck."""
    source = tmp_path / "model.inp"
    source.write_text("*Heading\n*Cload\nTIP, 2, -100.0\n", encoding="utf-8")
    spec_path = _write_custom_spec(tmp_path, source)
    workdir = tmp_path / "run"
    _forbid_cae(monkeypatch)

    first = build_model_module.build_model(spec_path, workdir)
    assert first["cached"] is False

    source.write_text("*Heading\n*Cload\nTIP, 2, -900.0\n", encoding="utf-8")
    second = build_model_module.build_model(spec_path, workdir)

    assert second["cached"] is False
    assert "源 .inp 文件内容已变化" in second["cache_reason"]
    assert (workdir / "custom_model.inp").read_text(encoding="utf-8") \
        == "*Heading\n*Cload\nTIP, 2, -900.0\n"


def test_unchanged_custom_inp_hits_cache(tmp_path, monkeypatch):
    source = tmp_path / "model.inp"
    source.write_text("*Heading\nstable deck\n", encoding="utf-8")
    spec_path = _write_custom_spec(tmp_path, source)
    workdir = tmp_path / "run"
    _forbid_cae(monkeypatch)

    first = build_model_module.build_model(spec_path, workdir)
    assert first["cached"] is False

    # Prove the hit path doesn't silently re-copy: a re-copy would be
    # harmless, but then "cached" would be a lie in the other direction.
    monkeypatch.setattr(
        build_model_module.shutil, "copyfile",
        lambda *a, **k: pytest.fail("cache hit must not re-copy the source"))
    second = build_model_module.build_model(spec_path, workdir)

    assert second["cached"] is True
    assert "构建指纹一致" in second["cache_reason"]
    assert second["custom_inp"] is True
    assert second["source_inp_path"] == source.resolve()


def test_manifest_records_source_and_deck_hashes(tmp_path, monkeypatch):
    source = tmp_path / "model.inp"
    source.write_text("*Heading\nhashed deck\n", encoding="utf-8")
    spec_path = _write_custom_spec(tmp_path, source)
    workdir = tmp_path / "run"
    _forbid_cae(monkeypatch)

    build_model_module.build_model(spec_path, workdir)

    manifest = json.loads(
        (workdir / build_model_module.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["source_inp_sha256"] == build_model_module._sha256_file(source)
    assert manifest["inp_sha256"] == build_model_module._sha256_file(
        workdir / "custom_model.inp")
    assert manifest["abaqus_release_probed"] == "2021"
    assert "spec_sha256" in manifest


def test_tampered_deck_in_workdir_forces_rebuild(tmp_path, monkeypatch):
    source = tmp_path / "model.inp"
    source.write_text("*Heading\noriginal\n", encoding="utf-8")
    spec_path = _write_custom_spec(tmp_path, source)
    workdir = tmp_path / "run"
    _forbid_cae(monkeypatch)

    build_model_module.build_model(spec_path, workdir)
    # Out-of-band edit of the run-dir deck (manifest untouched).
    (workdir / "custom_model.inp").write_text("*Heading\ntampered\n",
                                              encoding="utf-8")

    result = build_model_module.build_model(spec_path, workdir)

    assert result["cached"] is False
    assert ".inp 与构建指纹不符" in result["cache_reason"]
    assert (workdir / "custom_model.inp").read_text(encoding="utf-8") \
        == "*Heading\noriginal\n"


def test_corrupt_manifest_forces_rebuild(tmp_path, monkeypatch):
    source = tmp_path / "model.inp"
    source.write_text("*Heading\ndeck\n", encoding="utf-8")
    spec_path = _write_custom_spec(tmp_path, source)
    workdir = tmp_path / "run"
    _forbid_cae(monkeypatch)

    build_model_module.build_model(spec_path, workdir)
    (workdir / build_model_module.MANIFEST_NAME).write_text(
        "{not json", encoding="utf-8")

    result = build_model_module.build_model(spec_path, workdir)

    assert result["cached"] is False
    assert "指纹文件损坏" in result["cache_reason"]


# ---------------------------------------------------------------------------
# CAE-generated deck identity
# ---------------------------------------------------------------------------

def test_cae_build_writes_manifest_then_reuses(tmp_path, monkeypatch):
    spec_path = _write_cae_spec(tmp_path)
    workdir = tmp_path / "run"
    calls = _fake_cae(monkeypatch)

    first = build_model_module.build_model(spec_path, workdir)
    assert first["cached"] is False
    # The handoff, in full. Release is read back off the spec rather than
    # written as a literal year — a literal breaks whenever a spec is
    # retargeted at a different Abaqus, which is what happened when the cases
    # were corrected from a claimed 2024 to the 2021 actually installed.
    release = yaml.safe_load(
        spec_path.read_text(encoding="utf-8"))["meta"]["abaqus_release"]
    assert calls == [(workdir / "build_model_script.py", workdir, release)]
    assert first["inp_path"] == workdir / "cae_model.inp"
    assert first["cae_path"] == workdir / "cae_model.cae"
    assert (workdir / build_model_module.MANIFEST_NAME).exists()

    _forbid_cae(monkeypatch)
    second = build_model_module.build_model(spec_path, workdir)
    assert second["cached"] is True
    assert "构建指纹一致" in second["cache_reason"]


def test_spec_change_forces_rebuild_in_same_workdir(tmp_path, monkeypatch):
    """Sweep-variant hazard: two specs sharing a workdir must never share a
    deck. (Normally run_id separates them; an explicit workdir must not
    reintroduce the collision.)"""
    workdir = tmp_path / "run"
    _fake_cae(monkeypatch, "*Heading\ndeck for -100N\n")
    build_model_module.build_model(_write_cae_spec(tmp_path, -100.0), workdir)

    calls = _fake_cae(monkeypatch, "*Heading\ndeck for -900N\n")
    result = build_model_module.build_model(
        _write_cae_spec(tmp_path, -900.0, name="spec2.yaml"), workdir)

    assert result["cached"] is False
    assert "spec 内容已变化" in result["cache_reason"]
    assert len(calls) == 1
    assert (workdir / "cae_model.inp").read_text(encoding="utf-8") \
        == "*Heading\ndeck for -900N\n"


def test_generator_change_forces_rebuild(tmp_path, monkeypatch):
    spec_path = _write_cae_spec(tmp_path)
    workdir = tmp_path / "run"
    _fake_cae(monkeypatch)
    build_model_module.build_model(spec_path, workdir)

    # Simulate a code change in the script generator: same spec now emits
    # different CAE script bytes. Patched at runner.build_v2.generate_script,
    # which is the generator the assembly dialect actually runs through and
    # whose output is what _build_fingerprint hashes — patching build_model's
    # own wrapper would prove the fingerprint moves without proving it watches
    # the generator.
    real_generate = build_v2_module.generate_script

    def patched_generate(spec, spec_dir=None):
        return real_generate(spec, spec_dir=spec_dir) + "\n# generator v2\n"

    monkeypatch.setattr(build_v2_module, "generate_script", patched_generate)
    calls = _fake_cae(monkeypatch)
    result = build_model_module.build_model(spec_path, workdir)

    assert result["cached"] is False
    assert "建模脚本生成器已变化" in result["cache_reason"]
    assert len(calls) == 1


def test_probed_release_change_forces_rebuild(tmp_path, monkeypatch):
    spec_path = _write_cae_spec(tmp_path)
    workdir = tmp_path / "run"
    _fake_cae(monkeypatch)
    build_model_module.build_model(spec_path, workdir)

    monkeypatch.setattr(
        abaqus_cmd_module, "detect_abaqus_release",
        lambda timeout=90.0, force=False: "2024")
    calls = _fake_cae(monkeypatch)
    result = build_model_module.build_model(spec_path, workdir)

    assert result["cached"] is False
    assert "检测到的 Abaqus 版本已变化" in result["cache_reason"]
    assert len(calls) == 1


def test_crash_before_manifest_leaves_a_miss(tmp_path, monkeypatch):
    """Manifest is written strictly after the .inp: a build that dies in
    between must leave an unproven deck, not a vouched-for one."""
    spec_path = _write_cae_spec(tmp_path)
    workdir = tmp_path / "run"
    _fake_cae(monkeypatch)

    real_manifest_writer = build_model_module._write_build_manifest
    monkeypatch.setattr(
        build_model_module, "_write_build_manifest",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("crash")))
    with pytest.raises(RuntimeError):
        build_model_module.build_model(spec_path, workdir)
    assert (workdir / "cae_model.inp").exists()
    assert not (workdir / build_model_module.MANIFEST_NAME).exists()

    monkeypatch.setattr(
        build_model_module, "_write_build_manifest", real_manifest_writer)
    calls = _fake_cae(monkeypatch)
    result = build_model_module.build_model(spec_path, workdir)

    assert result["cached"] is False
    assert "没有构建指纹" in result["cache_reason"]
    assert len(calls) == 1
