"""MCP stdio client smoke tests.

These tests start ``mcp_server.py`` as a real subprocess and communicate through
the MCP stdio transport. They complement ``test_mcp_server.py``, which calls the
tool functions directly.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from evidence.vault import create_vault_entry

ROOT = Path(__file__).resolve().parent.parent


def _json_from_tool_result(result: Any) -> dict[str, Any]:
    assert result.content
    assert result.content[0].type == "text"
    return json.loads(result.content[0].text)


async def _run_stdio_smoke() -> None:
    vault_dir_ctx = tempfile.TemporaryDirectory(prefix="abaqus-agent-stdio-memory.")
    vault_dir = Path(vault_dir_ctx.name)
    memory_report = vault_dir / "memory-doctor.md"
    memory_report.write_text("# Solver Doctor: Stdio Memory\n", encoding="utf-8")
    first_evidence = vault_dir / "stdio-first-evidence.json"
    second_evidence = vault_dir / "stdio-second-evidence.json"
    first_evidence.write_text(
        json.dumps(
            {
                "workflow": "offline-evidence-slice",
                "run_id": "stdio-first",
                "overall_status": "PASS",
                "candidate_kpis": {"U_tip": -2.0},
            }
        ),
        encoding="utf-8",
    )
    second_evidence.write_text(
        json.dumps(
            {
                "workflow": "offline-evidence-slice",
                "run_id": "stdio-second",
                "overall_status": "PASS",
                "candidate_kpis": {"U_tip": -2.2},
            }
        ),
        encoding="utf-8",
    )
    create_vault_entry(
        kind="solver-doctor",
        title="Stdio Memory",
        files={"doctor.md": memory_report},
        summary={"status": "FAILED", "primary_category": "LICENSE"},
        root=vault_dir,
    )
    first_record = create_vault_entry(
        kind="offline-evidence",
        title="Stdio First",
        files={"evidence.json": first_evidence},
        root=vault_dir,
    )
    second_record = create_vault_entry(
        kind="offline-evidence",
        title="Stdio Second",
        files={"evidence.json": second_evidence},
        root=vault_dir,
    )
    nested_first_record = create_vault_entry(
        kind="offline-evidence",
        title="Stdio Nested First",
        files={"gallery/cantilever/evidence.json": first_evidence},
        root=vault_dir,
    )
    nested_second_record = create_vault_entry(
        kind="offline-evidence",
        title="Stdio Nested Second",
        files={"gallery/plate_hole/evidence.json": second_evidence},
        root=vault_dir,
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "mcp_server.py")],
        env={**os.environ, "ABAQUS_AGENT_EVIDENCE_VAULT": str(vault_dir)},
        cwd=str(ROOT),
    )

    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            init = await session.initialize()
            server_info = getattr(init, "serverInfo", None) or getattr(init, "server_info")
            assert server_info.name == "abaqus-agent"

            tools = await session.list_tools()
            tool_names = {tool.name for tool in tools.tools}
            assert {
                "health_check",
                "validate_spec_tool",
                "generate_spec",
                "run_benchmark_tool",
                "run_offline_evidence_tool",
                "get_offline_evidence_example_tool",
                "create_local_demo_pack_tool",
                "run_local_cli_smoke_tool",
                "verify_local_demo_pack_bundle_tool",
                "verify_local_cli_smoke_bundle_tool",
                "verify_evidence_vault_smoke_bundle_tool",
                "search_evidence_vault_tool",
                "get_evidence_vault_record_tool",
                "read_evidence_vault_file_tool",
                "copy_evidence_vault_file_tool",
                "verify_evidence_vault_demo_pack_bundle_tool",
                "search_case_memory_tool",
                "diff_case_memory_tool",
                "get_kpi_recipe_tool",
                "diagnose_solver_logs_tool",
                "run_simulation_diff_tool",
                "get_solver_doctor_patterns_tool",
                "get_features",
            }.issubset(tool_names)
            # The licence gate is gone: the activation tool must not be
            # advertised at all.
            assert "activate_premium" not in tool_names

            health = _json_from_tool_result(await session.call_tool("health_check", {}))
            assert health["status"] == "ok"
            assert health["transport"] == "mcp"
            assert "cantilever" in health["cases"]

            spec_yaml = (ROOT / "cases" / "cantilever" / "spec.yaml").read_text(
                encoding="utf-8"
            )
            validation = _json_from_tool_result(
                await session.call_tool("validate_spec_tool", {"spec_yaml": spec_yaml})
            )
            assert validation == {"valid": True, "errors": []}

            feature_modules = _json_from_tool_result(
                await session.call_tool("get_features", {})
            )
            assert set(feature_modules["features"]) >= {"coupling", "parametric"}
            assert "capabilities" in feature_modules
            assert "enabled" not in json.dumps(feature_modules)

            resources = await session.list_resources()
            resource_uris = {str(resource.uri) for resource in resources.resources}
            assert {
                "benchmark://cases",
                "features://capabilities",
                "evidence://examples",
                "evidence-vault://entries",
                "case-memory://vault",
                "kpi-recipes://examples",
                "simdiff://example",
                "doctor-patterns://catalog",
            }.issubset(resource_uris)

            benchmark_resource = await session.read_resource("benchmark://cases")
            assert benchmark_resource.contents
            benchmark_cases = json.loads(benchmark_resource.contents[0].text)
            assert benchmark_cases["total"] >= 4
            expected_cases = {
                "cantilever",
                "plate_hole",
                "modal",
                "explicit_impact",
            }
            assert expected_cases.issubset(
                {case["name"] for case in benchmark_cases["cases"]}
            )

            evidence_examples_resource = await session.read_resource("evidence://examples")
            assert evidence_examples_resource.contents
            evidence_examples = json.loads(evidence_examples_resource.contents[0].text)
            evidence_example_cases = {case["case"] for case in evidence_examples["cases"]}
            assert expected_cases.issubset(evidence_example_cases)
            assert "custom_inp_deck" in evidence_example_cases

            kpi_recipes_resource = await session.read_resource("kpi-recipes://examples")
            assert kpi_recipes_resource.contents
            kpi_recipes = json.loads(kpi_recipes_resource.contents[0].text)
            assert kpi_recipes["workflow"] == "kpi-recipe-gallery"
            assert "eigenfrequency" in kpi_recipes["supported_kpi_types"]
            assert expected_cases.issubset({item["case"] for item in kpi_recipes["items"]})

            simdiff_resource = await session.read_resource("simdiff://example")
            assert simdiff_resource.contents
            simdiff_example = json.loads(simdiff_resource.contents[0].text)
            assert simdiff_example["diff_id"] == "cantilever-simdiff-example"
            assert simdiff_example["real_env_verified"] is False

            doctor_patterns_resource = await session.read_resource("doctor-patterns://catalog")
            assert doctor_patterns_resource.contents
            doctor_patterns = json.loads(doctor_patterns_resource.contents[0].text)
            assert doctor_patterns["workflow"] == "solver-doctor-pattern-gallery"
            assert doctor_patterns["total"] >= 20

            vault_resource = await session.read_resource("evidence-vault://entries")
            assert vault_resource.contents
            vault_resource_data = json.loads(vault_resource.contents[0].text)
            assert vault_resource_data["total"] >= 3
            assert any(
                item["kind"] == "offline-evidence"
                for item in vault_resource_data["items"]
            )

            vault_search = _json_from_tool_result(
                await session.call_tool(
                    "search_evidence_vault_tool",
                    {
                        "query": "Stdio First",
                        "kind": "offline-evidence",
                    },
                )
            )
            assert vault_search["total"] >= 1
            assert vault_search["items"][0]["vault_urls"]["evidence.json"].startswith(
                "evidence-vault://entries/"
            )

            vault_detail = _json_from_tool_result(
                await session.call_tool(
                    "get_evidence_vault_record_tool",
                    {"vault_id": first_record["vault_id"]},
                )
            )
            assert vault_detail["vault_id"] == first_record["vault_id"]
            assert vault_detail["files"]["evidence.json"]["size_bytes"] > 0

            vault_file = _json_from_tool_result(
                await session.call_tool(
                    "read_evidence_vault_file_tool",
                    {
                        "vault_id": first_record["vault_id"],
                        "filename": "evidence.json",
                        "max_chars": 200,
                    },
                )
            )
            assert vault_file["vault_url"].startswith("evidence-vault://entries/")
            assert vault_file["truncated"] is False
            assert '"run_id": "stdio-first"' in vault_file["content"]

            copied_vault_file = vault_dir / "stdio-copy" / "evidence.json"
            vault_copy = _json_from_tool_result(
                await session.call_tool(
                    "copy_evidence_vault_file_tool",
                    {
                        "vault_id": first_record["vault_id"],
                        "filename": "evidence.json",
                        "out_path": str(copied_vault_file),
                    },
                )
            )
            assert vault_copy["vault_id"] == first_record["vault_id"]
            assert vault_copy["output_path"] == str(copied_vault_file)
            assert copied_vault_file.exists()
            assert '"run_id": "stdio-first"' in copied_vault_file.read_text(
                encoding="utf-8"
            )

            plate_recipe = _json_from_tool_result(
                await session.call_tool(
                    "get_kpi_recipe_tool",
                    {"recipe_id": "plate-hole-max-mises"},
                )
            )
            assert plate_recipe["id"] == "plate-hole-max-mises"
            assert plate_recipe["kpi_spec"][0]["type"] == "field_max"

            case_memory_resource = await session.read_resource("case-memory://vault")
            assert case_memory_resource.contents
            case_memory_resource_data = json.loads(case_memory_resource.contents[0].text)
            assert case_memory_resource_data["workflow"] == "case-memory-vault-search"
            assert case_memory_resource_data["total"] >= 3
            assert any(
                item["kind"] == "solver-doctor"
                for item in case_memory_resource_data["items"]
            )

            case_memory = _json_from_tool_result(
                await session.call_tool(
                    "search_case_memory_tool",
                    {"query": "license", "kind": "solver-doctor"},
                )
            )
            assert case_memory["total"] == 1
            assert case_memory["items"][0]["title"] == "Stdio Memory"

            case_memory_diff = _json_from_tool_result(
                await session.call_tool(
                    "diff_case_memory_tool",
                    {
                        "baseline_vault_id": first_record["vault_id"],
                        "candidate_vault_id": second_record["vault_id"],
                        "diff_id": "stdio-case-memory-diff",
                    },
                )
            )
            assert case_memory_diff["diff_id"] == "stdio-case-memory-diff"
            assert case_memory_diff["overall_status"] == "FAIL"
            assert case_memory_diff["vault_id"].startswith("case-memory-diff-")
            assert "Case Memory Sources" in case_memory_diff["report_markdown"]

            nested_case_memory_diff = _json_from_tool_result(
                await session.call_tool(
                    "diff_case_memory_tool",
                    {
                        "baseline_vault_id": nested_first_record["vault_id"],
                        "baseline_filename": "gallery/cantilever/evidence.json",
                        "candidate_vault_id": nested_second_record["vault_id"],
                        "candidate_filename": "gallery/plate_hole/evidence.json",
                        "diff_id": "stdio-nested-case-memory-diff",
                    },
                )
            )
            assert nested_case_memory_diff["diff_id"] == "stdio-nested-case-memory-diff"
            assert nested_case_memory_diff["overall_status"] == "FAIL"
            assert nested_case_memory_diff["case_memory_diff"]["baseline_source"]["filename"] == (
                "gallery/cantilever/evidence.json"
            )
            assert nested_case_memory_diff["case_memory_diff"]["candidate_source"]["filename"] == (
                "gallery/plate_hole/evidence.json"
            )

            modal_example = _json_from_tool_result(
                await session.call_tool(
                    "get_offline_evidence_example_tool",
                    {"case_name": "modal"},
                )
            )
            assert modal_example["run_id"] == "modal-example-offline"
            assert modal_example["candidate_kpis"]["freq_2"] == 1000.0

            custom_inp_example = _json_from_tool_result(
                await session.call_tool(
                    "get_offline_evidence_example_tool",
                    {"case_name": "custom_inp_deck"},
                )
            )
            assert custom_inp_example["input_type"] == "custom_inp"
            assert custom_inp_example["input_path"].endswith(".inp")

            benchmark_run = _json_from_tool_result(
                await session.call_tool("run_benchmark_tool", {"dry_run": True})
            )
            assert benchmark_run["dry_run"] is True
            assert benchmark_run["run_id"].startswith("bench_")
            assert expected_cases.issubset(set(benchmark_run["cases"]))

            baseline = json.loads(
                (ROOT / "examples" / "kpis" / "cantilever_baseline.json").read_text(
                    encoding="utf-8"
                )
            )["kpis"]
            candidate = json.loads(
                (ROOT / "examples" / "kpis" / "cantilever_candidate.json").read_text(
                    encoding="utf-8"
                )
            )["kpis"]
            contracts = yaml.safe_load(
                (ROOT / "examples" / "contracts" / "cantilever.yaml").read_text(
                    encoding="utf-8"
                )
            )["contracts"]
            offline_evidence = _json_from_tool_result(
                await session.call_tool(
                    "run_offline_evidence_tool",
                    {
                        "baseline_kpis": baseline,
                        "candidate_kpis": candidate,
                        "contracts": contracts,
                        "run_id": "stdio-offline-cantilever",
                        "input_path": str(ROOT / "cases" / "cantilever" / "spec.yaml"),
                        "input_metadata": json.dumps({"case": "cantilever"}),
                    },
                )
            )
            assert offline_evidence["overall_status"] == "PASS"
            assert offline_evidence["contracts"]["status"] == "PASS"
            assert offline_evidence["diff"]["status"] == "PASS"
            assert "Verdict Summary" in offline_evidence["report_markdown"]
            assert Path(offline_evidence["capsule"]["manifest_path"]).exists()

            simulation_diff = _json_from_tool_result(
                await session.call_tool(
                    "run_simulation_diff_tool",
                    {
                        "baseline_kpis": {"U_tip": -2.0, "max_mises": 100.0},
                        "candidate_kpis": {"U_tip": -2.4, "max_mises": 100.0},
                        "tolerances": {"U_tip": {"rtol": 0.05}},
                        "diff_id": "stdio-simdiff-cantilever",
                        "input_metadata": json.dumps({"case": "cantilever"}),
                    },
                )
            )
            assert simulation_diff["overall_status"] == "FAIL"
            assert simulation_diff["diff"]["changed_count"] == 1
            assert simulation_diff["real_env_verified"] is False
            assert "Simulation Diff Report" in simulation_diff["report_markdown"]
            assert Path(simulation_diff["diff_path"]).exists()

            with tempfile.TemporaryDirectory(prefix="abaqus-agent-stdio-demo-pack.") as temp_dir:
                demo_pack = _json_from_tool_result(
                    await session.call_tool(
                        "create_local_demo_pack_tool",
                        {"out_dir": temp_dir},
                    )
                )
                assert demo_pack["overall_status"] == "PASS"
                assert demo_pack["real_env_verified"] is False
                assert demo_pack["index"]["workflow"] == "local-demo-pack"
                assert demo_pack["index"]["manifest_path"].endswith(
                    "local-demo-pack-manifest.json"
                )
                assert demo_pack["index"]["offline_demo_gallery"]["case_count"] == 4
                assert demo_pack["index"]["solver_doctor"]["status"] == "FAILED"
                assert demo_pack["index"]["simulation_diff"]["status"] == "FAIL"
                assert "Abaqus Agent Local Demo Pack" in demo_pack["index_markdown"]
                assert "Simulation Diff Sample" in demo_pack["index_markdown"]
                assert "Offline Simulation QA evidence bundle" in demo_pack["index_html"]
                assert "offline-demo-gallery/index.html" in demo_pack["index_html"]
                assert "simulation-diff/diff.md" in demo_pack["index_html"]
                assert Path(demo_pack["index_path"]).exists()
                assert Path(demo_pack["index_markdown_path"]).exists()
                assert Path(demo_pack["index_html_path"]).exists()
                assert Path(demo_pack["pack_zip_path"]).exists()
                with zipfile.ZipFile(demo_pack["pack_zip_path"]) as pack:
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
                        "offline-demo-gallery/cantilever/evidence.json",
                        "offline-demo-gallery/cantilever/evidence.md",
                        "offline-demo-gallery/cantilever/evidence.html",
                        "offline-demo-gallery/cantilever/capsule.json",
                        "offline-demo-gallery/cantilever/cantilever-demo-bundle.zip",
                        "solver-doctor/doctor.json",
                        "solver-doctor/doctor.md",
                        "simulation-diff/diff.json",
                        "simulation-diff/diff.md",
                    }.issubset(names)
                    manifest = json.loads(pack.read("local-demo-pack-manifest.json"))
                    assert manifest["workflow"] == "local-demo-pack"
                    manifest_files = {entry["filename"]: entry for entry in manifest["files"]}
                    assert "local-demo-pack-manifest.json" not in manifest_files
                    assert manifest_files["index.json"]["size_bytes"] == len(
                        pack.read("index.json")
                    )
                    assert manifest_files["index.json"]["sha256"] == hashlib.sha256(
                        pack.read("index.json")
                    ).hexdigest()
                    assert len(manifest_files["simulation-diff/diff.json"]["sha256"]) == 64
                    assert len(
                        [
                            name
                            for name in names
                            if name.startswith("offline-demo-gallery/")
                            and name.endswith("/evidence.html")
                        ]
                    ) == 4

                demo_verify = _json_from_tool_result(
                    await session.call_tool(
                        "verify_local_demo_pack_bundle_tool",
                        {"zip_path": demo_pack["pack_zip_path"]},
                    )
                )
                assert demo_verify["workflow"] == "local-demo-pack-bundle-verify"
                assert demo_verify["bundle_workflow"] == "local-demo-pack"
                assert demo_verify["overall_status"] == "PASS"
                assert demo_verify["checked_file_count"] == 31
                assert all(item["status"] == "PASS" for item in demo_verify["files"])

                demo_vault_record = create_vault_entry(
                    kind="local-demo-pack",
                    title="Stdio Demo Pack Verify",
                    files={
                        "local-demo-pack.zip": Path(demo_pack["pack_zip_path"]),
                        "local-demo-pack-manifest.json": Path(
                            demo_pack["index"]["manifest_path"]
                        ),
                    },
                    summary={"overall_status": "PASS"},
                    root=vault_dir,
                )
                demo_vault_verify = _json_from_tool_result(
                    await session.call_tool(
                        "verify_evidence_vault_demo_pack_bundle_tool",
                        {
                            "vault_id": demo_vault_record["vault_id"],
                            "vault_root": str(vault_dir),
                        },
                    )
                )
                assert demo_vault_verify["vault_id"] == demo_vault_record["vault_id"]
                assert demo_vault_verify["filename"] == "local-demo-pack.zip"
                assert demo_vault_verify["vault_root"] == str(vault_dir)
                assert demo_vault_verify["overall_status"] == "PASS"
                assert demo_vault_verify["checked_file_count"] == 31

            with tempfile.TemporaryDirectory(prefix="abaqus-agent-stdio-cli-smoke.") as temp_dir:
                cli_smoke = _json_from_tool_result(
                    await session.call_tool(
                        "run_local_cli_smoke_tool",
                        {"out_dir": temp_dir},
                    )
                )
                assert cli_smoke["workflow"] == "local-cli-smoke"
                assert cli_smoke["overall_status"] == "PASS"
                assert cli_smoke["real_env_verified"] is False
                assert cli_smoke["step_count"] == 11
                assert all(step["status"] == "PASS" for step in cli_smoke["steps"])
                assert cli_smoke["smoke_vault_id"].startswith("local-cli-smoke-")
                assert Path(cli_smoke["json_path"]).exists()
                assert Path(cli_smoke["html_path"]).exists()
                assert Path(cli_smoke["zip_path"]).exists()
                assert "local_cli_smoke.zip" in cli_smoke["smoke_vault_files"]
                with zipfile.ZipFile(cli_smoke["zip_path"]) as bundle:
                    assert set(bundle.namelist()) == {
                        "copied-local-demo-pack.zip",
                        "local_cli_smoke.html",
                        "local_cli_smoke.json",
                        "local_cli_smoke_manifest.json",
                        "local_cli_smoke.md",
                    }
                assert "Abaqus Agent Local CLI Smoke" in cli_smoke["report_markdown"]
                assert "Smoke Steps" in cli_smoke["report_html"]

                verified_smoke = _json_from_tool_result(
                    await session.call_tool(
                        "verify_local_cli_smoke_bundle_tool",
                        {"zip_path": cli_smoke["zip_path"]},
                    )
                )
                assert verified_smoke["workflow"] == "local-cli-smoke-bundle-verify"
                assert verified_smoke["overall_status"] == "PASS"
                assert verified_smoke["checked_file_count"] == 4
                assert all(item["status"] == "PASS" for item in verified_smoke["files"])
                nested_verified_smoke = verified_smoke["copied_demo_pack_verification"]
                assert nested_verified_smoke["overall_status"] == "PASS"
                assert nested_verified_smoke["checked_file_count"] == 31

                verified_vault_smoke = _json_from_tool_result(
                    await session.call_tool(
                        "verify_evidence_vault_smoke_bundle_tool",
                        {
                            "vault_id": cli_smoke["smoke_vault_id"],
                            "vault_root": cli_smoke["vault_root"],
                        },
                    )
                )
                assert verified_vault_smoke["vault_id"] == cli_smoke["smoke_vault_id"]
                assert verified_vault_smoke["filename"] == "local_cli_smoke.zip"
                assert verified_vault_smoke["overall_status"] == "PASS"
                assert verified_vault_smoke["checked_file_count"] == 4
                nested_verified_vault_smoke = verified_vault_smoke[
                    "copied_demo_pack_verification"
                ]
                assert nested_verified_vault_smoke["overall_status"] == "PASS"
                assert nested_verified_vault_smoke["checked_file_count"] == 31

            doctor = _json_from_tool_result(
                await session.call_tool(
                    "diagnose_solver_logs_tool",
                    {
                        "job_name": "Stdio-Doctor",
                        "msg_text": "***ERROR: Abaqus Error: License checkout failed\n",
                        "log_text": "Abaqus JOB Stdio-Doctor\n",
                    },
                )
            )
            assert doctor["status"] == "FAILED"
            assert doctor["primary_category"] == "LICENSE"
            assert doctor["real_env_verified"] is False
            assert "Solver Doctor: Stdio-Doctor" in doctor["report_markdown"]

            doctor_pattern_tool = _json_from_tool_result(
                await session.call_tool(
                    "get_solver_doctor_patterns_tool",
                    {"category": "license", "severity": "error"},
                )
            )
            assert doctor_pattern_tool["total"] >= 1
            assert {pattern["category"] for pattern in doctor_pattern_tool["patterns"]} == {"LICENSE"}
            assert {pattern["severity"] for pattern in doctor_pattern_tool["patterns"]} == {"ERROR"}

            features_resource = await session.read_resource("features://capabilities")
            assert features_resource.contents
            features_resource_data = json.loads(features_resource.contents[0].text)
            assert set(features_resource_data["features"]) == set(
                feature_modules["features"]
            )
    vault_dir_ctx.cleanup()


def test_mcp_stdio_client_smoke() -> None:
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_run_stdio_smoke())
    finally:
        loop.close()
        # Legacy tests in this repository still use asyncio.get_event_loop().
        # Keep a fresh default loop available after this smoke test completes.
        asyncio.set_event_loop(asyncio.new_event_loop())
