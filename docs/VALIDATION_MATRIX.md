# Validation Matrix

This matrix records verified environments and evidence for Abaqus Agent's
Simulation QA kernel. It distinguishes real Abaqus execution from local dry-run
or unit-test coverage.

## Current Evidence

| Date | Environment | Abaqus | Case / Workflow | Result | Evidence |
|---|---|---|---|---|---|
| 2026-06-02 | GitHub Actions, Ubuntu, Python 3.10/3.11/3.12 | Not installed | Unit tests + package build | PASS | CI run `26803610038`, `260 passed`, build passed |
| 2026-06-02 | macOS local dev, Python 3.12 venv | Not installed | `run_benchmark.py --dry-run` over 5 public cases | PASS | `5 / 5` dry-run validation |
| 2026-06-02 | Windows 11 23H2 `BUILD-HOST`, Tailscale SSH | Abaqus 2021 | `cantilever` full orchestrator run | PASS | `status=COMPLETED`, `U_tip=-0.0019039579201489687`, `MISES_MAX=0.6528551578521729`, KPI errors `[]` |
| 2026-06-02 | Windows 11 23H2 `BUILD-HOST`, Tailscale SSH | Abaqus 2021 | `plate_hole` full orchestrator run | PASS | `status=COMPLETED`, `MISES_HOLE_EDGE=295.57122802734375`, `U_X_MAX=0.05009150877594948`, `SCF=264.1424560546875`, regression PASS, KPI errors `[]`, exported `mises_contour.png` and `u_magnitude.png` |
| 2026-06-02 | Windows 11 23H2 `BUILD-HOST`, Tailscale SSH | Abaqus 2021 | `modal` full orchestrator run | PASS | `status=COMPLETED`, `freq_1=210.24`, `freq_2=416.36`, `freq_3=1304.0`, regression PASS, KPI errors `[]` |
| 2026-06-02 | Windows 11 23H2 `BUILD-HOST`, Tailscale SSH | Abaqus 2021 | `explicit_impact` full orchestrator run | PASS | `status=COMPLETED`, syntaxcheck warnings `4`, `RF_Z_MAX=31817.26953125`, `U_Z_MIN=-2.0`, regression PASS, KPI errors `[]`, exported `u_magnitude.png` |
| 2026-06-02 | Windows 11 23H2 `BUILD-HOST`, Tailscale SSH | Abaqus 2021 | `blast_plate` full orchestrator run | PASS | `status=COMPLETED`, syntaxcheck warnings `2`, `U_MAX_DEFLECTION=-93.54364776611328`, `PEEQ_MAX=0.026396118104457855`, `ALLPD_MAX=125353184.0`, regression PASS, KPI errors `[]`, exported `u_magnitude.png` and `peeq_contour.png` |
| 2026-06-02 | Windows 11 23H2 `BUILD-HOST`, Tailscale SSH | Abaqus 2021 | Physics Contracts on `cantilever` | PASS | `tip_deflects_downward`, `tip_displacement_regression_band`, `mises_max_reasonable` all PASS |
| 2026-06-02 | Windows 11 23H2 `BUILD-HOST`, Tailscale SSH | Abaqus 2021 | Simulation Diff: baseline load `-1.0` vs candidate load `-1.1` | PASS / Expected WARNING | Diff report showed `bc_load.value -1 -> -1.1`, `U_tip` and `MISES_MAX` changed by `10.00%`, contracts stayed PASS |
| 2026-06-02 | Windows 11 23H2 `BUILD-HOST`, Tailscale SSH | Abaqus 2021 | ODB Lens extractor on real `Cantilever.odb` | PASS | custom recipe with lowercase `u2` returned `U_tip_lower=-0.0019039579201489687`, `MISES_LAST=0.6528551578521729`, errors `[]` |
| 2026-06-02 | Windows 11 23H2 `BUILD-HOST`, Tailscale SSH | Abaqus 2021 | Case Memory search controls against real capsule history | PASS | `python cli.py memory search cases --query PlateHole --sort-by run_id --sort-order asc --min-score 0.5 --json` indexed `4`, matched `1`, returned real `plate_hole` run `95712d55bf05f243`, score `1.25`, reasons `text:platehole`, `contracts passed`, `completed run`; `--artifact mises_contour.png --min-score 0.5` returned the same run, score `1.1`, reason `artifact:mises_contour.png` |
| 2026-06-02 | Windows 11 23H2 `BUILD-HOST`, Tailscale SSH | Abaqus 2021 | Report HTML preview and bundle export from real `plate_hole` capsule | PASS | `GET /api/run/real_plate_hole_report/report.html?template=client_summary&download=false` returned `200 text/html` inline with `PlateWithHole` and embedded image data; `GET /api/run/real_plate_hole_report/report.zip?template=client_summary` returned `200 application/zip`, `1,892,410` bytes, with `report.md`, `report.html`, `capsule.json`, `artifact_manifest.json`, `mises_contour.png`, and `27` included artifacts |
| 2026-06-02 | Windows 11 23H2 `BUILD-HOST`, Tailscale SSH | Abaqus 2021 | Environment preflight command | PASS | `python cli.py validate env --json` returned `status=ready`, resolved `C:\SIMULIA\Commands\abaqus.BAT`, ran `abaqus information=release` with return code `0`, and detected release `2021` |
| 2026-06-02 | Windows 11 23H2 `BUILD-HOST`, Tailscale SSH | Abaqus 2021 | Offline report export CLI from real `plate_hole` capsule | PASS | `python cli.py report export cases\plate_hole\runs\95712d55bf05f243 --template client_summary --out ...\offline_report.html --json` wrote `42,799` byte HTML; zip export wrote `1,893,638` bytes with `32` entries, included `report.md`, `report.html`, `capsule.json`, `result.json`, `artifact_manifest.json`, `artifacts/mises_contour.png`, and `artifacts/u_magnitude.png`; HTML contained `Simulation QA Summary`, `PlateWithHole`, and embedded image data |
| 2026-06-02 | macOS local dev, Python 3.12 venv, browser UI | Not installed | Offline report export API/UI smoke | PASS | `/api/report/export` loaded a synthetic run directory into the Report panel; UI rendered `ui_offline_report`, model `UiOffline`, KPI `U_tip=-0.002`, and client-summary Markdown without starting a new analysis run |
| 2026-06-02 | macOS local dev, Python 3.12 venv, headless Chrome UI | Not installed | Optional PDF export API/UI smoke | PASS | `/api/report/export.pdf` returned `501` with explicit `abaqus-agent[pdf]` / `playwright install chromium` guidance when Playwright was absent; headless Chrome loaded synthetic offline report `ui_pdf_report`, rendered model `UiPdf`, and showed the `下载 .pdf` action without layout overflow |
| 2026-05-06 | External contributor validation | Abaqus 2026 | Cantilever GUI / Windows compatibility | PASS | GLY2024 contribution and case study, see `docs/CASE_STUDY_GLY2024.md` |

## Public Case Coverage

These specs validate without an Abaqus installation, and have now also passed
full Abaqus 2021 execution on Windows:

| Case | Dry-run | Real Abaqus 2021 | Notes |
|---|---|---|---|
| `blast_plate` | PASS | PASS | Explicit blast workflow, PEEQ/U/history KPI extraction |
| `cantilever` | PASS | PASS | Static baseline, contracts, diff, ODB Lens recipe |
| `explicit_impact` | PASS | PASS | Explicit displacement workflow, RF/U KPI extraction |
| `modal` | PASS | PASS | Frequency workflow, eigenfrequency KPI extraction |
| `plate_hole` | PASS | PASS | Static stress concentration workflow and image export |

## Next Validation Targets

- Before each real validation pass, run `abaqus-agent validate env --json` to record OS, Python, Abaqus command resolution, and `abaqus information=release` evidence.
- Windows + Abaqus 2021: repeat full public-case validation after major changes to build, submit, ODB extraction, or visualization.
- Windows + Abaqus 2026: repeat cantilever and one ODB Lens recipe with contributor environment if available.
- Linux + Abaqus: syntaxcheck and custom `.inp` capsule path.
- Report templates: validate optional Playwright PDF export on a machine with Chromium installed, then polish downstream document templates.
