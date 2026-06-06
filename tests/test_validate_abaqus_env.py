import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts import validate_abaqus_env as validator


def _capability(report, name):
    return next(cap for cap in report["capabilities"] if cap["name"] == name)


def _no_abaqus(_cmd):
    return None


def test_default_without_abaqus_exits_zero_and_reports_environment_limited():
    report = validator.collect_report(mode="default", env={}, which=_no_abaqus)

    assert validator.exit_code_for_report(report, require_real=False, dry_run=False) == 0
    assert report["real_env_prerequisites_ready"] is False
    assert report["real_abaqus_e2e_verified"] is False

    abaqus = _capability(report, "abaqus_executable")
    e2e = _capability(report, "real_abaqus_e2e_pipeline")

    assert abaqus["status"] == validator.STATUS_MISSING
    assert abaqus["missing_reason"]
    assert e2e["status"] == validator.STATUS_ENV_LIMITED
    assert e2e["real_env_verified"] is False


def test_require_real_without_abaqus_exits_nonzero(capsys):
    code = validator.run(["--require-real"], env={}, which=_no_abaqus)
    output = capsys.readouterr().out

    assert code == 2
    assert "require-real missing:" in output
    assert "abaqus_executable" in output


def test_simulated_abaqus_executable_upgrades_probe_but_not_e2e(tmp_path):
    fake_abaqus = tmp_path / "abaqus"
    fake_abaqus.write_text("#!/bin/sh\n", encoding="utf-8")

    report = validator.collect_report(
        mode="default",
        env={"ABAQUS_EXECUTABLE": str(fake_abaqus)},
        which=_no_abaqus,
    )

    abaqus = _capability(report, "abaqus_executable")
    syntaxcheck = _capability(report, "syntaxcheck_prerequisites")
    submit = _capability(report, "submit_monitor_prerequisites")
    e2e = _capability(report, "real_abaqus_e2e_pipeline")

    assert abaqus["status"] == validator.STATUS_AVAILABLE
    assert abaqus["real_env_verified"] is True
    assert syntaxcheck["status"] == validator.STATUS_CANDIDATE
    assert submit["status"] == validator.STATUS_ENV_LIMITED
    assert e2e["status"] == validator.STATUS_ENV_LIMITED
    assert e2e["real_env_verified"] is False


def test_simulated_abaqus_and_license_hint_make_real_prerequisites_candidate(tmp_path):
    fake_abaqus = tmp_path / "abaqus"
    fake_abaqus.write_text("#!/bin/sh\n", encoding="utf-8")

    report = validator.collect_report(
        mode="require-real",
        env={"ABAQUS_EXECUTABLE": str(fake_abaqus), "LM_LICENSE_FILE": "27800@example"},
        which=_no_abaqus,
    )

    assert report["real_env_prerequisites_ready"] is True
    assert validator.exit_code_for_report(report, require_real=True, dry_run=False) == 0
    assert _capability(report, "submit_monitor_prerequisites")["status"] == validator.STATUS_CANDIDATE
    assert _capability(report, "odb_kpi_prerequisites")["status"] == validator.STATUS_CANDIDATE
    assert _capability(report, "real_abaqus_e2e_pipeline")["real_env_verified"] is False


def test_json_output_is_parseable_and_has_stable_fields(capsys):
    code = validator.run(["--json", "--dry-run"], env={}, which=_no_abaqus)
    output = capsys.readouterr().out
    data = json.loads(output)

    assert code == 0
    assert data["schema_version"] == "1.0"
    assert data["project"] == "abaqus-agent"
    assert data["mode"] == "dry-run"
    assert isinstance(data["capabilities"], list)
    assert isinstance(data["missing"], list)
    assert {"name", "status", "evidence", "real_env_verified", "missing_reason"} <= set(
        data["capabilities"][0]
    )
