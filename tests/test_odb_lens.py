"""Tests for ODB Lens recipe normalization and reports."""

from __future__ import annotations

import json

import yaml

import cli
from odb_lens import load_recipe, normalize_plots, normalize_recipe, render_kpi_markdown


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
