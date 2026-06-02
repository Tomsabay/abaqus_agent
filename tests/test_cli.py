"""Tests for the abaqus-agent command line interface."""

from __future__ import annotations

import json

import yaml

import cli


def test_no_args_keeps_server_default(monkeypatch):
    called = {}

    def fake_serve(_args):
        called["serve"] = True
        return 0

    monkeypatch.setattr(cli, "_cmd_serve", fake_serve)
    assert cli.main([]) == 0
    assert called["serve"] is True


def test_capsule_init_cli(tmp_path, capsys):
    inp = tmp_path / "model.inp"
    inp.write_text("*Heading\nmodel\n", encoding="utf-8")
    out = tmp_path / "capsule"

    rc = cli.main(["capsule", "init", "--from-inp", str(inp), "--out", str(out)])

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert rc == 0
    assert data["inputs"]["model_name"] == "model"
    assert (out / "capsule.json").exists()


def test_doctor_cli_directory_mode(tmp_path, capsys):
    (tmp_path / "job.msg").write_text("Too many attempts made for this increment\n", encoding="utf-8")

    rc = cli.main(["doctor", str(tmp_path)])

    out = capsys.readouterr().out
    assert rc == 0
    assert "too_many_attempts" in out


def test_doctor_cli_writes_expanded_pattern_report(tmp_path):
    msg = tmp_path / "job.msg"
    report = tmp_path / "doctor.md"
    msg.write_text("Node set FIXED_NODES has not been defined\n", encoding="utf-8")

    rc = cli.main(["doctor", str(msg), "--out", str(report)])

    text = report.read_text(encoding="utf-8")
    assert rc == 0
    assert "Solver Doctor Report" in text
    assert "missing_node_set" in text


def test_doctor_cli_missing_path_returns_2(tmp_path, capsys):
    rc = cli.main(["doctor", str(tmp_path / "missing.msg")])

    err = capsys.readouterr().err
    assert rc == 2
    assert "Path not found" in err


def test_check_cli_writes_markdown_and_sets_exit_code(tmp_path):
    kpis = tmp_path / "kpis.json"
    contracts = tmp_path / "contracts.yaml"
    report = tmp_path / "contracts.md"
    kpis.write_text(json.dumps({"U_tip": 0.002}), encoding="utf-8")
    contracts.write_text(
        yaml.safe_dump({
            "contracts": [
                {"name": "down", "type": "direction", "kpi": "U_tip", "direction": "negative"}
            ]
        }),
        encoding="utf-8",
    )

    rc = cli.main(["check", str(kpis), str(contracts), "--out", str(report)])

    assert rc == 1
    assert "Physics Contract Report" in report.read_text(encoding="utf-8")
    assert "FAIL" in report.read_text(encoding="utf-8")


def test_diff_cli_writes_markdown(tmp_path):
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    report = tmp_path / "diff.md"
    baseline.write_text(json.dumps({"kpis": {"MISES": 100.0}}), encoding="utf-8")
    candidate.write_text(json.dumps({"kpis": {"MISES": 101.0}}), encoding="utf-8")

    rc = cli.main(["diff", str(baseline), str(candidate), "--out", str(report)])

    assert rc == 0
    text = report.read_text(encoding="utf-8")
    assert "Simulation Diff Report" in text
    assert "MISES" in text


def test_memory_search_cli_prints_json(tmp_path, capsys):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "capsule.json").write_text(
        json.dumps({
            "schema_version": "0.2.0-dev",
            "run_id": "memory_cli",
            "created_at": "2026-06-02T10:00:00",
            "inputs": {"model_name": "MemoryCliModel"},
            "artifacts": {},
            "provenance": {"status": "COMPLETED"},
        }),
        encoding="utf-8",
    )

    rc = cli.main([
        "memory", "search", str(tmp_path),
        "--query", "MemoryCliModel",
        "--sort-by", "run_id",
        "--sort-order", "asc",
        "--min-score", "0.5",
        "--json",
    ])

    data = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert data["matches"][0]["run_id"] == "memory_cli"
    assert data["query"]["sort_by"] == "run_id"
    assert data["query"]["sort_order"] == "asc"
    assert data["query"]["min_score"] == 0.5
