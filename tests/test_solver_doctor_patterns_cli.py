import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_inspect_solver_doctor_patterns_cli_list_and_detail():
    script = ROOT / "scripts" / "inspect_solver_doctor_patterns.py"

    list_result = subprocess.run(
        [
            sys.executable,
            str(script),
            "list",
            "--category",
            "license",
            "--severity",
            "error",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    list_data = json.loads(list_result.stdout)
    assert list_data["workflow"] == "solver-doctor-pattern-gallery"
    assert list_data["filters"] == {"category": "LICENSE", "severity": "ERROR"}
    assert list_data["total"] >= 1
    assert {pattern["category"] for pattern in list_data["patterns"]} == {"LICENSE"}
    assert {pattern["severity"] for pattern in list_data["patterns"]} == {"ERROR"}

    pattern_id = list_data["patterns"][0]["id"]
    detail_result = subprocess.run(
        [
            sys.executable,
            str(script),
            "detail",
            pattern_id,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    detail_data = json.loads(detail_result.stdout)
    assert detail_data["workflow"] == "solver-doctor-pattern-gallery"
    assert detail_data["real_env_verified"] is False
    assert detail_data["pattern"]["id"] == pattern_id
    assert detail_data["pattern"]["category"] == "LICENSE"
    assert detail_data["pattern"]["source_file"] in {".msg", ".dat"}
    assert "license" in detail_data["pattern"]["recommendation"].lower()


def test_inspect_solver_doctor_patterns_cli_missing_id_returns_json_error():
    script = ROOT / "scripts" / "inspect_solver_doctor_patterns.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "detail",
            "missing-pattern",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "Solver Doctor pattern not found" in json.loads(result.stdout)["error"]
