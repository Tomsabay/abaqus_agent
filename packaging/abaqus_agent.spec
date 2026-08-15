# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the Abaqus Agent workbench backend.

Produces a single onedir bundle whose entry (scripts/start_server.py) starts
the FastAPI app in-process (packaged mode: 127.0.0.1, reload off). The Tauri
shell spawns this exe as a sidecar.

Data bundled at repo-relative paths so the app's existing __file__-relative
resolution (frontend/, schema/, cases/) works unchanged inside the frozen
extraction dir. Case run/ outputs (165MB) are excluded — the packaged app
writes runs to the user data dir at runtime.

Build (run from repo root):
  .venv/Scripts/python.exe -m PyInstaller packaging/abaqus_agent.spec \
      --noconfirm --distpath dist --workpath build/_pyi_work
"""

import os
from pathlib import Path

ROOT = Path(os.getcwd())

# ── Data files: static UI + schema + case definitions (no runs/) ──────
datas = [
    (str(ROOT / "frontend"), "frontend"),
    (str(ROOT / "schema"), "schema"),
    # The FreeCAD-derived material cards. core/material_library.py resolves
    # them relative to its own file, so a frozen build without them answers
    # every material name with "not in the library".
    (str(ROOT / "data" / "materials"), "data/materials"),
]

# Case definitions only — skip the multi-hundred-MB runs/ and pycache.
for case_dir in sorted((ROOT / "cases").iterdir()):
    if not case_dir.is_dir():
        continue
    for f in case_dir.iterdir():
        if f.is_file():
            datas.append((str(f), f"cases/{case_dir.name}"))

# post/*.py: these modules resolve their own path via Path(__file__) and pass
# the .py file to an abaqus subprocess (SMAPython). PyInstaller compiles them
# into the PYZ by default — no .py file exists at runtime, and SMAPython errors
# with [Errno 2]. Ship them as data so Path(__file__) points at a real file.
for f in (ROOT / "post").glob("*.py"):
    if f.name != "__init__.py":
        datas.append((str(f), "post"))

# prompts/*.txt: agent/llm_planner.py and features/autorepair read prompt files
# via Path(__file__).parent.parent / "prompts". These text files aren't Python,
# so PyInstaller wouldn't ship them by default.
if (ROOT / "prompts").is_dir():
    datas.append((str(ROOT / "prompts"), "prompts"))

# ── Hidden imports uvicorn resolves dynamically ───────────────────────
hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on",
    # W20: the packaged exe also builds docx/xlsx reports (report-docx /
    # report-xlsx subcommands). python-docx imports lxml through a C extension
    # and openpyxl resolves writers dynamically, so both stay hidden from static
    # analysis; their PyInstaller hooks pull the package data once they are here.
    "lxml",
    "lxml.etree",
    "docx",
    "openpyxl",
]

# ── Excludes: heavy/dev-only deps not needed in the packaged app ──────
excludes = [
    "playwright",      # PDF export degrades gracefully (lazy import)
    "pytest", "_pytest", "ruff",
    "IPython", "notebook", "matplotlib", "numpy", "scipy", "pandas",
    "tkinter",
    # openpyxl imports Pillow only in openpyxl.drawing.image, guarded by
    # try/except, and only for embedding raster images into a sheet. The report
    # workbook uses native charts instead, and nothing else in the app imports
    # PIL — shipping Pillow would add ~11MB (incl. the 7.5MB AVIF codec) and
    # would push the bundle back past the size budget G3 established.
    "PIL",
]

block_cipher = None

a = Analysis(
    [str(ROOT / "scripts" / "start_server.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ── G3: strip the statically linked GPLv3 ffmpeg that imageio_ffmpeg bundles
# (~84MB, 73% of the bundle). Shipping it would impose GPLv3 source-offer
# obligations on a paid product. At runtime post/export_odb_animation_runner
# resolves a user-provided ffmpeg instead (IMAGEIO_FFMPEG_EXE env var or
# system PATH) and degrades to frames-only with an install hint when absent.
# See THIRD_PARTY_NOTICES.md.
def _drop_bundled_ffmpeg(toc):
    return [
        entry for entry in toc
        if not os.path.basename(entry[0]).lower().startswith("ffmpeg")
    ]

a.binaries = _drop_bundled_ffmpeg(a.binaries)
a.datas = _drop_bundled_ffmpeg(a.datas)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="abaqus-agent-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="abaqus-agent-server",
)
