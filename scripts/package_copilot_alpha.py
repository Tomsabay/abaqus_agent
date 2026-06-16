#!/usr/bin/env python3
"""Build a downloadable Abaqus/CAE Copilot Alpha package."""

from __future__ import annotations

import argparse
import json
import time
import zipfile
from pathlib import Path
from typing import Any

from scripts.verify_copilot_alpha_release import collect_release_gate, write_release_gate

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = Path("artifacts/copilot/alpha_package")
PACKAGE_NAME = "abaqus-agent-copilot-alpha.zip"

PACKAGE_FILES = [
    ("plugins/abaqus_agent/abaqusAgent_plugin.py", "plugin/abaqusAgent_plugin.py"),
    ("plugins/abaqus_agent/README.md", "plugin/README.md"),
    ("docs/COPILOT_MVP.md", "docs/COPILOT_MVP.md"),
    ("artifacts/copilot/release_gate/copilot_alpha_release_gate.json", "evidence/copilot_alpha_release_gate.json"),
    ("artifacts/copilot/release_gate/copilot_alpha_release_gate.md", "evidence/copilot_alpha_release_gate.md"),
    (
        "artifacts/copilot/real_smoke_cli_codex/Cantilever_200mm_Static_copilot_result.json",
        "evidence/real_smoke/Cantilever_200mm_Static_copilot_result.json",
    ),
    (
        "artifacts/copilot/plugin_run_plan_codex/copilot_plugin_run_plan_trace.json",
        "evidence/plugin_run_plan/copilot_plugin_run_plan_trace.json",
    ),
    (
        "artifacts/copilot/plugin_run_plan_codex/Cantilever_200mm_Static_copilot_result.json",
        "evidence/plugin_run_plan/Cantilever_200mm_Static_copilot_result.json",
    ),
    (
        "artifacts/copilot/plugin_manifest/abaqus_agent_plugin_manifest.json",
        "evidence/plugin_manifest/abaqus_agent_plugin_manifest.json",
    ),
]


def build_copilot_alpha_package(
    *,
    root: Path = ROOT,
    out_dir: Path = DEFAULT_OUT_DIR,
    server_url: str = "http://127.0.0.1:8000",
) -> dict[str, Any]:
    out_path = root / out_dir if not out_dir.is_absolute() else out_dir
    out_path.mkdir(parents=True, exist_ok=True)
    release_gate = collect_release_gate(root=root)
    gate_files = write_release_gate(release_gate, root / "artifacts/copilot/release_gate")
    package_path = out_path / PACKAGE_NAME
    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    config_server_url = server_url.rstrip("/") or "http://127.0.0.1:8000"
    included_files = []
    missing_files = []
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for source, archive_name in PACKAGE_FILES:
            source_path = root / source
            if not source_path.exists():
                missing_files.append(source)
                continue
            bundle.write(source_path, archive_name)
            included_files.append(archive_name)
        manifest = {
            "schema_version": "1.0",
            "package": "abaqus-agent-copilot-alpha",
            "generated_at": generated_at,
            "overall_status": release_gate["overall_status"],
            "strict_gui_ready": release_gate["overall_status"] == "RELEASE_READY",
            "default_server_url": config_server_url,
            "release_gate_files": gate_files,
            "included_files": included_files,
            "missing_files": missing_files,
            "install_steps": [
                "Start the local AbaqusAgent server.",
                "Copy plugin/abaqusAgent_plugin.py into the Abaqus/CAE plug-ins directory.",
                "Copy plugin/abaqus_agent_config.example.json to abaqus_agent_config.json in the same directory and set server_url if needed.",
                "Restart Abaqus/CAE.",
                "Open Plug-ins -> AbaqusAgent Copilot: Open Sidecar.",
                "Generate a plan and run Plug-ins -> AbaqusAgent Copilot: Run Current Plan.",
            ],
        }
        included_files.append("plugin/abaqus_agent_config.example.json")
        manifest["included_files"] = included_files
        bundle.writestr(
            "plugin/abaqus_agent_config.example.json",
            json.dumps(
                {
                    "server_url": config_server_url,
                    "session_id": "",
                },
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        bundle.writestr(
            "PACKAGE_MANIFEST.json",
            json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True),
        )
        bundle.writestr("README.md", _render_package_readme(manifest))
    return {
        "status": "packaged",
        "package_path": str(package_path),
        "package_name": PACKAGE_NAME,
        "overall_status": release_gate["overall_status"],
        "included_files": included_files,
        "missing_files": missing_files,
        "manifest": manifest,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--server-url", default="http://127.0.0.1:8000")
    args = parser.parse_args(argv)

    result = build_copilot_alpha_package(out_dir=Path(args.out_dir), server_url=args.server_url)
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


def _render_package_readme(manifest: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# AbaqusAgent Copilot Alpha Package",
            "",
            f"- Overall status: `{manifest['overall_status']}`",
            f"- Generated at: `{manifest['generated_at']}`",
            "",
            "## Install",
            "",
            "1. Start the AbaqusAgent server on the machine that runs the sidecar.",
            "2. Copy `plugin/abaqusAgent_plugin.py` into the Abaqus/CAE plug-ins directory.",
            "3. Copy `plugin/abaqus_agent_config.example.json` to `abaqus_agent_config.json` in the same directory and set `server_url` if Abaqus runs on another machine.",
            "4. Restart Abaqus/CAE.",
            "5. Use `Plug-ins -> AbaqusAgent Copilot: Open Sidecar`.",
            "6. Generate a plan, then use `Plug-ins -> AbaqusAgent Copilot: Run Current Plan`.",
            "",
            "## Evidence",
            "",
            "- `evidence/copilot_alpha_release_gate.md` summarizes the current gate.",
            "- `evidence/real_smoke/` contains real Abaqus noGUI result evidence.",
            "- `evidence/plugin_run_plan/` contains plug-in one-shot run evidence.",
            "- `evidence/plugin_manifest/` contains CAE plug-in menu manifest evidence.",
            "",
            "## Current Limitation",
            "",
            "Interactive Abaqus/CAE GUI screenshot or recording is still required for strict release.",
            "",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
