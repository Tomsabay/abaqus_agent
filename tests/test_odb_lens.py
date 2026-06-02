"""Tests for ODB Lens recipe normalization and reports."""

from __future__ import annotations

import json

import yaml

import cli
from odb_lens import load_recipe, normalize_plots, normalize_recipe, render_kpi_markdown
from post.extract_kpis import _extract_single_kpi


class FakeValue:
    def __init__(self, data=None, mises=None, magnitude=None):
        self.data = data
        if mises is not None:
            self.mises = mises
        if magnitude is not None:
            self.magnitude = magnitude


class FakeRegion:
    def __init__(self, name):
        self.name = name


class FakeField:
    def __init__(self, values, subsets=None):
        self.values = values
        self.subsets = subsets or {}

    def getSubset(self, region=None, position=None):
        if region is not None:
            return self.subsets[region.name]
        return self


class FakeHistoryOutput:
    def __init__(self, data):
        self.data = data


class FakeHistoryRegion:
    def __init__(self, outputs):
        self.historyOutputs = outputs


class FakeFrame:
    def __init__(self, field_outputs=None, frequency=0.0):
        self.fieldOutputs = field_outputs or {}
        self.frequency = frequency


class FakeStep:
    def __init__(self, frames, history_regions=None):
        self.frames = frames
        self.historyRegions = history_regions or {}


class FakeAssembly:
    def __init__(self):
        self.nodeSets = {"TIP": FakeRegion("TIP")}
        self.elementSets = {"CRITICAL": FakeRegion("CRITICAL")}
        self.surfaces = {}


class FakeOdb:
    def __init__(self, steps):
        self.steps = steps
        self.rootAssembly = FakeAssembly()


def test_normalize_outputs_kpis_legacy_shape():
    recipe = normalize_recipe({
        "outputs": {
            "kpis": [
                {"name": "U_tip", "type": "nodal_displacement", "location": "TIP", "component": "U2"}
            ]
        }
    })

    assert recipe == [
        {"name": "U_tip", "type": "nodal_displacement", "location": "TIP", "component": "U2"}
    ]


def test_normalize_declarative_field_recipe():
    recipe = normalize_recipe({
        "kpis": [
            {
                "name": "max_mises",
                "source": "odb",
                "field": "S",
                "invariant": "mises",
                "region": "set:CRITICAL_ZONE",
                "reducer": "max",
                "frame": "last",
            }
        ]
    })

    assert recipe[0]["type"] == "field_max"
    assert recipe[0]["field_variable"] == "S"
    assert recipe[0]["invariant"] == "MISES"
    assert recipe[0]["location"] == "CRITICAL_ZONE"


def test_normalize_history_recipe():
    recipe = normalize_recipe({
        "odb_lens": {
            "kpis": [
                {"name": "plastic_work", "source": "history", "variable": "ALLPD", "reducer": "abs_max"}
            ]
        }
    })

    assert recipe[0]["type"] == "history_output_max"
    assert recipe[0]["variable"] == "ALLPD"


def test_normalize_plots_infers_mises_and_displacement():
    kpis = normalize_recipe([
        {"name": "MISES_MAX", "field": "S", "invariant": "MISES"},
        {"name": "U_tip", "type": "nodal_displacement", "component": "U2"},
    ])

    plots = normalize_plots({}, kpis)

    assert plots == [
        {
            "name": "mises_contour",
            "field_variable": "S",
            "invariant": "MISES",
            "deformed": False,
            "frame": "last",
        },
        {
            "name": "u_magnitude",
            "field_variable": "U",
            "invariant": "MAGNITUDE",
            "deformed": True,
            "frame": "last",
        },
    ]


def test_normalize_plots_accepts_explicit_outputs_shape():
    plots = normalize_plots({
        "outputs": {
            "plots": [
                {"name": "u1 contour", "field": "U", "component": "U1", "deformed": True}
            ]
        }
    })

    assert plots[0]["name"] == "u1_contour"
    assert plots[0]["field_variable"] == "U"
    assert plots[0]["component"] == "U1"


def test_normalize_rejects_duplicate_names():
    try:
        normalize_recipe([
            {"name": "U", "type": "field_max"},
            {"name": "U", "type": "field_min"},
        ])
    except ValueError as e:
        assert "duplicate KPI name" in str(e)
    else:
        raise AssertionError("Expected duplicate KPI names to fail")


def test_load_recipe_from_yaml(tmp_path):
    path = tmp_path / "kpis.yaml"
    path.write_text(
        yaml.safe_dump({"kpis": [{"name": "rf_max", "field": "RF", "component": "RF3"}]}),
        encoding="utf-8",
    )

    recipe = load_recipe(path)

    assert recipe[0]["type"] == "reaction_force_max"


def test_render_kpi_markdown_with_recipe_context():
    report = render_kpi_markdown(
        {"max_mises": {"value": 210.5, "unit": "MPa"}},
        [{"name": "max_mises", "type": "field_max", "field_variable": "S", "invariant": "MISES"}],
    )

    assert "ODB Lens KPI Report" in report
    assert "max_mises" in report
    assert "field_variable=S" in report


def test_lens_normalize_cli(tmp_path, capsys):
    recipe_path = tmp_path / "recipe.yaml"
    recipe_path.write_text(
        yaml.safe_dump({"kpis": [{"name": "max_mises", "field": "S", "invariant": "MISES"}]}),
        encoding="utf-8",
    )

    rc = cli.main(["lens", "normalize", str(recipe_path)])

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out[0]["type"] == "field_max"


def test_lens_report_cli(tmp_path):
    kpis = tmp_path / "kpis.json"
    recipe = tmp_path / "recipe.yaml"
    report = tmp_path / "report.md"
    kpis.write_text(json.dumps({"kpis": {"max_mises": 210.5}}), encoding="utf-8")
    recipe.write_text(
        yaml.safe_dump({"kpis": [{"name": "max_mises", "field": "S", "invariant": "MISES"}]}),
        encoding="utf-8",
    )

    rc = cli.main(["lens", "report", str(kpis), "--recipe", str(recipe), "--out", str(report)])

    assert rc == 0
    assert "ODB Lens KPI Report" in report.read_text(encoding="utf-8")


def test_extract_single_kpi_uses_frame_region_and_invariant():
    global_s = FakeField([FakeValue(mises=10.0), FakeValue(mises=90.0)])
    critical_s = FakeField([FakeValue(mises=25.0), FakeValue(mises=42.0)])
    frame0 = FakeFrame({"S": FakeField([FakeValue(mises=5.0)])})
    frame1 = FakeFrame({"S": FakeField(global_s.values, {"CRITICAL": critical_s})})
    odb = FakeOdb({"Step-1": FakeStep([frame0, frame1])})

    value = _extract_single_kpi(odb, {
        "name": "max_mises_critical",
        "type": "field_max",
        "field_variable": "S",
        "invariant": "MISES",
        "location": "set:critical",
        "frame": "last",
    })

    assert value == 42.0


def test_extract_single_kpi_respects_reducers():
    tip_u = FakeField([
        FakeValue(data=(0.0, -0.2, 0.0)),
        FakeValue(data=(0.0, 0.15, 0.0)),
    ])
    u_field = FakeField(
        [FakeValue(data=(0.0, 9.0, 0.0))],
        {"TIP": tip_u},
    )
    frame = FakeFrame({"U": u_field})
    odb = FakeOdb({"Step-1": FakeStep([frame])})

    value = _extract_single_kpi(odb, {
        "name": "tip_abs_u2",
        "type": "nodal_displacement",
        "location": "TIP",
        "component": "u2",
        "reducer": "abs_max",
    })

    assert value == -0.2


def test_extract_single_history_output_supports_last_reducer():
    step = FakeStep(
        [FakeFrame()],
        {
            "Assembly ASSEMBLY": FakeHistoryRegion({
                "ALLPD": FakeHistoryOutput([(0.0, 1.0), (1.0, 3.0), (2.0, 2.0)])
            })
        },
    )
    odb = FakeOdb({"Step-1": step})

    value = _extract_single_kpi(odb, {
        "name": "plastic_work_last",
        "type": "history_output_max",
        "variable": "ALLPD",
        "reducer": "last",
    })

    assert value == 2.0
