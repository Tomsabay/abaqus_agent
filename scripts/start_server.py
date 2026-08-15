"""
scripts/start_server.py
-----------------------
Unified server launcher. Reads all runtime configuration from core.config
(env-driven) and starts uvicorn. Replaces bare `python server.py`.

  - dev (default):        python scripts/start_server.py
  - packaged (Tauri):     the shell sets ABAQUS_AGENT_DATA_DIR + ABAQUS_AGENT_PORT
                          + ABAQUS_AGENT_DEV=0, then runs the frozen exe whose
                          entry calls main() here.

This is also the intended PyInstaller entry point (stage 1): it imports the app
object and runs it in-process, which works inside a frozen executable where the
"server:app" import-string + reload form does not.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _docx_main():
    from reporting.build_docx_report import main as entry
    return entry


def _xlsx_main():
    from reporting.build_xlsx_workbook import main as entry
    return entry


def _pdf_route_main():
    from reporting.pdf_route import main as entry
    return entry


REPORT_SUBCOMMANDS = {
    "report-docx": _docx_main,
    "report-xlsx": _xlsx_main,
    "report-pdf": _pdf_route_main,
}


def main() -> int:
    # A frozen Windows exe defaults stdout to the GBK console codec, which
    # crashes on the unicode banner below. Force UTF-8 with replacement.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass  # stream may be None (windowed) or already fine

    # BUILD_SPEC W20 criterion 6: the packaged bundle has no python interpreter of
    # its own, so the report builders are reachable as subcommands of this entry.
    # Zero args (how the Tauri shell launches it) still starts the server.
    argv = sys.argv[1:]
    if argv and argv[0] in REPORT_SUBCOMMANDS:
        return REPORT_SUBCOMMANDS[argv[0]]()(argv[1:])

    import uvicorn

    from core import config
    from core.helpers import check_abaqus, list_cases

    host = config.host()
    port = config.port()
    dev = config.is_dev()

    print("\n  Abaqus Agent — workbench server")
    print("  ─────────────────────────────")
    print(f"  URL      : http://{host}:{port}/workbench")
    print(f"  Mode     : {'dev (reload)' if dev else 'packaged'}")
    if config.is_packaged():
        print(f"  Data dir : {config.data_dir()}")
    print(f"  Abaqus   : {'✓ real solve' if check_abaqus() else '✗ simulation/replay mode'}")
    print(f"  Cases    : {len(list_cases())} available")
    print()

    if dev:
        uvicorn.run("server:app", host=host, port=port, reload=True)
    else:
        from server import app
        uvicorn.run(app, host=host, port=port, reload=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
