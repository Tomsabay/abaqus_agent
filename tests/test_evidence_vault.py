import json
import subprocess
import sys
from pathlib import Path

import pytest

from evidence.vault import (
    create_vault_entry,
    get_vault_file_path,
    get_vault_record,
    list_vault_entries,
)
from scripts.run_local_demo_pack import create_local_demo_pack

ROOT = Path(__file__).resolve().parent.parent


def test_vault_allows_nested_relative_files(tmp_path):
    source = tmp_path / "source.html"
    source.write_text("<h1>Nested report</h1>", encoding="utf-8")

    record = create_vault_entry(
        kind="demo-pack",
        title="demo-pack",
        files={"offline-demo-gallery/index.html": source},
        root=tmp_path / "vault",
    )

    assert "offline-demo-gallery/index.html" in record["files"]
    stored = get_vault_file_path(
        record["vault_id"],
        "offline-demo-gallery/index.html",
        root=tmp_path / "vault",
    )
    assert stored == tmp_path / "vault" / record["vault_id"] / "offline-demo-gallery" / "index.html"
    assert stored.read_text(encoding="utf-8") == "<h1>Nested report</h1>"

    loaded_record = get_vault_record(record["vault_id"], root=tmp_path / "vault")
    assert loaded_record["vault_id"] == record["vault_id"]
    assert loaded_record["files"]["offline-demo-gallery/index.html"]["size_bytes"] > 0


@pytest.mark.parametrize(
    "filename",
    [
        "",
        "/tmp/report.html",
        "../report.html",
        "offline-demo-gallery/../index.html",
        r"offline-demo-gallery\index.html",
        "offline demo/index.html",
    ],
)
def test_vault_rejects_unsafe_nested_filenames(tmp_path, filename):
    source = tmp_path / "source.html"
    source.write_text("<h1>Nested report</h1>", encoding="utf-8")

    with pytest.raises(ValueError):
        create_vault_entry(
            kind="demo-pack",
            title="demo-pack",
            files={filename: source},
            root=tmp_path / "vault",
        )


def test_vault_list_filters_by_kind_and_summary_status(tmp_path):
    source = tmp_path / "source.json"
    source.write_text('{"ok": true}', encoding="utf-8")
    vault_root = tmp_path / "vault"

    create_vault_entry(
        kind="local-demo-pack",
        title="passing pack",
        files={"index.json": source},
        summary={"overall_status": "PASS"},
        root=vault_root,
    )
    create_vault_entry(
        kind="case-memory-diff",
        title="failing diff",
        files={"diff.json": source},
        summary={"status": "FAIL"},
        root=vault_root,
    )
    create_vault_entry(
        kind="solver-doctor",
        title="failed doctor",
        files={"doctor.json": source},
        summary={"doctor_status": "FAILED"},
        root=vault_root,
    )

    pack_entries = list_vault_entries(
        root=vault_root,
        kind="local-demo-pack",
        status="PASS",
    )
    assert pack_entries["kind"] == "local-demo-pack"
    assert pack_entries["status"] == "pass"
    assert pack_entries["total"] == 1
    assert pack_entries["items"][0]["kind"] == "local-demo-pack"

    failed_entries = list_vault_entries(root=vault_root, status="FAILED")
    assert failed_entries["total"] == 1
    assert failed_entries["items"][0]["kind"] == "solver-doctor"

    title_query_entries = list_vault_entries(root=vault_root, query="failing")
    assert title_query_entries["query"] == "failing"
    assert title_query_entries["total"] == 1
    assert title_query_entries["items"][0]["kind"] == "case-memory-diff"

    filename_query_entries = list_vault_entries(root=vault_root, query="doctor.json")
    assert filename_query_entries["total"] == 1
    assert filename_query_entries["items"][0]["kind"] == "solver-doctor"

    combined_entries = list_vault_entries(
        root=vault_root,
        query="pack",
        kind="local-demo-pack",
        status="PASS",
    )
    assert combined_entries["total"] == 1
    assert combined_entries["items"][0]["title"] == "passing pack"

    missing_entries = list_vault_entries(
        root=vault_root,
        kind="solver-doctor",
        status="PASS",
    )
    assert missing_entries["items"] == []
    assert missing_entries["total"] == 0


def test_inspect_evidence_vault_cli_list_detail_and_read(tmp_path):
    source = tmp_path / "index.md"
    source.write_text("# Demo Pack\nLong report body\n", encoding="utf-8")
    vault_root = tmp_path / "vault"
    record = create_vault_entry(
        kind="local-demo-pack",
        title="CLI Demo Pack",
        files={"index.md": source, "local-demo-pack.zip": source},
        summary={"overall_status": "PASS"},
        root=vault_root,
    )
    script = ROOT / "scripts" / "inspect_evidence_vault.py"

    list_result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(vault_root),
            "list",
            "--query",
            "local-demo-pack.zip",
            "--kind",
            "local-demo-pack",
            "--status",
            "PASS",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    list_data = json.loads(list_result.stdout)
    assert list_data["total"] == 1
    assert list_data["items"][0]["vault_id"] == record["vault_id"]

    detail_result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(vault_root),
            "detail",
            record["vault_id"],
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    detail_data = json.loads(detail_result.stdout)
    assert detail_data["summary"]["overall_status"] == "PASS"

    read_result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(vault_root),
            "read",
            record["vault_id"],
            "index.md",
            "--max-chars",
            "6",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    read_data = json.loads(read_result.stdout)
    assert read_data["truncated"] is True
    assert read_data["content"] == "# Demo"

    zip_result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(vault_root),
            "read",
            record["vault_id"],
            "local-demo-pack.zip",
        ],
        capture_output=True,
        text=True,
    )
    assert zip_result.returncode == 2
    assert "Unsupported text vault file type" in json.loads(zip_result.stdout)["error"]

    copied_zip = tmp_path / "exports" / "local-demo-pack.zip"
    copy_result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(vault_root),
            "copy",
            record["vault_id"],
            "local-demo-pack.zip",
            "--out",
            str(copied_zip),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    copy_data = json.loads(copy_result.stdout)
    assert copy_data["vault_id"] == record["vault_id"]
    assert copy_data["filename"] == "local-demo-pack.zip"
    assert copy_data["output_path"] == str(copied_zip)
    assert copy_data["size_bytes"] == copied_zip.stat().st_size
    assert copied_zip.read_text(encoding="utf-8") == "# Demo Pack\nLong report body\n"


def test_inspect_evidence_vault_cli_verify_demo_pack(tmp_path):
    demo_index = create_local_demo_pack(tmp_path / "demo-pack")
    vault_root = tmp_path / "vault"
    record = create_vault_entry(
        kind="local-demo-pack",
        title="CLI Demo Pack Verify",
        files={
            "local-demo-pack.zip": Path(demo_index["pack_zip_path"]),
            "local-demo-pack-manifest.json": Path(demo_index["manifest_path"]),
        },
        summary={"overall_status": "PASS"},
        root=vault_root,
    )
    script = ROOT / "scripts" / "inspect_evidence_vault.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(vault_root),
            "verify-demo-pack",
            record["vault_id"],
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    data = json.loads(result.stdout)
    assert data["vault_id"] == record["vault_id"]
    assert data["filename"] == "local-demo-pack.zip"
    assert data["source_path"].endswith("local-demo-pack.zip")
    assert data["overall_status"] == "PASS"
    assert data["checked_file_count"] == 31
    assert all(item["status"] == "PASS" for item in data["files"])


def test_inspect_evidence_vault_cli_verify_demo_pack_fails_invalid_zip(tmp_path):
    source = tmp_path / "local-demo-pack.zip"
    source.write_text("not a zip", encoding="utf-8")
    vault_root = tmp_path / "vault"
    record = create_vault_entry(
        kind="local-demo-pack",
        title="Broken CLI Demo Pack",
        files={"local-demo-pack.zip": source},
        summary={"overall_status": "PASS"},
        root=vault_root,
    )
    script = ROOT / "scripts" / "inspect_evidence_vault.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(vault_root),
            "verify-demo-pack",
            record["vault_id"],
        ],
        capture_output=True,
        text=True,
    )

    data = json.loads(result.stdout)
    assert result.returncode == 1
    assert data["vault_id"] == record["vault_id"]
    assert data["filename"] == "local-demo-pack.zip"
    assert data["overall_status"] == "FAIL"
    assert "Invalid ZIP bundle" in data["error"]
