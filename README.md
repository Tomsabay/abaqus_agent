# Abaqus Agent

> **LLM-powered automation agent for Abaqus FEA.**
> Natural language → Problem Spec → CAE model → Solver → KPI report.

---

## Architecture

```
User (NL) → LLMPlanner → spec.yaml
                              ↓
                       validate_spec (schema)
                              ↓
                       build_model (CAE noGUI → .inp)
                              ↓
                       syntaxcheck (no license consumed)
                              ↓
                       submit_job (analysis execution)
                              ↓
                       monitor_job (.sta / .log polling)
                              ↓
                       extract_kpis (abaqus python → ODB)
                              ↓
                       compare_expected → result.json + benchmark report
```

**Design principles**

| Principle | Implementation |
|-----------|---------------|
| Low-cost fail-fast | `syntaxcheck` gate before solver (no license consumed) |
| Idempotency | `run_id = sha256(spec)` — re-run reads cached artifacts |
| Safety | Static AST guard blocks forbidden imports/calls before execution |
| Structured errors | `AbaqusAgentError(ErrorCode, message, suggestion)` — every failure is diagnosable |
| Separation of runtimes | Outer Python (orchestrator) ↔ Abaqus Python (CAE/ODB) communicate via files |

---

## Project Structure

```
abaqus-agent/
├── schema/
│   └── spec_schema.json        # JSON Schema for Problem Spec
├── cases/
│   ├── cantilever/             # Case 1: 3D static cantilever
│   ├── plate_hole/             # Case 2: 2D plate with hole (stress concentration)
│   ├── modal/                  # Case 3: Modal / frequency analysis
│   └── explicit_impact/        # Case 4: Explicit dynamic impact
│       ├── spec.yaml
│       ├── expected.json       # KPI tolerance definitions
│       └── runner.json         # cpus, timeout, license queue config
├── runner/
│   ├── build_model.py          # D3: CAE noGUI → .inp
│   ├── syntaxcheck.py          # D4: syntaxcheck (no token consumed)
│   ├── submit_job.py           # D5: analysis execution
│   └── monitor_job.py          # D7: .sta/.log status polling
├── post/
│   ├── extract_kpis.py         # D6: ODB → KPI dict (via abaqus python)
│   └── upgrade_odb.py          # ODB version check + upgrade
├── tools/
│   ├── errors.py               # ErrorCode enum + AbaqusAgentError
│   ├── static_guard.py         # D9: AST security guard
│   └── schema_validator.py     # Spec validation
├── agent/
│   ├── orchestrator.py         # End-to-end pipeline
│   └── llm_planner.py          # NL → spec.yaml (OpenAI / Anthropic / template)
├── prompts/
│   ├── spec_generator.txt      # Prompt: NL → spec YAML
│   ├── script_generator.txt    # Prompt: spec → CAE script
│   └── failure_analyzer.txt    # Prompt: log → root cause + fix
├── tests/
│   ├── test_schema.py
│   ├── test_static_guard.py
│   ├── test_errors.py
│   └── test_monitor_job.py
├── run_benchmark.py            # Benchmark runner + report generator
└── requirements.txt
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run unit tests (no Abaqus required)

```bash
pytest tests/ -v
```

### 3. Validate all benchmark specs (no Abaqus)

```bash
python run_benchmark.py --dry-run
```

### 4. Run a single case end-to-end (requires Abaqus)

```bash
python agent/orchestrator.py cases/cantilever/spec.yaml \
    cases/cantilever/expected.json \
    cases/cantilever/runner.json
```

### 5. Run full benchmark suite

```bash
python run_benchmark.py
```

### 6. NL → Spec generation

```bash
# Template fallback (no LLM key needed)
python agent/llm_planner.py "100mm悬臂梁，端部施加1MPa压力，输出梁端挠度"

# With Anthropic (set ANTHROPIC_API_KEY)
ANTHROPIC_API_KEY=sk-... python agent/llm_planner.py "..."

# With OpenAI (set OPENAI_API_KEY)
OPENAI_API_KEY=sk-... python agent/llm_planner.py "..."
```

---

## Problem Spec Format

```yaml
meta:
  abaqus_release: "2024"     # "2023" | "2024" | "2025"
  model_name: "Cantilever"
  units: "mm_MPa_t"
  description: "One sentence description"

geometry:
  type: cantilever_block      # see supported types below
  L: 100.0                    # mm
  W: 10.0
  H: 10.0
  seed_size: 5.0

material:
  name: Steel
  E: 210000.0                 # MPa
  nu: 0.3
  density: 7.85e-9            # t/mm^3 (required for dynamic)

analysis:
  solver: standard            # standard | explicit
  step_type: Static           # Static | Frequency | Dynamic_Explicit | Dynamic_Implicit
  cpus: 2
  mp_mode: threads            # threads | mpi

bc_load:
  fixed_face: "x=0"
  load_face:  "x=L"
  load_type:  pressure        # pressure | concentrated_force | displacement
  value: -1.0

outputs:
  kpis:
    - name: U_tip
      type: nodal_displacement
      location: tip_center
      component: U2
```

### Supported geometry types

| Type | Parameters |
|------|-----------|
| `cantilever_block` | L, W, H, seed_size |
| `plate_with_hole` | L, W, R (hole radius), seed_size |
| `axisymmetric_disk` | L (height), R (outer radius), seed_size |
| `custom_inp` | inp_path (copy existing .inp directly) |

---

## Benchmark Cases

| Case | Type | Solver | Key KPI | Analytical Reference |
|------|------|--------|---------|---------------------|
| `cantilever` | 3D static | Standard | Tip deflection U2 | PL³/(3EI) |
| `plate_hole` | 2D plane stress | Standard | Max Mises at hole | Kt ≈ 3.0 |
| `modal` | Frequency | Standard | Natural frequencies | Euler beam theory |
| `explicit_impact` | Dynamic | Explicit | Reaction force, displacement | — |

### expected.json format

```json
{
  "kpis": {
    "U_tip": {
      "value": -2.0e-3,
      "rtol": 0.10,
      "atol": 1e-6,
      "unit": "mm",
      "note": "Analytical: PL^3/(3EI)"
    }
  }
}
```

---

## Safety Architecture

All LLM-generated scripts pass through a 3-layer gate before execution:

1. **Static AST Guard** (`tools/static_guard.py`)
   - Blocks: `os`, `subprocess`, `socket`, `requests`, `eval`, `exec`, `__import__`
   - Whitelist: all standard Abaqus modules

2. **Schema Validation** (`tools/schema_validator.py`)
   - Problem Spec validated against `schema/spec_schema.json` before any code runs

3. **Abaqus syntaxcheck**
   - `.inp` validated by Abaqus before job submission
   - **Does not consume license tokens** (official docs)

---

## Abaqus Version Compatibility

| Abaqus Release | Python Runtime | Notes |
|---------------|----------------|-------|
| ≤ 2023 | Python 2.7.15 | Legacy; limited third-party package support |
| 2024+ | Python 3.10.5 | Use `abqPy2to3` for script migration; `abqPip` for packages |
| 2025 | Python 3.10.x | Continued Py3 |

Use `abqPy2to3` migration tool for pre-2024 scripts when upgrading.

---

## Error Codes

| Code | Meaning | Auto-suggestion |
|------|---------|----------------|
| `SYNTAX_ERROR` | .inp keyword error | Run syntaxcheck; fix .inp |
| `LICENSE_UNAVAILABLE` | No free token | Wait or reduce concurrent jobs |
| `NONCONVERGENCE` | Solver diverged | Reduce increment, enable nlgeom |
| `ODB_UPGRADE_REQUIRED` | ODB version mismatch | Call `upgrade_odb_if_needed()` |
| `PATH_TOO_LONG` | Path > 256 chars | Shorten workdir path |
| `STATIC_GUARD_BLOCKED` | Dangerous code | Remove forbidden imports/calls |

Full list: `tools/errors.py`

---

## Commercial Deployment

> **License compliance note**: Abaqus license terms restrict running the software
> as an online service / ASP using your own license for third-party workloads.
> The recommended deployment model is:
>
> - **Customer-local runner**: agent software runs in the customer's own Abaqus-licensed environment
> - **Consulting delivery**: you deliver results/reports as a service, not software access
>
> Always verify against your Abaqus OST/LPT before commercial deployment.

---

## Roadmap (2-week MVP)

- [x] D1: Problem Spec schema + 4 benchmark cases
- [x] D2-D3: build_model (CAE noGUI → .inp)
- [x] D4: syntaxcheck gate
- [x] D5: submit_job (analysis execution)
- [x] D6: extract_kpis (ODB via abaqus python)
- [x] D7: monitor_job (.sta/.log polling) + error classification
- [x] D8: 4 benchmark cases with expected KPIs
- [x] D9: Static guard + schema validator
- [x] D10: Structured logging (result.json per run)
- [x] D11: LLM integration (OpenAI / Anthropic / template fallback)
- [x] D12: Benchmark runner + Markdown report
- [x] D13: Test suite (unit tests, no Abaqus required)
- [ ] D14: CI/CD config + first trial user run

---

## References

- Abaqus Scripting User's Guide — CAE API, ODB access, examples
- Abaqus/CAE Execution — `noGUI`, passing arguments, license checkout
- Abaqus/Standard and Explicit Execution — `syntaxcheck`, `cpus`, `mp_mode`, `background`
- Abaqus Scripting Reference — `odbAccess.openOdb`, `isUpgradeRequiredForOdb`, `upgradeOdb`
- License Management Parameters — DSLS/FlexNet, SimUnit, queuing
- Abaqus 2024 What's New — Python 3.10.5 upgrade, `abqPy2to3`, `abqPip`
