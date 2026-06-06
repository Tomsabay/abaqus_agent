import hashlib
import json
import zipfile
from pathlib import Path

from evidence.examples import get_example
from evidence.offline import collect_evidence_from_values
from scripts import run_local_demo_pack as demo_pack
from scripts import run_offline_demo_gallery as gallery
from scripts import run_offline_evidence_slice as offline


def test_collect_evidence_writes_report_json_and_capsule(tmp_path):
    root = Path(__file__).resolve().parents[1]
    out_dir = tmp_path / "evidence"

    evidence = offline.collect_evidence(
        baseline_kpis_path=root / "examples" / "kpis" / "cantilever_baseline.json",
        candidate_kpis_path=root / "examples" / "kpis" / "cantilever_candidate.json",
        contracts_path=root / "examples" / "contracts" / "cantilever.yaml",
        out_dir=out_dir,
        run_id="cantilever-offline",
        extra_inputs=[root / "cases" / "cantilever" / "spec.yaml"],
    )

    assert evidence["overall_status"] == "PASS"
    assert evidence["contracts"]["status"] == "PASS"
    assert evidence["diff"]["status"] == "PASS"
    assert evidence["real_env_verified"] is False
    assert (out_dir / "evidence.json").exists()
    assert (out_dir / "evidence.md").exists()
    report = (out_dir / "evidence.md").read_text(encoding="utf-8")
    assert "Offline Evidence Slice Report" in report
    assert "## Verdict Summary" in report
    assert "| Overall | `PASS` |" in report
    assert "## Run Metadata" in report
    assert "## Capsule Provenance" in report
    assert "| Real Abaqus execution | `not verified` |" in report
    assert "does not invoke Abaqus" in report

    manifest_path = Path(evidence["capsule"]["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["metadata"]["metadata_schema_version"] == "1.0"
    assert manifest["metadata"]["project"] == "abaqus-agent"
    assert manifest["metadata"]["workflow"] == "offline-evidence-slice"
    assert manifest["metadata"]["evidence_source"] == "supplied-kpi-json"
    assert manifest["metadata"]["evidence_level"] == "offline"
    assert manifest["metadata"]["overall_status"] == "PASS"
    assert manifest["metadata"]["real_env_required"] is False
    assert manifest["metadata"]["real_env_verified"] is False
    assert {entry["name"] for entry in manifest["inputs"]} >= {
        "cantilever_baseline.json",
        "cantilever_candidate.json",
        "cantilever.yaml",
        "spec.yaml",
    }
    assert {entry["name"] for entry in manifest["artifacts"]} == {
        "evidence.json",
        "evidence.html",
        "evidence.md",
    }
    assert (out_dir / "evidence.html").exists()
    html = (out_dir / "evidence.html").read_text(encoding="utf-8")
    assert "Abaqus Agent Offline Evidence Slice Report" in html
    assert "does not invoke Abaqus" in html


def test_run_cli_returns_nonzero_for_failed_contracts(tmp_path):
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    contracts = tmp_path / "contracts.yaml"
    baseline.write_text('{"U_tip": -0.002}', encoding="utf-8")
    candidate.write_text('{"U_tip": 0.002}', encoding="utf-8")
    contracts.write_text(
        "contracts:\n"
        "  - name: tip down\n"
        "    type: direction\n"
        "    kpi: U_tip\n"
        "    op: '<'\n"
        "    value: 0\n",
        encoding="utf-8",
    )

    code = offline.run(
        [
            "--baseline-kpis",
            str(baseline),
            "--candidate-kpis",
            str(candidate),
            "--contracts",
            str(contracts),
            "--out-dir",
            str(tmp_path / "out"),
            "--run-id",
            "failed-case",
        ]
    )

    assert code == 1
    evidence = json.loads((tmp_path / "out" / "evidence.json").read_text(encoding="utf-8"))
    assert evidence["overall_status"] == "FAIL"
    assert evidence["contracts"]["failed_count"] == 1
    report = (tmp_path / "out" / "evidence.md").read_text(encoding="utf-8")
    assert "| Overall | `FAIL` |" in report
    assert "| Physics Contracts | `FAIL` | 0 pass / 0 warning / 1 fail. |" in report


def test_offline_demo_gallery_writes_index_and_case_bundles(tmp_path):
    code = gallery.run(["--out-dir", str(tmp_path), "--json"])

    assert code == 0
    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert index["overall_status"] == "PASS"
    assert index["case_count"] == 4
    assert {case["case"] for case in index["cases"]} == {
        "cantilever",
        "explicit_impact",
        "modal",
        "plate_hole",
    }
    report = (tmp_path / "index.md").read_text(encoding="utf-8")
    assert "Offline Demo Gallery" in report
    assert "Real Abaqus execution: `not verified`" in report
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "Abaqus Agent Offline Demo Gallery" in html
    assert "plate_hole/evidence.html" in html
    assert "does not invoke Abaqus" in html
    assert Path(index["index_html_path"]).exists()
    assert Path(index["gallery_zip_path"]).exists()

    plate = next(case for case in index["cases"] if case["case"] == "plate_hole")
    assert plate["overall_status"] == "PASS"
    assert Path(plate["report_path"]).exists()
    assert Path(plate["html_path"]).exists()
    with zipfile.ZipFile(plate["bundle_path"]) as bundle:
        assert set(bundle.namelist()) == {
            "bundle_manifest.json",
            "capsule.json",
            "evidence.json",
            "evidence.html",
            "evidence.md",
        }
        manifest = json.loads(bundle.read("bundle_manifest.json"))
        assert manifest["case"] == "plate_hole"
        assert manifest["overall_status"] == "PASS"
        assert b"Offline Evidence Slice Report" in bundle.read("evidence.html")

    with zipfile.ZipFile(index["gallery_zip_path"]) as gallery_bundle:
        assert {
            "gallery_manifest.json",
            "index.html",
            "index.json",
            "index.md",
            "plate_hole/evidence.json",
            "plate_hole/evidence.html",
            "plate_hole/evidence.md",
            "plate_hole/capsule.json",
            "plate_hole/plate_hole-demo-bundle.zip",
            "cases/plate_hole/evidence.json",
            "cases/plate_hole/evidence.html",
            "cases/plate_hole/evidence.md",
            "cases/plate_hole/capsule.json",
            "cases/plate_hole/plate_hole-demo-bundle.zip",
        }.issubset(set(gallery_bundle.namelist()))
        gallery_manifest = json.loads(gallery_bundle.read("gallery_manifest.json"))
        assert gallery_manifest["workflow"] == "offline-demo-gallery"
        assert gallery_manifest["case_count"] == 4
        assert b"Abaqus Agent Offline Demo Gallery" in gallery_bundle.read("index.html")
        assert b"Offline Evidence Slice Report" in gallery_bundle.read(
            "plate_hole/evidence.html"
        )


def test_custom_inp_deck_example_copies_input_deck_into_capsule(tmp_path):
    root = Path(__file__).resolve().parents[1]
    example = get_example("custom_inp_deck")

    assert example["input_type"] == "custom_inp"
    assert example["input_path"].endswith(".inp")

    evidence = collect_evidence_from_values(
        baseline_kpis=example["baseline_kpis"],
        candidate_kpis=example["candidate_kpis"],
        contracts=example["contracts"],
        out_dir=tmp_path / "custom-inp-evidence",
        run_id=example["run_id"],
        input_paths=[root / example["input_path"]],
        input_metadata={"case": example["case"], "input_type": example["input_type"]},
    )

    assert evidence["overall_status"] == "PASS"
    assert evidence["real_env_verified"] is False
    assert evidence["inputs"]["metadata"]["input_type"] == "custom_inp"
    manifest = json.loads(Path(evidence["capsule"]["manifest_path"]).read_text(encoding="utf-8"))
    input_names = {entry["name"] for entry in manifest["inputs"]}
    assert "custom_cantilever.inp" in input_names
    assert "input_metadata.json" in input_names


def test_local_demo_pack_writes_combined_index_and_zip(tmp_path):
    code = demo_pack.run(["--out-dir", str(tmp_path), "--json"])

    assert code == 0
    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert index["workflow"] == "local-demo-pack"
    assert index["overall_status"] == "PASS"
    assert index["real_env_verified"] is False
    assert index["offline_demo_gallery"]["case_count"] == 4
    assert index["solver_doctor"]["status"] == "FAILED"
    assert index["solver_doctor"]["finding_count"] >= 2
    assert index["simulation_diff"]["status"] == "FAIL"
    assert index["simulation_diff"]["changed_count"] == 1
    assert index["simulation_diff"]["added_count"] == 1
    assert Path(index["offline_demo_gallery"]["zip_path"]).exists()
    assert Path(index["offline_demo_gallery"]["html_path"]).exists()
    assert Path(index["solver_doctor"]["markdown_path"]).exists()
    assert Path(index["simulation_diff"]["markdown_path"]).exists()
    assert Path(index["manifest_path"]).exists()
    report = (tmp_path / "index.md").read_text(encoding="utf-8")
    assert "Abaqus Agent Local Demo Pack" in report
    assert "Simulation Diff Sample" in report
    assert "does not invoke Abaqus" in report
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "Offline Simulation QA evidence bundle" in html
    assert "offline-demo-gallery/index.html" in html
    assert "offline-demo-gallery/index.md" in html
    assert "solver-doctor/doctor.md" in html
    assert "simulation-diff/diff.md" in html

    with zipfile.ZipFile(index["pack_zip_path"]) as pack:
        names = set(pack.namelist())
        assert {
            "index.json",
            "index.md",
            "index.html",
            "local-demo-pack-manifest.json",
            "offline-demo-gallery/index.json",
            "offline-demo-gallery/index.md",
            "offline-demo-gallery/index.html",
            "offline-demo-gallery/offline-demo-gallery.zip",
            "offline-demo-gallery/plate_hole/evidence.json",
            "offline-demo-gallery/plate_hole/evidence.md",
            "offline-demo-gallery/plate_hole/evidence.html",
            "offline-demo-gallery/plate_hole/capsule.json",
            "offline-demo-gallery/plate_hole/plate_hole-demo-bundle.zip",
            "solver-doctor/doctor.json",
            "solver-doctor/doctor.md",
            "simulation-diff/diff.json",
            "simulation-diff/diff.md",
        }.issubset(names)
        manifest = json.loads(pack.read("local-demo-pack-manifest.json"))
        assert manifest["workflow"] == "local-demo-pack"
        assert manifest["real_env_verified"] is False
        manifest_files = {entry["filename"]: entry for entry in manifest["files"]}
        assert "local-demo-pack-manifest.json" not in manifest_files
        assert "index.json" in manifest_files
        assert manifest_files["index.json"]["size_bytes"] == len(pack.read("index.json"))
        assert manifest_files["index.json"]["sha256"] == hashlib.sha256(
            pack.read("index.json")
        ).hexdigest()
        assert len(manifest_files["simulation-diff/diff.md"]["sha256"]) == 64
        assert len(
            [
                name
                for name in names
                if name.startswith("offline-demo-gallery/")
                and name.endswith("/evidence.html")
            ]
        ) == 4
        assert b"Solver Doctor" in pack.read("solver-doctor/doctor.md")
        assert b"Simulation Diff Report" in pack.read("simulation-diff/diff.md")
        assert b"Abaqus Agent Local Demo Pack" in pack.read("index.html")
        assert b"Abaqus Agent Offline Demo Gallery" in pack.read(
            "offline-demo-gallery/index.html"
        )
