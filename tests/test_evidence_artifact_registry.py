"""The registry that keeps generated evidence artifacts reachable.

One module now, mounted twice: `server.py` under /api/evidence and
`mcp_bridge.py` under /mcp/api/evidence. Both used to carry their own copy.

The tests here pin the three things that copy-then-share can quietly break:
the two mounts stay independent, the URLs each one hands out carry its own
prefix, and a reset actually resets. That last one is the reason this file
exists -- the artifact counter used to be a module-level int, so the fixtures
zeroed it with `server.EVIDENCE_ARTIFACT_SEQUENCE = 0`. Moving it into the
registry turned that line into a no-op that binds a name nothing reads: no
test went red, the counter just climbed across the whole session and every
`sequence` the API reported was an arbitrary number instead of 1, 2, 3.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evidence.artifact_registry import (  # noqa: E402
    ArtifactNotFound,
    EvidenceArtifactRegistry,
)

EVIDENCE = {
    "overall_status": "PASS",
    "real_env_verified": False,
    "contracts": {"status": "PASS", "total": 2, "failed_count": 0, "warning_count": 0},
    "diff": {"status": "PASS", "total": 2, "changed_count": 0, "added_count": 0,
             "removed_count": 0},
    "capsule": {"run_id": "r", "capsule_hash": "abc", "input_count": 1,
                "artifact_count": 3},
}


def _files(tmp_path: Path) -> dict[str, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    made = {}
    for name in ("evidence.json", "evidence.md", "evidence.html", "capsule.json"):
        path = tmp_path / name
        path.write_text(json.dumps(EVIDENCE) if name.endswith(".json") else name,
                        encoding="utf-8")
        made[name] = path
    return made


def _register(registry: EvidenceArtifactRegistry, tmp_path: Path, run_id="r"):
    f = _files(tmp_path)
    return registry.register_evidence(
        run_id=run_id, evidence=EVIDENCE,
        evidence_path=f["evidence.json"], report_path=f["evidence.md"],
        html_path=f["evidence.html"], capsule_manifest_path=f["capsule.json"])


def test_clear_resets_the_counter_not_just_the_dicts(tmp_path):
    """The regression that prompted this file. A fixture that clears between
    cases must give the next case sequence 1, or `sequence` in the API
    response means nothing."""
    registry = EvidenceArtifactRegistry("/api/evidence")

    _register(registry, tmp_path / "a")
    _register(registry, tmp_path / "b")
    assert registry.list_evidence_records()["items"][0]["sequence"] == 2

    registry.clear()
    _register(registry, tmp_path / "c")

    records = registry.list_evidence_records()
    assert records["total"] == 1
    assert records["items"][0]["sequence"] == 1


def test_two_mounts_do_not_share_artifacts(tmp_path):
    """server.py and mcp_bridge.py each keep their own. An artifact generated
    through the bridge must not be fetchable from the server's registry."""
    server_side = EvidenceArtifactRegistry("/api/evidence")
    bridge_side = EvidenceArtifactRegistry("/mcp/api/evidence")

    made = _register(bridge_side, tmp_path)

    assert bridge_side.evidence_path(made["artifact_id"], "evidence.json").exists()
    try:
        server_side.evidence_path(made["artifact_id"], "evidence.json")
    except ArtifactNotFound:
        pass
    else:
        raise AssertionError("the two mounts share state")


def test_every_url_carries_its_own_mount_prefix(tmp_path):
    bridge = EvidenceArtifactRegistry("/mcp/api/evidence")

    urls = _register(bridge, tmp_path)["artifact_urls"]

    assert set(urls) == {"evidence_json", "report_markdown", "report_html",
                         "capsule_manifest", "bundle_zip"}
    assert all(u.startswith("/mcp/api/evidence/artifacts/") for u in urls.values())


def test_a_trailing_slash_on_the_mount_does_not_double_up(tmp_path):
    registry = EvidenceArtifactRegistry("/api/evidence/")

    urls = _register(registry, tmp_path)["artifact_urls"]

    assert not any("//" in u for u in urls.values())


def test_a_missing_id_and_a_deleted_file_read_differently(tmp_path):
    """Two 404s with different causes. "not found" means no such artifact;
    "file missing" means the temp directory it lived in is gone -- which is
    what actually happens when the OS cleans up between runs."""
    registry = EvidenceArtifactRegistry("/api/evidence")
    made = _register(registry, tmp_path)

    try:
        registry.evidence_path("no-such-id", "evidence.json")
    except ArtifactNotFound as exc:
        assert "not found" in str(exc)

    (tmp_path / "evidence.json").unlink()
    try:
        registry.evidence_path(made["artifact_id"], "evidence.json")
    except ArtifactNotFound as exc:
        assert "file missing" in str(exc)
    else:
        raise AssertionError("a deleted artifact file was reported as present")


def test_the_bundle_zip_holds_the_four_files_and_a_manifest(tmp_path):
    registry = EvidenceArtifactRegistry("/api/evidence")
    made = _register(registry, tmp_path)

    import zipfile
    with zipfile.ZipFile(registry.evidence_path(made["artifact_id"], "bundle.zip")) as z:
        names = sorted(z.namelist())
        manifest = json.loads(z.read("bundle_manifest.json"))

    assert names == ["bundle_manifest.json", "capsule.json", "evidence.html",
                     "evidence.json", "evidence.md"]
    assert manifest["artifact_id"] == made["artifact_id"]


def test_the_record_listing_is_newest_first_and_capped(tmp_path):
    registry = EvidenceArtifactRegistry("/api/evidence")
    for i in range(5):
        _register(registry, tmp_path / str(i), run_id="run-%d" % i)

    top = registry.list_evidence_records(limit=2)

    assert top["total"] == 5 and len(top["items"]) == 2
    assert [item["sequence"] for item in top["items"]] == [5, 4]


def test_the_two_dicts_the_servers_alias_are_the_registry_s_own():
    """server.py binds EVIDENCE_ARTIFACTS to registry.artifacts. If that ever
    becomes a copy, the fixtures clear a dict the routes do not read."""
    import mcp_bridge
    import server

    assert server.EVIDENCE_ARTIFACTS is server.EVIDENCE.artifacts
    assert server.DEMO_GALLERY_ARTIFACTS is server.EVIDENCE.demo_galleries
    assert mcp_bridge.EVIDENCE_ARTIFACTS is mcp_bridge.EVIDENCE.artifacts
    assert server.EVIDENCE.artifacts is not mcp_bridge.EVIDENCE.artifacts
    assert (server.EVIDENCE.url_root, mcp_bridge.EVIDENCE.url_root) == (
        "/api/evidence", "/mcp/api/evidence")
