import hashlib
import json
import subprocess
import sys
import zipfile
from io import BytesIO
from pathlib import Path

from scripts import run_local_cli_smoke as smoke
from scripts import verify_local_cli_smoke_bundle as smoke_verify

ROOT = Path(__file__).resolve().parent.parent


def test_local_cli_smoke_writes_report_and_exercises_cli_surfaces(tmp_path):
    code = smoke.run(["--out-dir", str(tmp_path), "--json"])

    assert code == 0
    report = json.loads((tmp_path / "local_cli_smoke.json").read_text(encoding="utf-8"))
    assert report["workflow"] == "local-cli-smoke"
    assert report["overall_status"] == "PASS"
    assert report["real_env_verified"] is False
    assert Path(report["demo_pack_index"]).exists()
    assert Path(report["vault_root"]).exists()
    assert report["smoke_vault_id"].startswith("local-cli-smoke-")
    assert set(report["smoke_vault_files"]) == {
        "copied-local-demo-pack.zip",
        "local_cli_smoke.html",
        "local_cli_smoke.json",
        "local_cli_smoke_manifest.json",
        "local_cli_smoke.md",
        "local_cli_smoke.zip",
    }
    assert {step["name"] for step in report["steps"]} == {
        "evidence-vault-list",
        "evidence-vault-detail",
        "evidence-vault-read",
        "evidence-vault-copy",
        "case-memory-search",
        "case-memory-detail",
        "case-memory-diff",
        "kpi-recipes-list",
        "kpi-recipes-export",
        "solver-doctor-patterns-list",
        "solver-doctor-patterns-detail",
    }
    assert all(step["status"] == "PASS" for step in report["steps"])
    assert (tmp_path / "copied-local-demo-pack.zip").exists()
    assert (tmp_path / "modal-kpi-spec.json").exists()
    assert (tmp_path / "case-memory-diff" / "diff.md").exists()
    markdown = (tmp_path / "local_cli_smoke.md").read_text(encoding="utf-8")
    assert "Abaqus Agent Local CLI Smoke" in markdown
    assert report["smoke_vault_id"] in markdown
    assert "does not invoke Abaqus" in markdown
    html = (tmp_path / "local_cli_smoke.html").read_text(encoding="utf-8")
    assert "Abaqus Agent Local CLI Smoke" in html
    assert "Smoke Steps" in html
    assert report["smoke_vault_id"] in html
    assert "does not invoke Abaqus" in html
    assert Path(report["zip_path"]).exists()
    with zipfile.ZipFile(report["zip_path"]) as bundle:
        assert set(bundle.namelist()) == {
            "copied-local-demo-pack.zip",
            "local_cli_smoke.html",
            "local_cli_smoke.json",
            "local_cli_smoke_manifest.json",
            "local_cli_smoke.md",
        }
        bundled_report = json.loads(bundle.read("local_cli_smoke.json"))
        assert bundled_report["smoke_vault_id"] == report["smoke_vault_id"]
        manifest = json.loads(bundle.read("local_cli_smoke_manifest.json"))
        assert manifest["workflow"] == "local-cli-smoke"
        assert manifest["smoke_vault_id"] == report["smoke_vault_id"]
        manifest_files = {item["filename"]: item for item in manifest["files"]}
        assert "copied-local-demo-pack.zip" in manifest_files
        assert len(manifest_files["copied-local-demo-pack.zip"]["sha256"]) == 64

    vault_result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "inspect_evidence_vault.py"),
            "--root",
            report["vault_root"],
            "list",
            "--query",
            "local_cli_smoke.md",
            "--kind",
            "local-cli-smoke",
            "--status",
            "PASS",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    vault_data = json.loads(vault_result.stdout)
    assert vault_data["total"] == 1
    assert vault_data["items"][0]["vault_id"] == report["smoke_vault_id"]

    memory_result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "inspect_case_memory.py"),
            "--root",
            report["vault_root"],
            "search",
            "--query",
            "local_cli_smoke.md",
            "--kind",
            "local-cli-smoke",
            "--status",
            "PASS",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    memory_data = json.loads(memory_result.stdout)
    assert memory_data["total"] == 1
    assert memory_data["items"][0]["memory_id"] == report["smoke_vault_id"]

    verify_result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "inspect_evidence_vault.py"),
            "--root",
            report["vault_root"],
            "verify-smoke",
            report["smoke_vault_id"],
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    verify_data = json.loads(verify_result.stdout)
    assert verify_data["vault_id"] == report["smoke_vault_id"]
    assert verify_data["filename"] == "local_cli_smoke.zip"
    assert verify_data["overall_status"] == "PASS"
    assert verify_data["checked_file_count"] == 4
    assert all(item["status"] == "PASS" for item in verify_data["files"])


def test_verify_local_cli_smoke_bundle_checks_manifest_hashes(tmp_path):
    assert smoke.run(["--out-dir", str(tmp_path), "--json"]) == 0

    verify_result = smoke_verify.verify_smoke_bundle(tmp_path / "local_cli_smoke.zip")
    assert verify_result["overall_status"] == "PASS"
    assert verify_result["checked_file_count"] == 4
    assert verify_result["copied_demo_pack_verification"]["overall_status"] == "PASS"
    assert verify_result["copied_demo_pack_verification"]["checked_file_count"] == 31
    assert {item["filename"] for item in verify_result["files"]} == {
        "copied-local-demo-pack.zip",
        "local_cli_smoke.html",
        "local_cli_smoke.json",
        "local_cli_smoke.md",
    }
    assert all(item["status"] == "PASS" for item in verify_result["files"])

    tampered_zip = tmp_path / "tampered-local-cli-smoke.zip"
    with zipfile.ZipFile(tmp_path / "local_cli_smoke.zip") as source:
        with zipfile.ZipFile(tampered_zip, "w", zipfile.ZIP_DEFLATED) as target:
            for info in source.infolist():
                content = source.read(info.filename)
                if info.filename == "local_cli_smoke.md":
                    content += b"\nTampered evidence text.\n"
                target.writestr(info, content)

    tampered_result = smoke_verify.verify_smoke_bundle(tampered_zip)
    assert tampered_result["overall_status"] == "FAIL"
    tampered_file = next(
        item for item in tampered_result["files"] if item["filename"] == "local_cli_smoke.md"
    )
    assert tampered_file["status"] == "SIZE_MISMATCH"

    nested_tampered_zip = tmp_path / "nested-tampered-local-cli-smoke.zip"
    with zipfile.ZipFile(tmp_path / "local_cli_smoke.zip") as source:
        copied_demo_pack = source.read("copied-local-demo-pack.zip")
        tampered_demo_pack = _tamper_demo_pack_manifest_hash(copied_demo_pack)
        smoke_manifest = json.loads(source.read("local_cli_smoke_manifest.json"))
        for item in smoke_manifest["files"]:
            if item["filename"] == "copied-local-demo-pack.zip":
                item["size_bytes"] = len(tampered_demo_pack)
                item["sha256"] = hashlib.sha256(tampered_demo_pack).hexdigest()
        with zipfile.ZipFile(nested_tampered_zip, "w", zipfile.ZIP_DEFLATED) as target:
            for info in source.infolist():
                content = source.read(info.filename)
                if info.filename == "copied-local-demo-pack.zip":
                    content = tampered_demo_pack
                elif info.filename == "local_cli_smoke_manifest.json":
                    content = json.dumps(smoke_manifest, indent=2, sort_keys=True).encode()
                target.writestr(info, content)

    nested_tampered_result = smoke_verify.verify_smoke_bundle(nested_tampered_zip)
    assert nested_tampered_result["overall_status"] == "FAIL"
    assert all(item["status"] == "PASS" for item in nested_tampered_result["files"])
    nested_verification = nested_tampered_result["copied_demo_pack_verification"]
    assert nested_verification["overall_status"] == "FAIL"
    nested_file = next(item for item in nested_verification["files"] if item["filename"] == "index.json")
    assert nested_file["status"] == "SHA256_MISMATCH"


def _tamper_demo_pack_manifest_hash(zip_bytes: bytes) -> bytes:
    source_buffer = BytesIO(zip_bytes)
    target_buffer = BytesIO()
    with zipfile.ZipFile(source_buffer) as source:
        manifest = json.loads(source.read("local-demo-pack-manifest.json"))
        manifest["files"][0]["sha256"] = "0" * 64
        with zipfile.ZipFile(target_buffer, "w", zipfile.ZIP_DEFLATED) as target:
            for info in source.infolist():
                content = source.read(info.filename)
                if info.filename == "local-demo-pack-manifest.json":
                    content = json.dumps(manifest, indent=2, sort_keys=True).encode()
                target.writestr(info, content)
    return target_buffer.getvalue()
