import json

import pytest

from doctor.solver_doctor import (
    diagnose_job_logs,
    diagnose_log_texts,
    list_doctor_patterns,
    main,
    render_markdown,
)


def test_solver_doctor_reports_completed_job_with_no_findings(tmp_path):
    (tmp_path / "Job-1.log").write_text("Abaqus JOB Job-1 COMPLETED\n", encoding="utf-8")

    report = diagnose_job_logs(tmp_path, "Job-1")

    assert report.status == "COMPLETED"
    assert report.primary_category == "UNKNOWN"
    assert report.completed
    assert report.findings == []
    assert "completed" in report.summary.lower()


def test_solver_doctor_detects_common_log_categories(tmp_path):
    (tmp_path / "Job-1.msg").write_text(
        "\n".join(
            [
                "STEP     1  INCREMENT     5",
                "***ERROR: THE SOLUTION HAS NOT CONVERGED",
                "***ERROR: EXCESSIVE DISTORTION OF ELEMENTS 123, 456",
                "***ERROR: Abaqus Error: License checkout failed",
                "***ERROR: The database was created by a newer release of Abaqus",
                "***ERROR: The system cannot find the path specified",
                "***WARNING: ZERO PIVOT DETECTED AT DOF 3 NODE 100",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "Job-1.dat").write_text(
        "\n".join(
            [
                "***ERROR: Unknown keyword *BODNARY",
                "***ERROR: INSUFFICIENT MEMORY FOR SOLVER",
                "***WARNING: Output request UVARM is not available",
            ]
        ),
        encoding="utf-8",
    )

    report = diagnose_job_logs(tmp_path, "Job-1")
    categories = {finding.category for finding in report.findings}

    assert report.status == "FAILED"
    assert "CONVERGENCE" in categories
    assert "ELEMENT_DISTORTION" in categories
    assert "LICENSE" in categories
    assert "ODB" in categories
    assert "PATH" in categories
    assert "RIGID_BODY_MOTION" in categories
    assert "SYNTAX" in categories
    assert "MEMORY" in categories
    assert "OUTPUT" in categories
    assert any("license server" in finding.recommendation.lower() for finding in report.findings)
    assert all(finding.source_file for finding in report.findings)


def test_solver_doctor_markdown_contains_evidence_table(tmp_path):
    (tmp_path / "Job-1.msg").write_text(
        "***ERROR: TOO MANY ATTEMPTS MADE FOR THIS INCREMENT\n",
        encoding="utf-8",
    )

    report = diagnose_job_logs(tmp_path, "Job-1")
    markdown = render_markdown(report)

    assert "# Solver Doctor: Job-1" in markdown
    assert "| Severity | Category | Source | Message | Recommendation |" in markdown
    assert "CONVERGENCE" in markdown
    assert "Job-1.msg:1" in markdown


def test_solver_doctor_cli_writes_json_and_markdown(tmp_path):
    (tmp_path / "Job-1.dat").write_text(
        "***ERROR: License server is down or not responding\n",
        encoding="utf-8",
    )
    json_out = tmp_path / "doctor.json"
    markdown_out = tmp_path / "doctor.md"

    assert main([str(tmp_path), "Job-1", "--out", str(json_out)]) == 0
    data = json.loads(json_out.read_text(encoding="utf-8"))
    assert data["status"] == "FAILED"
    assert data["findings"][0]["category"] == "LICENSE"

    assert main([str(tmp_path), "Job-1", "--format", "markdown", "--out", str(markdown_out)]) == 0
    assert "Solver Doctor" in markdown_out.read_text(encoding="utf-8")


def test_solver_doctor_diagnoses_supplied_log_texts(tmp_path):
    report = diagnose_log_texts(
        job_name="Job-Text",
        logs={
            "msg": "***ERROR: TOO MANY ATTEMPTS MADE FOR THIS INCREMENT\n",
            ".log": "Abaqus JOB Job-Text\n",
        },
        workdir=tmp_path,
    )

    assert report.job_name == "Job-Text"
    assert report.status == "FAILED"
    assert report.primary_category == "CONVERGENCE"
    assert any(path.endswith("Job-Text.msg") for path in report.evidence_files)


def test_solver_doctor_rejects_bad_text_payloads():
    with pytest.raises(ValueError, match="job_name"):
        diagnose_log_texts(job_name="../bad", logs={"msg": "x"})
    with pytest.raises(ValueError, match="At least one"):
        diagnose_log_texts(job_name="Job-1", logs={"msg": ""})
    with pytest.raises(ValueError, match="Unsupported"):
        diagnose_log_texts(job_name="Job-1", logs={"odb": "x"})


def test_solver_doctor_pattern_gallery_lists_and_filters_patterns():
    gallery = list_doctor_patterns()

    assert gallery["workflow"] == "solver-doctor-pattern-gallery"
    assert gallery["real_env_verified"] is False
    assert gallery["total"] >= 20
    assert ".msg" in gallery["supported_source_files"]
    assert any(category["category"] == "LICENSE" for category in gallery["categories"])
    assert any(pattern["category"] == "CONVERGENCE" for pattern in gallery["patterns"])
    assert all(pattern["recommendation"] for pattern in gallery["patterns"])

    license_errors = list_doctor_patterns(category="license", severity="error")
    assert license_errors["filters"] == {"category": "LICENSE", "severity": "ERROR"}
    assert license_errors["total"] >= 1
    assert {pattern["category"] for pattern in license_errors["patterns"]} == {"LICENSE"}
    assert {pattern["severity"] for pattern in license_errors["patterns"]} == {"ERROR"}
