import json
import zipfile
from pathlib import Path

from scripts.run_local_demo_pack import create_local_demo_pack
from scripts.verify_local_demo_pack_bundle import (
    main,
    verify_demo_pack_bundle,
    verify_demo_pack_bundle_bytes,
)


def test_verify_local_demo_pack_bundle_passes_for_generated_pack(tmp_path):
    index = create_local_demo_pack(tmp_path / "demo-pack")

    result = verify_demo_pack_bundle(index["pack_zip_path"])

    assert result["workflow"] == "local-demo-pack-bundle-verify"
    assert result["bundle_workflow"] == "local-demo-pack"
    assert result["bundle_overall_status"] == "PASS"
    assert result["overall_status"] == "PASS"
    assert result["checked_file_count"] == 31
    assert all(item["status"] == "PASS" for item in result["files"])
    assert "local-demo-pack-manifest.json" in result["zip_members"]


def test_verify_local_demo_pack_bundle_cli_json(tmp_path, capsys):
    index = create_local_demo_pack(tmp_path / "demo-pack")

    exit_code = main([index["pack_zip_path"], "--json"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["overall_status"] == "PASS"
    assert output["checked_file_count"] == 31


def test_verify_local_demo_pack_bundle_bytes(tmp_path):
    index = create_local_demo_pack(tmp_path / "demo-pack")

    result = verify_demo_pack_bundle_bytes(
        Path(index["pack_zip_path"]).read_bytes(),
        zip_path="copied-local-demo-pack.zip",
    )

    assert result["zip_path"] == "copied-local-demo-pack.zip"
    assert result["overall_status"] == "PASS"
    assert result["checked_file_count"] == 31


def test_verify_local_demo_pack_bundle_fails_for_missing_file(tmp_path):
    index = create_local_demo_pack(tmp_path / "demo-pack")
    broken_zip = tmp_path / "missing-member.zip"
    _rewrite_zip(
        Path(index["pack_zip_path"]),
        broken_zip,
        skip_members={"simulation-diff/diff.md"},
    )

    result = verify_demo_pack_bundle(broken_zip)

    assert result["overall_status"] == "FAIL"
    statuses = {item["filename"]: item["status"] for item in result["files"]}
    assert statuses["simulation-diff/diff.md"] == "MISSING"


def test_verify_local_demo_pack_bundle_fails_for_size_mismatch(tmp_path):
    index = create_local_demo_pack(tmp_path / "demo-pack")
    broken_zip = tmp_path / "size-mismatch.zip"
    manifest = _read_manifest(index["pack_zip_path"])
    manifest["files"][0]["size_bytes"] += 1
    _rewrite_zip(
        Path(index["pack_zip_path"]),
        broken_zip,
        replacements={"local-demo-pack-manifest.json": json.dumps(manifest).encode()},
    )

    result = verify_demo_pack_bundle(broken_zip)

    assert result["overall_status"] == "FAIL"
    assert result["files"][0]["status"] == "SIZE_MISMATCH"


def test_verify_local_demo_pack_bundle_fails_for_sha_mismatch(tmp_path):
    index = create_local_demo_pack(tmp_path / "demo-pack")
    broken_zip = tmp_path / "sha-mismatch.zip"
    manifest = _read_manifest(index["pack_zip_path"])
    manifest["files"][0]["sha256"] = "0" * 64
    _rewrite_zip(
        Path(index["pack_zip_path"]),
        broken_zip,
        replacements={"local-demo-pack-manifest.json": json.dumps(manifest).encode()},
    )

    result = verify_demo_pack_bundle(broken_zip)

    assert result["overall_status"] == "FAIL"
    assert result["files"][0]["status"] == "SHA256_MISMATCH"


def test_verify_local_demo_pack_bundle_fails_for_unsafe_manifest_name(tmp_path):
    index = create_local_demo_pack(tmp_path / "demo-pack")
    broken_zip = tmp_path / "unsafe-name.zip"
    manifest = _read_manifest(index["pack_zip_path"])
    manifest["files"][0]["filename"] = "../index.json"
    _rewrite_zip(
        Path(index["pack_zip_path"]),
        broken_zip,
        replacements={"local-demo-pack-manifest.json": json.dumps(manifest).encode()},
    )

    result = verify_demo_pack_bundle(broken_zip)

    assert result["overall_status"] == "FAIL"
    assert result["files"][0]["status"] == "UNSAFE_NAME"


def test_verify_local_demo_pack_bundle_fails_for_missing_manifest(tmp_path):
    index = create_local_demo_pack(tmp_path / "demo-pack")
    broken_zip = tmp_path / "missing-manifest.zip"
    _rewrite_zip(
        Path(index["pack_zip_path"]),
        broken_zip,
        skip_members={"local-demo-pack-manifest.json"},
    )

    result = verify_demo_pack_bundle(broken_zip)

    assert result["overall_status"] == "FAIL"
    assert result["error"] == "Missing local-demo-pack-manifest.json"


def test_verify_local_demo_pack_bundle_fails_for_invalid_zip(tmp_path):
    broken_zip = tmp_path / "not-a-zip.zip"
    broken_zip.write_text("not a zip", encoding="utf-8")

    result = verify_demo_pack_bundle(broken_zip)

    assert result["overall_status"] == "FAIL"
    assert "Invalid ZIP bundle" in result["error"]


def test_verify_local_demo_pack_bundle_cli_fails_for_missing_path(capsys):
    exit_code = main(["/tmp/abaqus-agent-missing-demo-pack.zip", "--json"])

    assert exit_code == 1
    output = json.loads(capsys.readouterr().out)
    assert output["overall_status"] == "FAIL"
    assert "No such file or directory" in output["error"]


def _read_manifest(zip_path: str | Path) -> dict:
    with zipfile.ZipFile(zip_path) as bundle:
        return json.loads(bundle.read("local-demo-pack-manifest.json"))


def _rewrite_zip(
    source_zip: Path,
    target_zip: Path,
    *,
    skip_members: set[str] | None = None,
    replacements: dict[str, bytes] | None = None,
) -> None:
    skip_members = skip_members or set()
    replacements = replacements or {}
    with (
        zipfile.ZipFile(source_zip) as source,
        zipfile.ZipFile(target_zip, "w", compression=zipfile.ZIP_DEFLATED) as target,
    ):
        for name in source.namelist():
            if name in skip_members:
                continue
            target.writestr(name, replacements.get(name, source.read(name)))
