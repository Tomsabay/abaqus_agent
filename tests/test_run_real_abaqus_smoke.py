import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts import run_real_abaqus_smoke as smoke


def _stage(report, name):
    return next(stage for stage in report["stages"] if stage["name"] == name)


def _clear_real_abaqus_env(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path / "empty-path"))
    for key in (
        "ABAQUS_EXECUTABLE",
        "ABAQUS_COMMAND",
        "ABAQUS_PATH",
        "LM_LICENSE_FILE",
        "ABAQUSLM_LICENSE_FILE",
        "ABAQUS_LICENSE_FILE",
        "DSLS_CONFIG",
        "ABAQUS_AGENT_LICENSE_CONFIRMED",
    ):
        monkeypatch.delenv(key, raising=False)


def test_dry_run_writes_parseable_evidence_without_real_verification(monkeypatch, tmp_path):
    _clear_real_abaqus_env(monkeypatch, tmp_path)

    report, code = smoke.collect_smoke_evidence(mode="dry-run", out_dir=tmp_path)

    assert code == 0
    assert report["schema_version"] == "1.0"
    assert report["mode"] == "dry-run"
    assert report["overall_status"] == "dry-run-ready"
    assert report["real_env_verified"] is False
    assert (tmp_path / "smoke_evidence.json").exists()
    assert json.loads((tmp_path / "smoke_evidence.json").read_text())["mode"] == "dry-run"
    assert report["capsule"]["run_id"] == "cantilever-dry-run"
    capsule_manifest = json.loads(
        (tmp_path / "capsule" / "cantilever-dry-run" / "capsule.json").read_text()
    )
    metadata = capsule_manifest["metadata"]
    assert metadata["metadata_schema_version"] == "1.0"
    assert metadata["project"] == "abaqus-agent"
    assert metadata["workflow"] == "real-abaqus-smoke-harness"
    assert metadata["evidence_source"] == "smoke-harness:dry-run"
    assert metadata["evidence_level"] == "dry-run"
    assert metadata["overall_status"] == "dry-run-ready"
    assert metadata["real_env_required"] is True
    assert metadata["real_env_verified"] is False
    assert metadata["case"] == "cantilever"
    assert metadata["mode"] == "dry-run"
    assert {entry["name"] for entry in capsule_manifest["inputs"]} >= {
        "spec.yaml",
        "expected.json",
        "runner.json",
    }
    assert any(entry["name"] == "stage_syntaxcheck.json" for entry in capsule_manifest["artifacts"])

    stage_names = {stage["name"] for stage in report["stages"]}
    assert set(smoke.STAGE_ORDER) <= stage_names
    assert _stage(report, smoke.STAGE_SYNTAXCHECK)["status"] == "dry-run"
    assert _stage(report, smoke.STAGE_ODB)["real_env_verified"] is False


def test_require_real_without_abaqus_exits_2_and_reports_missing(monkeypatch, tmp_path):
    _clear_real_abaqus_env(monkeypatch, tmp_path)

    report, code = smoke.collect_smoke_evidence(mode="require-real", out_dir=tmp_path)

    assert code == 2
    assert report["overall_status"] == "real-env-missing"
    assert report["real_env_verified"] is False
    assert (tmp_path / "missing_report.json").exists()
    assert report["capsule"]["run_id"] == "cantilever-require-real"
    capsule_manifest = json.loads(
        (tmp_path / "capsule" / "cantilever-require-real" / "capsule.json").read_text()
    )
    metadata = capsule_manifest["metadata"]
    assert metadata["workflow"] == "real-abaqus-smoke-harness"
    assert metadata["evidence_source"] == "smoke-harness:require-real"
    assert metadata["evidence_level"] == "environment-limited"
    assert metadata["overall_status"] == "real-env-missing"
    assert metadata["real_env_required"] is True
    assert metadata["real_env_verified"] is False
    assert any(entry["name"] == "missing_report.json" for entry in capsule_manifest["artifacts"])
    missing = {item["capability"] for item in report["require_real_missing"]}
    assert "abaqus_executable" in missing
    assert "abaqus_license_hint" in missing


def test_mock_real_exercises_fake_syntax_submit_monitor_but_not_odb_verified(
    monkeypatch,
    tmp_path,
):
    _clear_real_abaqus_env(monkeypatch, tmp_path)

    report, code = smoke.collect_smoke_evidence(mode="mock-real", out_dir=tmp_path)

    assert code == 0
    assert report["overall_status"] == "mock-real-completed-not-real-verified"
    assert report["real_env_verified"] is False

    syntax = _stage(report, smoke.STAGE_SYNTAXCHECK)
    submit = _stage(report, smoke.STAGE_SUBMIT)
    monitor = _stage(report, smoke.STAGE_MONITOR)
    odb = _stage(report, smoke.STAGE_ODB)

    assert syntax["status"] == "mock-real"
    assert any("ok=True" in item for item in syntax["evidence"])
    assert submit["status"] == "mock-real"
    assert any("status=completed" in item for item in submit["evidence"])
    assert monitor["status"] == "mock-real"
    assert any("status=COMPLETED" in item for item in monitor["evidence"])
    assert odb["status"] == "environment-limited"
    assert odb["real_env_verified"] is False
    assert any("odbAccess not available" in item for item in odb["evidence"])
    contract_diff = _stage(report, smoke.STAGE_CONTRACT_DIFF)
    assert contract_diff["status"] == "environment-limited"
    assert contract_diff["real_env_verified"] is False
    assert any("contract_diff_not_run=true" in item for item in contract_diff["evidence"])

    capsule_manifest = json.loads(
        (tmp_path / "capsule" / "cantilever-mock-real" / "capsule.json").read_text()
    )
    metadata = capsule_manifest["metadata"]
    assert metadata["evidence_source"] == "smoke-harness:mock-real"
    assert metadata["evidence_level"] == "mock-real"
    assert metadata["overall_status"] == "mock-real-completed-not-real-verified"
    assert metadata["real_env_required"] is True
    assert metadata["real_env_verified"] is False


def test_require_real_verified_kpis_generate_contract_diff_summary(monkeypatch, tmp_path):
    _clear_real_abaqus_env(monkeypatch, tmp_path)

    monkeypatch.setattr(
        smoke,
        "_collect_preflight",
        lambda mode: {
            "schema_version": "1.0",
            "project": "abaqus-agent",
            "mode": mode,
            "overall_status": "real-env-prerequisites-candidate",
            "real_env_prerequisites_ready": True,
            "real_abaqus_e2e_verified": False,
            "missing": [],
            "require_real_missing": [],
        },
    )

    def fake_prepare(spec_path, workdir, out_dir, *, dry_run, mock_real):
        workdir.mkdir(parents=True, exist_ok=True)
        inp_path = workdir / "Cantilever.inp"
        inp_path.write_text("*Heading\n", encoding="utf-8")
        return (
            smoke._write_stage(
                out_dir,
                smoke.SmokeStage(
                    name=smoke.STAGE_INPUT,
                    status=smoke.STATUS_COMPLETED,
                    evidence=[f"inp_path={inp_path}"],
                    real_env_required=True,
                    real_env_verified=True,
                ),
            ),
            inp_path,
        )

    def fake_real_stages(inp_path, workdir, out_dir, runner_cfg, *, mock_real):
        (workdir / "Cantilever.odb").write_text("fixture odb\n", encoding="utf-8")
        (workdir / "Cantilever.log").write_text("JOB COMPLETED\n", encoding="utf-8")
        (workdir / "Cantilever.sta").write_text("ANALYSIS COMPLETE\n", encoding="utf-8")
        (workdir / "Cantilever.dat").write_text("THE ANALYSIS HAS COMPLETED\n", encoding="utf-8")
        (workdir / "_kpi_spec.json").write_text("[]\n", encoding="utf-8")
        (workdir / "_kpi_result.json").write_text(
            json.dumps(
                {
                    "kpis": {"U_tip": -1.084326231648447e-05, "MISES_MAX": 1.0700273513793945},
                    "errors": [],
                    "odb_path": str(workdir / "Cantilever.odb"),
                }
            ),
            encoding="utf-8",
        )
        return [
            smoke._write_stage(
                out_dir,
                smoke.SmokeStage(
                    name=smoke.STAGE_SYNTAXCHECK,
                    status=smoke.STATUS_COMPLETED,
                    evidence=["ok=True"],
                    real_env_required=True,
                    real_env_verified=True,
                ),
            ),
            smoke._write_stage(
                out_dir,
                smoke.SmokeStage(
                    name=smoke.STAGE_SUBMIT,
                    status=smoke.STATUS_COMPLETED,
                    evidence=["status=completed"],
                    real_env_required=True,
                    real_env_verified=True,
                ),
            ),
            smoke._write_stage(
                out_dir,
                smoke.SmokeStage(
                    name=smoke.STAGE_MONITOR,
                    status=smoke.STATUS_COMPLETED,
                    evidence=["status=COMPLETED"],
                    real_env_required=True,
                    real_env_verified=True,
                ),
            ),
            smoke._write_stage(
                out_dir,
                smoke.SmokeStage(
                    name=smoke.STAGE_ODB,
                    status=smoke.STATUS_COMPLETED,
                    evidence=["kpis=['MISES_MAX', 'U_tip']"],
                    real_env_required=True,
                    real_env_verified=True,
                ),
            ),
        ]

    monkeypatch.setattr(smoke, "_prepare_input_stage", fake_prepare)
    monkeypatch.setattr(smoke, "_mock_or_real_stages", fake_real_stages)

    report, code = smoke.collect_smoke_evidence(mode="require-real", out_dir=tmp_path)

    assert code == 0
    assert report["overall_status"] == "real-env-verified"
    assert report["real_env_verified"] is True
    contract_diff = _stage(report, smoke.STAGE_CONTRACT_DIFF)
    assert contract_diff["status"] == "completed"
    assert contract_diff["real_env_verified"] is True
    assert any("overall_status=FAIL" in item for item in contract_diff["evidence"])
    assert report["contract_diff"]["workflow"] == "real-smoke-contract-diff"
    assert report["contract_diff"]["overall_status"] == "FAIL"
    assert Path(report["contract_diff"]["report_path"]).exists()
    assert Path(report["contract_diff"]["html_path"]).exists()
    capsule_manifest = json.loads(
        (tmp_path / "capsule" / "cantilever-require-real" / "capsule.json").read_text()
    )
    artifact_names = {entry["name"] for entry in capsule_manifest["artifacts"]}
    assert {
        "real_smoke_contract_diff.json",
        "real_smoke_contract_diff.md",
        "real_smoke_contract_diff.html",
    } <= artifact_names


def test_json_cli_output_has_stable_stage_fields(monkeypatch, tmp_path, capsys):
    _clear_real_abaqus_env(monkeypatch, tmp_path)

    code = smoke.run(["--dry-run", "--json", "--out-dir", str(tmp_path)])
    data = json.loads(capsys.readouterr().out)

    assert code == 0
    assert data["schema_version"] == "1.0"
    assert data["project"] == "abaqus-agent"
    assert data["stages"]
    assert {
        "name",
        "status",
        "command",
        "evidence",
        "real_env_required",
        "real_env_verified",
        "missing_reason",
        "artifact_path",
    } <= set(data["stages"][0])
