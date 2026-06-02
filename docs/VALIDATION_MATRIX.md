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
| 2026-06-02 | Windows 11 23H2 `BUILD-HOST`, Tailscale SSH | Abaqus 2021 | Physics Contracts on `cantilever` | PASS | `tip_deflects_downward`, `tip_displacement_regression_band`, `mises_max_reasonable` all PASS |
| 2026-06-02 | Windows 11 23H2 `BUILD-HOST`, Tailscale SSH | Abaqus 2021 | Simulation Diff: baseline load `-1.0` vs candidate load `-1.1` | PASS / Expected WARNING | Diff report showed `bc_load.value -1 -> -1.1`, `U_tip` and `MISES_MAX` changed by `10.00%`, contracts stayed PASS |
| 2026-06-02 | Windows 11 23H2 `BUILD-HOST`, Tailscale SSH | Abaqus 2021 | ODB Lens extractor on real `Cantilever.odb` | PASS | custom recipe with lowercase `u2` returned `U_tip_lower=-0.0019039579201489687`, `MISES_LAST=0.6528551578521729`, errors `[]` |
| 2026-05-06 | External contributor validation | Abaqus 2026 | Cantilever GUI / Windows compatibility | PASS | GLY2024 contribution and case study, see `docs/CASE_STUDY_GLY2024.md` |

## Public Case Dry-Run Coverage

These specs validate without an Abaqus installation:

| Case | Status | Notes |
|---|---|---|
| `blast_plate` | DRY_RUN_PASS | Spec/schema path only |
| `cantilever` | DRY_RUN_PASS | Spec/schema path only |
| `explicit_impact` | DRY_RUN_PASS | Spec/schema path only |
| `modal` | DRY_RUN_PASS | Spec/schema path only |
| `plate_hole` | DRY_RUN_PASS | Spec/schema path only |

## Next Validation Targets

- Windows + Abaqus 2021: continue full public-case validation for `modal`, `explicit_impact`, and `blast_plate`.
- Windows + Abaqus 2026: repeat cantilever and one ODB Lens recipe with contributor environment if available.
- Linux + Abaqus: syntaxcheck and custom `.inp` capsule path.
- Report templates: export-to-PDF or downstream document rendering once a PDF path is implemented.
