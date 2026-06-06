import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_inspect_kpi_recipes_cli_list_detail_and_export(tmp_path):
    script = ROOT / "scripts" / "inspect_kpi_recipes.py"

    list_result = subprocess.run(
        [
            sys.executable,
            str(script),
            "list",
            "--case",
            "plate_hole",
            "--kpi-type",
            "field_max",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    list_data = json.loads(list_result.stdout)
    assert list_data["workflow"] == "kpi-recipe-gallery"
    assert list_data["total"] == 1
    assert list_data["items"][0]["id"] == "plate-hole-max-mises"

    detail_result = subprocess.run(
        [
            sys.executable,
            str(script),
            "detail",
            "modal-first-three-frequencies",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    detail_data = json.loads(detail_result.stdout)
    assert detail_data["case"] == "modal"
    assert detail_data["kpi_types"] == ["eigenfrequency"]
    assert detail_data["real_env_verified"] is False
    assert "does not prove real Abaqus ODB extraction" in detail_data["verification_boundary"]

    out_path = tmp_path / "modal-kpi-spec.json"
    export_result = subprocess.run(
        [
            sys.executable,
            str(script),
            "export",
            "modal-first-three-frequencies",
            "--out",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    export_data = json.loads(export_result.stdout)
    exported_spec = json.loads(out_path.read_text(encoding="utf-8"))
    assert export_data["recipe_id"] == "modal-first-three-frequencies"
    assert export_data["kpi_spec_path"] == str(out_path)
    assert "abaqus python post/extract_kpis.py" in export_data["extract_command_hint"]
    assert [entry["name"] for entry in exported_spec] == ["freq_1", "freq_2", "freq_3"]


def test_inspect_kpi_recipes_cli_missing_recipe_returns_json_error():
    script = ROOT / "scripts" / "inspect_kpi_recipes.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "detail",
            "missing-recipe",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "KPI recipe not found" in json.loads(result.stdout)["error"]
