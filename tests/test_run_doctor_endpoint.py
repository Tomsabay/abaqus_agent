"""GET /api/run/{run_id}/doctor — the diagnosis a failed run shows.

Two properties matter more than the happy path and are asserted hardest here:

  * the endpoint never invents an explanation. When no pattern matches, it says
    so and still hands back the solver's own words.
  * it validates the job name. ``diagnose_job_logs`` does not (only
    ``diagnose_log_texts`` does), and the name comes from user-supplied
    ``meta.model_name``, which schema/spec_schema.json constrains only to
    minLength 1. Without validation the endpoint is an arbitrary-file-read.

Hermetic: no Abaqus, no CalculiX, no solve. Logs are written as plain text.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

NONCONVERGENCE_MSG = (
    " ***ERROR: TOO MANY ATTEMPTS MADE FOR THIS INCREMENT: ANALYSIS TERMINATED\n"
)


@pytest.fixture
def server_app(monkeypatch, tmp_path):
    import server

    monkeypatch.setenv("ABAQUS_AGENT_EVIDENCE_VAULT", str(tmp_path / "vault"))
    original_runs = dict(server.RUNS)
    server.RUNS.clear()
    try:
        yield server
    finally:
        server.RUNS.clear()
        server.RUNS.update(original_runs)


def _seed_run(server, run_id: str, workdir: Path, *, model_name: str = "Job-1",
              status: str = "FAILED", error: dict | None = None,
              **extra) -> dict:
    run = {
        "run_id": run_id,
        "status": status,
        "started_at": time.time(),
        "workdir": str(workdir),
        "spec": {"meta": {"model_name": model_name}},
        "stages": {},
        "kpis": {},
    }
    if error is not None:
        run["error"] = error
    run.update(extra)
    server.RUNS[run_id] = run
    return run


def test_returns_findings_for_a_failed_run(server_app, tmp_path) -> None:
    workdir = tmp_path / "run"
    workdir.mkdir()
    (workdir / "Job-1.msg").write_text(NONCONVERGENCE_MSG, encoding="utf-8")
    _seed_run(server_app, "r-nonconv", workdir,
              error={"error_code": "NONCONVERGENCE", "message": "job failed"})

    client = TestClient(server_app.app, raise_server_exceptions=False)
    resp = client.get("/api/run/r-nonconv/doctor")
    assert resp.status_code == 200
    data = resp.json()

    assert data["matched"] is True
    assert data["findings"], "a known nonconvergence banner must produce a finding"
    assert data["source"] == "solver_doctor"
    # The raw error survives alongside the interpretation.
    assert data["error"]["error_code"] == "NONCONVERGENCE"
    joined = " ".join(
        (f.get("message") or "") + (f.get("recommendation") or "")
        for f in data["findings"]
    )
    assert joined.strip(), "a finding with no message or recommendation is useless"


def test_reports_no_match_without_inventing_one(server_app, tmp_path) -> None:
    workdir = tmp_path / "run"
    workdir.mkdir()
    (workdir / "Job-1.msg").write_text(
        "something the pattern library has never seen\n", encoding="utf-8")
    _seed_run(server_app, "r-unknown", workdir,
              error={"error_code": "JOB_FAILED", "message": "opaque failure"})

    client = TestClient(server_app.app, raise_server_exceptions=False)
    data = client.get("/api/run/r-unknown/doctor").json()

    assert data["matched"] is False
    assert data["findings"] == []
    # Still echoes the solver's own words — that is the fallback, not a blank.
    assert data["error"]["message"] == "opaque failure"


def test_degrades_to_raw_error_when_workdir_missing(server_app) -> None:
    server_app.RUNS["r-nodir"] = {
        "run_id": "r-nodir",
        "status": "FAILED",
        "started_at": time.time(),
        "spec": {"meta": {"model_name": "Job-1"}},
        "error": {"error_code": "ABAQUS_NOT_FOUND", "message": "no solver"},
    }
    client = TestClient(server_app.app, raise_server_exceptions=False)
    data = client.get("/api/run/r-nodir/doctor").json()

    assert data["findings"] == []
    assert data["error"]["error_code"] == "ABAQUS_NOT_FOUND"


def test_refused_run_surfaces_kpi_notice_and_limitations(server_app) -> None:
    """A backend refusal is COMPLETED-adjacent, not a crash — it still needs a panel."""
    server_app.RUNS["r-refused"] = {
        "run_id": "r-refused",
        "status": "REFUSED",
        "started_at": time.time(),
        "spec": {"meta": {"model_name": "Job-1"}},
        "kpi_notice": "CalculiX 2.23 无法忠实求解这个问题，因此没有输出任何数值",
        "limitations": [{"feature": "bc_load.load_type", "value": "blast_conwep",
                         "reason": "CalculiX 不认识 CONWEP 爆炸载荷"}],
    }
    client = TestClient(server_app.app, raise_server_exceptions=False)
    data = client.get("/api/run/r-refused/doctor").json()

    assert "没有输出任何数值" in data["kpi_notice"]
    assert data["limitations"][0]["feature"] == "bc_load.load_type"


@pytest.mark.parametrize("evil", ["../../etc/passwd", "..\\..\\secrets", "a/b", ".."])
def test_rejects_traversing_model_name(server_app, tmp_path, evil) -> None:
    workdir = tmp_path / "run"
    workdir.mkdir()
    _seed_run(server_app, "r-evil", workdir, model_name=evil)

    client = TestClient(server_app.app, raise_server_exceptions=False)
    resp = client.get("/api/run/r-evil/doctor")
    assert resp.status_code == 400, (
        "diagnose_job_logs builds workdir/<model_name><suffix> without validating; "
        "the endpoint must reject the name itself"
    )


def test_404_for_unknown_run(server_app) -> None:
    client = TestClient(server_app.app, raise_server_exceptions=False)
    assert client.get("/api/run/does-not-exist/doctor").status_code == 404


def test_writes_no_vault_entry(server_app, tmp_path, monkeypatch) -> None:
    """Unlike POST /api/doctor/diagnose, this is hit on every page view."""
    vault = tmp_path / "vault"
    monkeypatch.setenv("ABAQUS_AGENT_EVIDENCE_VAULT", str(vault))
    workdir = tmp_path / "run"
    workdir.mkdir()
    (workdir / "Job-1.msg").write_text(NONCONVERGENCE_MSG, encoding="utf-8")
    _seed_run(server_app, "r-vault", workdir)

    client = TestClient(server_app.app, raise_server_exceptions=False)
    before = len(list(vault.rglob("*"))) if vault.exists() else 0
    for _ in range(3):
        assert client.get("/api/run/r-vault/doctor").status_code == 200
    after = len(list(vault.rglob("*"))) if vault.exists() else 0

    assert before == after, "the read-only view must not create vault entries"
    assert not (workdir / "doctor.json").exists()
    assert not (workdir / "doctor.md").exists()
