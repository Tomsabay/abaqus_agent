import json
from pathlib import Path

import pytest

from evidence.real_smoke_contract_diff import collect_real_smoke_contract_diff
from scripts import run_real_smoke_contract_diff as real_smoke_cli


def test_collect_real_smoke_contract_diff_writes_real_report_and_capsule(tmp_path):
    smoke_dir = _write_smoke_fixture(tmp_path / "smoke", verified=True)
    contracts = tmp_path / "contracts.yaml"
    contracts.write_text(
        "contracts:\n"
        "  - name: tip deflects downward\n"
        "    type: direction\n"
        "    kpi: U_tip\n"
        "    op: '<'\n"
        "    value: 0\n"
        "  - name: tip near expected\n"
        "    type: relative_error\n"
        "    kpi: U_tip\n"
        "    reference: -0.002\n"
        "    rtol: 0.1\n"
        "    atol: 0.000001\n"
        "  - name: stress near expected\n"
        "    type: relative_error\n"
        "    kpi: MISES_MAX\n"
        "    reference: 0.6\n"
        "    rtol: 0.2\n"
        "    atol: 0.01\n",
        encoding="utf-8",
    )

    evidence = collect_real_smoke_contract_diff(
        smoke_dir=smoke_dir,
        out_dir=tmp_path / "out",
        contracts_path=contracts,
        run_id="cantilever-real-smoke-test",
    )

    assert evidence["workflow"] == "real-smoke-contract-diff"
    assert evidence["overall_status"] == "PASS"
    assert evidence["real_env_required"] is True
    assert evidence["real_env_verified"] is True
    assert evidence["source_smoke"]["local_odb_path"].endswith("Cantilever.odb")
    assert evidence["contracts"]["status"] == "PASS"
    assert evidence["diff"]["status"] == "PASS"
    assert (tmp_path / "out" / "real_smoke_contract_diff.json").exists()
    report = (tmp_path / "out" / "real_smoke_contract_diff.md").read_text(encoding="utf-8")
    assert "Real Smoke Contract/Diff Report" in report
    assert "| Real Abaqus smoke | `verified` |" in report
    assert "This report does not rerun Abaqus" in report
    html = (tmp_path / "out" / "real_smoke_contract_diff.html").read_text(encoding="utf-8")
    assert "Abaqus Agent Real Smoke Contract/Diff Report" in html

    manifest = json.loads(Path(evidence["capsule"]["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["metadata"]["workflow"] == "real-smoke-contract-diff"
    assert manifest["metadata"]["evidence_source"] == "real-abaqus-smoke"
    assert manifest["metadata"]["evidence_level"] == "real"
    assert manifest["metadata"]["real_env_required"] is True
    assert manifest["metadata"]["real_env_verified"] is True
    assert "Cantilever.odb" in {entry["name"] for entry in manifest["artifacts"]}


def test_collect_real_smoke_contract_diff_rejects_unverified_smoke(tmp_path):
    smoke_dir = _write_smoke_fixture(tmp_path / "smoke", verified=False)
    contracts = tmp_path / "contracts.yaml"
    contracts.write_text("contracts: []\n", encoding="utf-8")

    with pytest.raises(ValueError, match="not a verified require-real"):
        collect_real_smoke_contract_diff(
            smoke_dir=smoke_dir,
            out_dir=tmp_path / "out",
            contracts_path=contracts,
        )


def test_real_smoke_contract_diff_cli_generates_json(tmp_path, capsys):
    smoke_dir = _write_smoke_fixture(tmp_path / "smoke", verified=True)
    contracts = tmp_path / "contracts.yaml"
    contracts.write_text(
        "contracts:\n"
        "  - name: stress positive\n"
        "    type: direction\n"
        "    kpi: MISES_MAX\n"
        "    op: '>'\n"
        "    value: 0\n",
        encoding="utf-8",
    )

    code = real_smoke_cli.run(
        [
            "--smoke-dir",
            str(smoke_dir),
            "--out-dir",
            str(tmp_path / "out"),
            "--contracts",
            str(contracts),
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["workflow"] == "real-smoke-contract-diff"
    assert payload["real_env_verified"] is True
    assert Path(payload["report_path"]).exists()


def _write_smoke_fixture(smoke_dir: Path, *, verified: bool) -> Path:
    (smoke_dir / "run").mkdir(parents=True)
    (smoke_dir / "case").mkdir(parents=True)
    (smoke_dir / "run" / "Cantilever.odb").write_text("fake odb bytes for manifest\n", encoding="utf-8")
    (smoke_dir / "run" / "Cantilever.log").write_text("JOB COMPLETED\n", encoding="utf-8")
    (smoke_dir / "run" / "Cantilever.sta").write_text("ANALYSIS COMPLETE\n", encoding="utf-8")
    (smoke_dir / "run" / "Cantilever.dat").write_text("THE ANALYSIS HAS COMPLETED\n", encoding="utf-8")
    (smoke_dir / "run" / "_kpi_spec.json").write_text("[]\n", encoding="utf-8")
    (smoke_dir / "run" / "_kpi_result.json").write_text(
        json.dumps(
            {
                "kpis": {"U_tip": -0.00205, "MISES_MAX": 0.58},
                "errors": [],
                "odb_path": r"D:\code\evidence\run\Cantilever.odb",
            }
        ),
        encoding="utf-8",
    )
    (smoke_dir / "case" / "expected.json").write_text(
        json.dumps(
            {
                "kpis": {
                    "U_tip": {"value": -0.002, "rtol": 0.1},
                    "MISES_MAX": {"value": 0.6, "rtol": 0.2},
                }
            }
        ),
        encoding="utf-8",
    )
    (smoke_dir / "case" / "spec.yaml").write_text("meta:\n  model_name: Cantilever\n", encoding="utf-8")
    smoke = {
        "project": "abaqus-agent",
        "mode": "require-real",
        "case": "cantilever",
        "overall_status": "real-env-verified" if verified else "real-env-incomplete",
        "real_env_verified": verified,
        "out_dir": str(smoke_dir),
        "stages": [
            {"name": "environment_preflight", "status": "completed", "real_env_verified": verified},
            {"name": "input_job_preparation", "status": "completed", "real_env_verified": verified},
            {"name": "syntaxcheck", "status": "completed", "real_env_verified": verified},
            {"name": "submit_job", "status": "completed", "real_env_verified": verified},
            {"name": "monitor_status_collection", "status": "completed", "real_env_verified": verified},
            {"name": "odb_kpi_adapter_probe", "status": "completed", "real_env_verified": verified},
        ],
    }
    (smoke_dir / "smoke_evidence.json").write_text(json.dumps(smoke), encoding="utf-8")
    for stage in [
        "stage_syntaxcheck.json",
        "stage_submit_job.json",
        "stage_monitor_status_collection.json",
        "stage_odb_kpi_adapter_probe.json",
    ]:
        (smoke_dir / stage).write_text("{}\n", encoding="utf-8")
    return smoke_dir
