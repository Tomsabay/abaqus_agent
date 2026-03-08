"""
upgrade_odb.py
--------------
ODB version detection and upgrade utilities.
Wraps odbAccess.isUpgradeRequiredForOdb / upgradeOdb.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def upgrade_odb_if_needed(
    odb_path: str | Path,
    upgraded_path: str | Path | None = None,
) -> dict:
    """
    Check if ODB upgrade is required and perform it if so.

    Runs via 'abaqus python' subprocess to access odbAccess.

    Returns
    -------
    dict:
        upgrade_required : bool
        upgraded         : bool
        original_path    : str
        output_path      : str   - upgraded path (or original if no upgrade)
        error            : str | None
    """
    odb_path = Path(odb_path).resolve()
    if upgraded_path is None:
        upgraded_path = odb_path.parent / (odb_path.stem + "_upgraded.odb")
    else:
        upgraded_path = Path(upgraded_path).resolve()

    inner_script = Path(__file__).parent / "_upgrade_inner.py"
    _write_inner_script(inner_script)

    result_file = odb_path.parent / "_upgrade_result.json"
    from tools.abaqus_cmd import get_abaqus_cmd
    cmd = [
        get_abaqus_cmd(), "python", str(inner_script),
        "--",
        str(odb_path), str(upgraded_path), str(result_file),
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except FileNotFoundError:
        return {"upgrade_required": None, "upgraded": False,
                "original_path": str(odb_path), "output_path": str(odb_path),
                "error": "'abaqus' not found in PATH"}
    except subprocess.TimeoutExpired:
        return {"upgrade_required": None, "upgraded": False,
                "original_path": str(odb_path), "output_path": str(odb_path),
                "error": "Upgrade timed out"}

    if result_file.exists():
        return json.loads(result_file.read_text(encoding="utf-8"))

    return {
        "upgrade_required": None,
        "upgraded": False,
        "original_path": str(odb_path),
        "output_path": str(odb_path),
        "error": proc.stderr[-1000:] or "No result produced",
    }


def _write_inner_script(path: Path) -> None:
    """Write the Abaqus-runtime inner script for ODB upgrade."""
    code = '''
import sys, json
args = sys.argv[sys.argv.index("--") + 1:]
odb_path, upgraded_path, result_path = args[0], args[1], args[2]

result = {"upgrade_required": False, "upgraded": False,
          "original_path": odb_path, "output_path": odb_path, "error": None}
try:
    import odbAccess
    needs_upgrade = odbAccess.isUpgradeRequiredForOdb(upgradeRequiredOdbPath=odb_path)
    result["upgrade_required"] = bool(needs_upgrade)
    if needs_upgrade:
        odbAccess.upgradeOdb(existingOdbPath=odb_path, upgradedOdbPath=upgraded_path)
        result["upgraded"] = True
        result["output_path"] = upgraded_path
        print("ODB_UPGRADED: " + upgraded_path)
    else:
        print("ODB_OK: no upgrade needed")
except Exception as e:
    result["error"] = str(e)

with open(result_path, "w") as f:
    json.dump(result, f, indent=2)
'''
    path.write_text(code.strip(), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python upgrade_odb.py <file.odb> [upgraded.odb]")
        sys.exit(1)
    r = upgrade_odb_if_needed(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(json.dumps(r, indent=2))
