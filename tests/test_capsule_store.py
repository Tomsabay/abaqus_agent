import hashlib
import json

import pytest

from capsule.metadata import evidence_metadata
from capsule.store import MANIFEST_NAME, create_capsule


def test_evidence_metadata_adds_standard_fields_and_extra_values():
    metadata = evidence_metadata(
        workflow="offline-evidence-slice",
        evidence_source="supplied-kpi-json",
        evidence_level="offline",
        overall_status="PASS",
        real_env_required=False,
        real_env_verified=False,
        extra={"case": "cantilever"},
    )

    assert metadata == {
        "metadata_schema_version": "1.0",
        "project": "abaqus-agent",
        "workflow": "offline-evidence-slice",
        "evidence_source": "supplied-kpi-json",
        "evidence_level": "offline",
        "overall_status": "PASS",
        "real_env_required": False,
        "real_env_verified": False,
        "case": "cantilever",
    }


def test_create_capsule_copies_inputs_artifacts_and_writes_manifest(tmp_path):
    spec = tmp_path / "spec.yaml"
    inp = tmp_path / "model.inp"
    report = tmp_path / "report.md"
    spec.write_text("meta:\n  model_name: cantilever\n", encoding="utf-8")
    inp.write_text("*Heading\n", encoding="utf-8")
    report.write_text("# Evidence\n", encoding="utf-8")

    manifest = create_capsule(
        tmp_path / "capsules",
        "run-123",
        inputs=[spec, inp],
        artifacts=[report],
        metadata={"abaqus_version": "not-run", "mode": "fixture"},
    )

    capsule_dir = tmp_path / "capsules" / "run-123"
    stored_manifest = json.loads((capsule_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert stored_manifest == manifest
    assert manifest["schema_version"] == 1
    assert manifest["run_id"] == "run-123"
    assert manifest["metadata"]["mode"] == "fixture"
    assert len(manifest["inputs"]) == 2
    assert len(manifest["artifacts"]) == 1
    assert (capsule_dir / "inputs" / "spec.yaml").read_text(encoding="utf-8") == spec.read_text(encoding="utf-8")
    assert (capsule_dir / "artifacts" / "report.md").read_text(encoding="utf-8") == report.read_text(encoding="utf-8")
    assert manifest["inputs"][0]["sha256"] == hashlib.sha256(spec.read_bytes()).hexdigest()
    assert len(manifest["capsule_hash"]) == 64


def test_create_capsule_keeps_duplicate_filenames_unique(tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    first = left / "job.log"
    second = right / "job.log"
    first.write_text("first\n", encoding="utf-8")
    second.write_text("second\n", encoding="utf-8")

    manifest = create_capsule(tmp_path / "capsules", "run-123", artifacts=[first, second])

    paths = [entry["path"] for entry in manifest["artifacts"]]
    assert paths == ["artifacts/job.log", "artifacts/job-2.log"]
    assert (tmp_path / "capsules" / "run-123" / "artifacts" / "job.log").read_text(encoding="utf-8") == "first\n"
    assert (tmp_path / "capsules" / "run-123" / "artifacts" / "job-2.log").read_text(encoding="utf-8") == "second\n"


def test_create_capsule_missing_file_fails_before_manifest_write(tmp_path):
    with pytest.raises(FileNotFoundError):
        create_capsule(tmp_path / "capsules", "run-123", inputs=[tmp_path / "missing.inp"])

    assert not (tmp_path / "capsules" / "run-123" / MANIFEST_NAME).exists()


def test_create_capsule_requires_run_id(tmp_path):
    with pytest.raises(ValueError, match="run_id"):
        create_capsule(tmp_path / "capsules", "", inputs=[])
