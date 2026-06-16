#!/usr/bin/env python3
"""Install the AbaqusAgent Copilot plug-in file into a user-chosen directory."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SOURCE = ROOT / "plugins" / "abaqus_agent" / "abaqusAgent_plugin.py"
CONFIG_FILENAME = "abaqus_agent_config.json"


def install_copilot_plugin(
    plugin_dir: str | Path,
    *,
    server_url: str = "http://127.0.0.1:8000",
    session_id: str = "",
    write_session_file: bool = False,
) -> dict[str, Any]:
    destination_dir = Path(plugin_dir).expanduser()
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_file = destination_dir / PLUGIN_SOURCE.name
    config_file = destination_dir / CONFIG_FILENAME
    shutil.copy2(PLUGIN_SOURCE, destination_file)
    config = {
        "server_url": server_url.rstrip("/"),
        "session_id": session_id,
    }
    config_file.write_text(
        json.dumps(config, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )

    result: dict[str, Any] = {
        "status": "installed",
        "plugin_source": str(PLUGIN_SOURCE),
        "plugin_path": str(destination_file),
        "config_path": str(config_file),
        "server_url": server_url,
        "session_id": session_id,
        "session_file": "",
        "next_steps": [
            "Start the AbaqusAgent FastAPI server.",
            "Restart Abaqus/CAE if it is already open.",
            "Use Plug-ins -> AbaqusAgent Copilot: Open Sidecar.",
            "Generate a plan in the sidecar; it will activate the session file automatically.",
            "Use Plug-ins -> AbaqusAgent Copilot: Run Current Plan.",
        ],
    }

    if write_session_file:
        session_file = Path.home() / ".abaqus_agent_session"
        session_file.write_text(session_id, encoding="utf-8")
        result["session_file"] = str(session_file)

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plugin-dir",
        required=True,
        help="Target Abaqus plug-ins directory. The directory is created if missing.",
    )
    parser.add_argument("--server-url", default="http://127.0.0.1:8000")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--write-session-file", action="store_true")
    args = parser.parse_args(argv)

    result = install_copilot_plugin(
        args.plugin_dir,
        server_url=args.server_url,
        session_id=args.session_id,
        write_session_file=args.write_session_file,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
