"""Tests for ODB image export orchestration.

The second half of this file tests code that RUNS INSIDE Abaqus/CAE. It can be
called from 3.13 because every abaqus import in that module is inside the
function that needs it, so a stand-in `abaqusConstants` in sys.modules is
enough. Worth the small stunt: this is the path every report and every
screenshot goes through, and until 2026-08-18 none of it was covered at all.
"""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from post.export_odb_images import (
    _dress_viewport,
    _plot_zoom,
    _restrict_to_instances,
    _set_contour_limits,
    export_odb_images,
)


def test_export_odb_images_returns_error_when_odb_missing(tmp_path):
    result = export_odb_images(
        tmp_path / "missing.odb",
        [{"name": "mises_contour", "field_variable": "S", "invariant": "MISES"}],
        workdir=tmp_path,
    )

    assert result["images"] == []
    assert "ODB not found" in result["errors"][0]


def test_export_odb_images_passes_paths_through_environment(tmp_path, monkeypatch):
    odb = tmp_path / "model.odb"
    odb.write_text("fake odb\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        assert "--" not in cmd
        env = kwargs["env"]
        assert env["ABAQUS_AGENT_ODB_PATH"].endswith("model.odb")
        result_path = env["ABAQUS_AGENT_PLOT_RESULT"]
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump({"images": [{"path": "mises_contour.png"}], "errors": []}, f)
        return SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    result = export_odb_images(
        odb,
        [{"name": "mises_contour", "field_variable": "S", "invariant": "MISES"}],
        workdir=tmp_path,
    )

    assert result["images"][0]["path"] == "mises_contour.png"


# ---------------------------------------------------------------------------
# Inside CAE: the colour scale and the framing
# ---------------------------------------------------------------------------

class _Recorder:
    def __init__(self):
        self.calls = []

    def setValues(self, **kwargs):
        self.calls.append(kwargs)


def _viewport():
    contour = _Recorder()
    return SimpleNamespace(odbDisplay=SimpleNamespace(contourOptions=contour)), contour


@pytest.fixture
def abaqus_constants(monkeypatch):
    """ON and OFF, as sentinels to be handed straight back."""
    monkeypatch.setitem(sys.modules, "abaqusConstants",
                        SimpleNamespace(OFF="OFF", ON="ON"))
    yield


def test_limits_pin_both_ends_of_the_scale(abaqus_constants):
    viewport, contour = _viewport()
    _set_contour_limits(viewport, {"limits": [0.0, 150.0]})
    assert contour.calls == [{"minAutoCompute": "OFF", "minValue": 0.0,
                              "maxAutoCompute": "OFF", "maxValue": 150.0}]


def test_a_plot_without_limits_restores_the_automatic_scale(abaqus_constants):
    """Not "leaves alone" -- one viewport serves every plot, so the previous
    plot's pinned range would carry over and the picture would be drawn on a
    scale its own legend was never about."""
    viewport, contour = _viewport()
    _set_contour_limits(viewport, {"name": "mises"})
    assert contour.calls == [{"minAutoCompute": "ON", "maxAutoCompute": "ON"}]


def test_unreadable_limits_fall_back_to_automatic(abaqus_constants):
    viewport, contour = _viewport()
    _set_contour_limits(viewport, {"limits": ["a lot", 150.0]})
    assert contour.calls == [{"minAutoCompute": "ON", "maxAutoCompute": "ON"}]


def test_the_contour_is_unaveraged_so_it_matches_the_reported_peak(monkeypatch):
    """Measured 2026-08-18 on the bolted connection: averaged 406.34,
    unaveraged 599.010, and the report's S_MISES_MAX 599.0099. The report
    reads the unaveraged element-nodal peak, so the picture must too --
    otherwise the two disagree and nothing says which is the bug.

    Pinned on basicOptions specifically: commonOptions answers "keyword error
    on averageElementOutput", which inside the try would be a silent no-op.
    """
    monkeypatch.setitem(sys.modules, "abaqusConstants",
                        SimpleNamespace(FEATURE="FEATURE", OFF="OFF", ON="ON"))
    basic, common, annotations = _Recorder(), _Recorder(), _Recorder()
    viewport = SimpleNamespace(
        viewportAnnotationOptions=annotations,
        odbDisplay=SimpleNamespace(commonOptions=common, basicOptions=basic))
    session = SimpleNamespace(pngOptions=_Recorder())

    _dress_viewport(session, viewport)

    assert any(c.get("averageElementOutput") == "OFF" for c in basic.calls)
    assert not any("averageElementOutput" in c for c in common.calls)


class _FakeLeaf:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


@pytest.fixture
def display_group(monkeypatch):
    replaced = []
    dgo = SimpleNamespace(
        LeafFromPartInstance=lambda **kw: _FakeLeaf(kind="instances", **kw),
        Leaf=lambda **kw: _FakeLeaf(kind="default", **kw))
    monkeypatch.setitem(sys.modules, "displayGroupOdbToolset", dgo)
    monkeypatch.setitem(sys.modules, "abaqusConstants",
                        SimpleNamespace(OFF="OFF", DEFAULT_MODEL="DEFAULT_MODEL"))
    viewport = SimpleNamespace(odbDisplay=SimpleNamespace(
        displayGroup=SimpleNamespace(
            replace=lambda leaf: replaced.append(leaf))))
    return viewport, replaced


def test_only_selects_the_named_instances(display_group):
    viewport, replaced = display_group
    _restrict_to_instances(viewport, {"only": ["EndPlate", "Bolt1"]})
    assert replaced[0].kwargs["kind"] == "instances"
    assert replaced[0].kwargs["partInstanceName"] == ("ENDPLATE", "BOLT1")


def test_instance_names_are_upper_cased(display_group):
    """The assembly writes them upper-case into the ODB; failing on the case
    would be a puzzle with no clue in it."""
    viewport, replaced = display_group
    _restrict_to_instances(viewport, {"only": ["beam"]})
    assert replaced[0].kwargs["partInstanceName"] == ("BEAM",)


def test_a_plot_without_only_restores_the_whole_model(display_group):
    """One viewport serves every plot, so a restriction left behind would
    silently crop the plots after it."""
    viewport, replaced = display_group
    _restrict_to_instances(viewport, {"name": "overview"})
    assert replaced[0].kwargs["kind"] == "default"
    assert replaced[0].kwargs["leafType"] == "DEFAULT_MODEL"


def test_a_plot_may_zoom_closer_than_the_run(monkeypatch):
    monkeypatch.delenv("ABAQUS_AGENT_IMAGE_ZOOM", raising=False)
    assert _plot_zoom({"zoom": 2.5}) == 2.5
    assert _plot_zoom({}) == 1.15
    # A zoom nobody can read is the run's, not an exception mid-render.
    assert _plot_zoom({"zoom": "close"}) == 1.15
