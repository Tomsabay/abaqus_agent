import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts import render_smoke_evidence_report as report
from scripts import run_real_abaqus_smoke as smoke


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


def test_render_markdown_preserves_dry_run_verification_boundary(monkeypatch, tmp_path):
    _clear_real_abaqus_env(monkeypatch, tmp_path)
    evidence, code = smoke.collect_smoke_evidence(mode="dry-run", out_dir=tmp_path)

    assert code == 0
    markdown = report.render_markdown(evidence, source_path=tmp_path / "smoke_evidence.json")

    assert "# Abaqus Smoke Evidence Report" in markdown
    assert "- Mode: `dry-run`" in markdown
    assert "- Real Abaqus verified: `false`" in markdown
    assert "not proof of real Abaqus end-to-end execution" in markdown
    assert "| syntaxcheck | dry-run | true | false |" in markdown
    assert "Dry-run does not invoke Abaqus syntaxcheck." in markdown


def test_cli_writes_markdown_report(monkeypatch, tmp_path):
    _clear_real_abaqus_env(monkeypatch, tmp_path)
    smoke.collect_smoke_evidence(mode="dry-run", out_dir=tmp_path)
    out_path = tmp_path / "smoke_evidence.md"

    code = report.run([str(tmp_path / "smoke_evidence.json"), "--out", str(out_path)])

    assert code == 0
    text = out_path.read_text(encoding="utf-8")
    assert "## Stage Summary" in text
    assert "environment_preflight" in text
    assert "real_env_prerequisites_ready=False" in text


def test_cli_reports_missing_evidence(tmp_path, capsys):
    missing = tmp_path / "missing.json"

    code = report.run([str(missing)])

    assert code == 2
    assert "smoke evidence not found" in capsys.readouterr().err


def test_load_evidence_rejects_json_without_stage_array(tmp_path):
    path = tmp_path / "smoke_evidence.json"
    path.write_text(json.dumps({"project": "abaqus-agent"}), encoding="utf-8")

    try:
        report.load_evidence(path)
    except ValueError as exc:
        assert "stages[] array" in str(exc)
    else:
        raise AssertionError("expected ValueError")
