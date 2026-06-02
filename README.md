# Abaqus Agent

[![CI](https://github.com/Tomsabay/abaqus_agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Tomsabay/abaqus_agent/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)

**Local Simulation QA & Regression Framework for Abaqus FEA.**

Turn Abaqus runs into reproducible experiment capsules:

```text
.inp / spec -> syntaxcheck -> solver -> ODB KPI -> physics contracts -> diff report
```

Abaqus Agent runs in your own Abaqus-licensed environment. The core is deterministic and auditable; LLMs, MCP clients, Codex, Claude Code, or the web UI are optional frontends.

## Why This Exists

Most AI simulation demos focus on generating a model or script. Real Abaqus teams usually have a harder problem:

- Did this run use the right input deck, solver settings, Abaqus version, and environment?
- Are the ODB KPIs within expected physical bounds?
- What changed between this run and the previous baseline?
- Why did the solver fail?
- Can this result be turned into a repeatable report for a team or customer?

Abaqus Agent is moving toward the simulation equivalent of `pytest` / CI / diff / diagnostics for Abaqus workflows.

## v0.2 Direction

The current codebase already has the original Abaqus automation pipeline. The v0.2 direction adds a Simulation DevOps kernel:

| Capability | Status | Purpose |
|---|---:|---|
| `custom_inp` first | Implemented | Bring existing customer `.inp` files instead of forcing NL/spec generation. |
| Experiment Capsule | Implemented | Store inputs, artifacts, hashes, environment, and provenance in `capsule.json`. |
| ODB Lens / KPI DSL | Implemented MVP | Reusable KPI extraction recipes and KPI Markdown reports for `.odb` outputs. |
| Physics Contracts | Implemented MVP | Check ranges, directions, relative error, and ordered KPIs. |
| Simulation Diff | Implemented MVP | Compare run/capsule inputs, KPIs, contracts, artifacts, and provenance. |
| Solver Doctor | Implemented MVP | Diagnose `.sta/.msg/.log/.dat` failures from 30+ known patterns. |
| MCP QA Tools | Implemented MVP | Expose capsule, contract, diff, and doctor kernels to MCP clients. |
| Case Memory | Implemented MVP | Search and rank local run/capsule history by metadata, KPIs, contracts, diagnosis IDs, artifact names, similarity signals, sort controls, and minimum score. |
| Report Export | Implemented MVP | Produce Markdown, standalone/printable HTML, and zipped run report bundles from capsules, KPIs, contracts, and visuals. |
| Environment Preflight | Implemented MVP | Record OS, Python, Abaqus command, and release-check evidence across CLI/API/MCP/UI before real validation. |

See [docs/STRATEGY.md](docs/STRATEGY.md) for the product strategy.

## Installation

Install from source:

```bash
git clone https://github.com/Tomsabay/abaqus_agent.git
cd abaqus_agent
pip install -e ".[dev,mcp]"
```

Optional extras:

```bash
pip install -e ".[llm]"  # Anthropic / OpenAI planners
pip install -e ".[all]"  # dev + mcp + llm
```

## Quick Start

Run tests that do not require Abaqus:

```bash
pytest tests/ -v
```

Check whether the current machine is ready for real Abaqus validation:

```bash
abaqus-agent validate env --json
abaqus-agent validate env --strict --out validation-preflight.md
```

Export an offline report from a run directory, `capsule.json`, or `result.json`:

```bash
abaqus-agent report export runs/my_run --template client_summary --out report.html
abaqus-agent report export runs/my_run --out report.zip
```

Validate public benchmark specs without Abaqus:

```bash
python run_benchmark.py --dry-run
```

Run one full Abaqus case on a machine with Abaqus installed:

```bash
python agent/orchestrator.py cases/cantilever/spec.yaml \
  cases/cantilever/expected.json \
  cases/cantilever/runner.json
```

Use an existing `.inp` as a first-class input:

```yaml
meta:
  abaqus_release: "2024"
  model_name: "CustomerModel"
geometry:
  type: custom_inp
  inp_path: model.inp
material:
  name: Placeholder
  E: 210000
  nu: 0.3
analysis:
  solver: standard
  step_type: Static
bc_load: {}
outputs:
  kpis:
    - name: U_tip
      type: nodal_displacement
```

Create an experiment capsule from an `.inp`:

```bash
abaqus-agent capsule init --from-inp model.inp --out runs/model_capsule
```

```python
from capsule.store import init_from_inp

capsule = init_from_inp("model.inp", "runs/model_capsule")
print(capsule["run_id"])
```

Evaluate physics contracts:

```python
from contracts import evaluate_contracts

result = evaluate_contracts(
    [
        {"name": "deflects_down", "type": "direction", "kpi": "U_tip", "direction": "negative"},
        {"name": "stress_margin", "type": "range", "kpi": "MISES_MAX", "max": 250.0},
    ],
    {"U_tip": -0.002, "MISES_MAX": 210.0},
)
```

Diagnose solver logs:

```bash
abaqus-agent doctor Job-1.msg Job-1.sta
```

```python
from doctor import diagnose_logs

diagnosis = diagnose_logs(paths=["Job-1.msg", "Job-1.sta"])
```

Compare KPI results:

```bash
abaqus-agent diff runs/baseline runs/candidate --out diff.md
```

Search local case memory:

```bash
abaqus-agent memory search runs/ --query too_many_attempts --json
abaqus-agent memory search runs/ --similar-to runs/candidate --kpi U_tip --out memory.md
```

```python
from simdiff import diff_runs

diff = diff_runs("runs/baseline", "runs/candidate")
```

Normalize an ODB Lens KPI recipe and render a KPI report:

```yaml
kpis:
  - name: max_mises
    source: odb
    field: S
    invariant: MISES
    region: set:CRITICAL_ZONE
    reducer: max
```

```bash
abaqus-agent lens normalize kpis.yaml --out _kpi_spec.json
abaqus-agent lens report result.json --recipe kpis.yaml --out kpi_report.md
```

## Architecture

```text
Codex / Claude Code / ChatGPT / Web UI / CLI
        |
        v
Intent layer (optional LLM)
        |
        v
Simulation DevOps kernel
  - Experiment Capsule
  - Physics Contracts
  - ODB Lens
  - Solver Doctor
  - Simulation Diff
        |
        v
Abaqus adapter / local BYOL runner
  - noGUI
  - syntaxcheck
  - submit
  - monitor
  - ODB extraction
        |
        v
Artifacts: .inp, .cae, .odb, .sta, .msg, .log, reports
```

The older NL-to-spec planner remains available, but it is no longer the product center.

## Project Structure

```text
agent/              End-to-end orchestration and optional LLM planner
capsule/            Experiment capsule manifest, hashing, and store helpers
contracts/          Physics contract evaluation
doctor/             Solver log diagnostics and pattern library
odb_lens/           Declarative KPI recipes and Markdown KPI reports
simdiff/            KPI diff and Markdown rendering
runner/             Abaqus build, syntaxcheck, submit, monitor
post/               ODB KPI extraction
tools/              Errors, schema validation, static guard, Abaqus command resolver
mcp_server.py       MCP server for agent integration
mcp_bridge.py       HTTP/SSE bridge for browser clients
server.py           FastAPI server
cases/              Public benchmark specs
premium/            Open-core prototype modules from v0.1
```

## Benchmark Status

Public specs currently cover:

| Case | Type | Solver | Key KPIs |
|---|---|---|---|
| `cantilever` | 3D static beam | Standard | `U_tip`, `MISES_MAX` |
| `plate_hole` | 2D plane-stress plate | Standard | `MISES_HOLE_EDGE`, `U_X_MAX`, `SCF` |
| `modal` | Fixed beam modal | Standard / Lanczos | `freq_1`, `freq_2`, `freq_3` |
| `explicit_impact` | Dynamic compression | Explicit | `RF_Z_MAX`, `U_Z_MIN` |
| `blast_plate` | Protective blast plate demo | Explicit | `U_MAX_DEFLECTION`, `PEEQ_MAX`, `ALLPD_MAX` |

Notes:

- `python run_benchmark.py --dry-run` validates specs without Abaqus.
- `abaqus-agent validate env` and the Environment panel record OS, Python, Abaqus command resolution, and `abaqus information=release` evidence before real validation.
- `abaqus-agent report export` produces Markdown, standalone HTML, or zipped report bundles from offline run evidence.
- Full regression requires a local Abaqus installation and license.
- Current environment evidence is tracked in [docs/VALIDATION_MATRIX.md](docs/VALIDATION_MATRIX.md).
- Current local validation has been done on Abaqus 2021 / Windows.
- External contributor validation exists for Abaqus 2026 compatibility.

## Safety And Deployment

All generated or processed workflows are intended to run locally in the user's own Abaqus-licensed environment.

The recommended commercial deployment model is BYOL:

- customer-local runner
- customer-owned Abaqus license
- local artifacts and ODBs
- optional consulting, report templates, private recipes, and team runner

Do not run third-party Abaqus workloads as a hosted SaaS without explicit legal review of the relevant Dassault Systemes license terms.

## Roadmap

- [x] 7-stage Abaqus pipeline: validate, build, syntaxcheck, submit, monitor, extract, compare
- [x] Windows `.bat` command resolver for Abaqus subprocess calls
- [x] MCP server and HTTP bridge
- [x] FastAPI/SSE web API
- [x] `custom_inp` no-CAE build path
- [x] v0.2 capsule / contract / diff / doctor kernel MVP
- [x] Capsule-backed run output from the orchestrator
- [x] Solver Doctor / contract check / KPI diff CLI
- [x] ODB Lens YAML KPI recipe normalization and KPI Markdown reports
- [x] Simulation Diff CLI/API/UI with real Windows Abaqus validation
- [x] MCP tools for capsule init, contract check, Solver Doctor, and Simulation Diff
- [x] ODB Lens direct Abaqus extractor coverage for frame, region, component, invariant, and reducer fields
- [x] Markdown report templates
- [x] Validation matrix for Abaqus versions and operating systems
- [x] Case Memory deterministic local capsule search
- [x] Case Memory CLI/API/MCP/UI workflow with real capsule-history validation
- [x] Case Memory artifact, sort order, and minimum score controls across CLI/API/MCP/UI
- [x] Markdown report copy/download actions in the web UI
- [x] Standalone HTML report export endpoint and web UI download action
- [x] Browser preview/print mode for downstream PDF handoff
- [x] Report bundle zip endpoint and web UI download action
- [x] Environment preflight CLI/API/MCP/UI workflow for Linux/Windows/Abaqus version validation readiness
- [x] Offline report export CLI for run directories, capsules, and result JSON files

## Acknowledgments

- **GLY2024 / Goulingyun** — first external contributor. Verified Abaqus 2026 compatibility and contributed Windows command-path fixes. See [docs/CASE_STUDY_GLY2024.md](docs/CASE_STUDY_GLY2024.md).

## License

Apache 2.0. See [LICENSE](LICENSE).
