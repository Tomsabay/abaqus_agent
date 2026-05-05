# Abaqus Agent

[![CI](https://github.com/Tomsabay/abaqus_agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Tomsabay/abaqus_agent/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/abaqus-agent)](https://pypi.org/project/abaqus-agent/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![Python](https://img.shields.io/pypi/pyversions/abaqus-agent)](https://pypi.org/project/abaqus-agent/)

> **LLM-powered automation agent for Abaqus FEA.**
> Natural language -> Problem Spec -> CAE model -> Solver -> KPI report.

---

## Installation

```bash
pip install abaqus-agent            # Core
pip install abaqus-agent[mcp]       # + MCP server support
pip install abaqus-agent[llm]       # + LLM backends (Anthropic, OpenAI)
pip install abaqus-agent[all]       # Everything including dev tools
```

Or install from source:

```bash
git clone https://github.com/Tomsabay/abaqus_agent.git
cd abaqus_agent
pip install -e ".[dev,mcp]"
```

### Docker

```bash
docker compose up -d
# API at http://localhost:8000
# MCP bridge at http://localhost:8001
```

---

## Architecture

```
User (NL) -> LLMPlanner -> spec.yaml
                              |
                       validate_spec (schema)
                              |
                       build_model (CAE noGUI -> .inp)
                              |
                       syntaxcheck (no license consumed)
                              |
                       submit_job (analysis execution)
                              |
                       monitor_job (.sta / .log polling)
                              |
                       extract_kpis (abaqus python -> ODB)
                              |
                       compare_expected -> result.json + benchmark report
```

**Design principles**

| Principle | Implementation |
|-----------|---------------|
| Low-cost fail-fast | `syntaxcheck` gate before solver (no license consumed) |
| Idempotency | `run_id = sha256(spec)` -- re-run reads cached artifacts |
| Safety | Static AST guard blocks forbidden imports/calls before execution |
| Structured errors | `AbaqusAgentError(ErrorCode, message, suggestion)` -- every failure is diagnosable |
| Separation of runtimes | Outer Python (orchestrator) <-> Abaqus Python (CAE/ODB) communicate via files |

---

## Dashboard Preview

<!-- TODO: 截一张你本地跑起来的 Dashboard 截图，替换下面的占位 -->
<!-- 建议截图内容：深色主题 + YAML 编辑器 + KPI 图表 + 实时日志，展示完整工作流 -->
<!-- 截图步骤：
  1. python server.py 启动服务
  2. 浏览器打开 http://localhost:8000
  3. 加载一个 cantilever case，跑一遍
  4. 截图或录 GIF（推荐用 LICEcap 或 Kap 录制）
  5. 图片放到 docs/assets/ 目录下
-->

```
┌─────────────────────────────────────────────────────────────────┐
│  Abaqus Agent Dashboard                              [dark UI] │
│                                                                 │
│  ┌─── YAML Editor ───┐  ┌──── KPI Results ─────┐              │
│  │ meta:              │  │ U_tip: -0.01587 mm   │              │
│  │   model: Cantilever│  │ Expected: -0.01588   │              │
│  │ geometry:          │  │ Error: 0.06%  ✓      │              │
│  │   type: cantilever │  │                      │              │
│  │   L: 100           │  │ ┌──── Chart ──────┐  │              │
│  │   ...              │  │ │  ██             │  │              │
│  └────────────────────┘  │ │  ████           │  │              │
│                          │ │  ██████         │  │              │
│  ┌─── Live Logs ──────┐  │ └────────────────┘  │              │
│  │ ✓ validate_spec    │  └──────────────────────┘              │
│  │ ✓ build_model      │                                        │
│  │ ✓ syntaxcheck      │  [▶ Run Pipeline]  [📋 Load Case]     │
│  │ ● submit_job...    │                                        │
│  └────────────────────┘                                        │
└─────────────────────────────────────────────────────────────────┘
```

> **上图为 ASCII 示意。** 实际截图请替换为：`![Dashboard](docs/assets/dashboard.png)`

---

## Quick Start

### 1. Run unit tests (no Abaqus required)

```bash
pytest tests/ -v
```

### 2. Validate all benchmark specs (no Abaqus)

```bash
python run_benchmark.py --dry-run
```

### 3. Run a single case end-to-end (requires Abaqus)

```bash
python agent/orchestrator.py cases/cantilever/spec.yaml \
    cases/cantilever/expected.json \
    cases/cantilever/runner.json
```

### 4. Start the API server

```bash
abaqus-agent
# or: uvicorn server:app --reload --port 8000
```

### 5. NL -> Spec generation

```bash
# Template fallback (no LLM key needed)
python agent/llm_planner.py "100mm cantilever beam, 1MPa tip pressure, output tip deflection"

# With Anthropic
ANTHROPIC_API_KEY=... python agent/llm_planner.py "..."

# With OpenAI
OPENAI_API_KEY=... python agent/llm_planner.py "..."
```

---

## Project Structure

```
abaqus-agent/
+-- schema/
|   +-- spec_schema.json        # JSON Schema for Problem Spec
+-- cases/
|   +-- cantilever/             # Case 1: 3D static cantilever
|   +-- plate_hole/             # Case 2: 2D plate with hole (stress concentration)
|   +-- modal/                  # Case 3: Modal / frequency analysis
|   +-- explicit_impact/        # Case 4: Explicit dynamic impact
+-- core/
|   +-- pipeline.py             # Shared pipeline logic
|   +-- helpers.py              # Utility functions
|   +-- spec_generator.py       # NL -> spec generation
+-- runner/
|   +-- build_model.py          # CAE noGUI -> .inp
|   +-- syntaxcheck.py          # syntaxcheck (no token consumed)
|   +-- submit_job.py           # analysis execution
|   +-- monitor_job.py          # .sta/.log status polling
+-- post/
|   +-- extract_kpis.py         # ODB -> KPI dict (via abaqus python)
|   +-- upgrade_odb.py          # ODB version check + upgrade
+-- tools/
|   +-- errors.py               # ErrorCode enum + AbaqusAgentError
|   +-- static_guard.py         # AST security guard
|   +-- schema_validator.py     # Spec validation
+-- agent/
|   +-- orchestrator.py         # End-to-end pipeline
|   +-- llm_planner.py          # NL -> spec.yaml
+-- premium/
|   +-- licensing.py            # Feature gating
|   +-- coupling/               # Multi-physics coupling
|   +-- adaptivity/             # Automatic mesh adaptivity
|   +-- parametric/             # Batch parametric sweeps
|   +-- geometry_ext/           # Extended geometry types
|   +-- autorepair/             # Advanced failure auto-repair
+-- prompts/                    # LLM system prompts
+-- frontend/                   # Web UI
+-- server.py                   # FastAPI REST API
+-- mcp_server.py               # MCP server (AI agent integration)
+-- mcp_bridge.py               # HTTP-to-MCP bridge
+-- run_benchmark.py            # Benchmark runner + report generator
+-- pyproject.toml              # Python packaging
+-- Dockerfile                  # Container support
+-- Makefile                    # Common commands
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
| `cantilever` | 3D static | Standard | Tip deflection U2 | PL^3/(3EI) |
| `plate_hole` | 2D plane stress | Standard | Max Mises at hole | Kt ~ 3.0 |
| `modal` | Frequency | Standard | Natural frequencies | Euler beam theory |
| `explicit_impact` | Dynamic | Explicit | Reaction force, displacement | -- |

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
   - Does not consume license tokens

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

## Abaqus Version Compatibility

| Abaqus Release | Python Runtime | Notes |
|---------------|----------------|-------|
| <= 2023 | Python 2.7.15 | Legacy; limited third-party package support |
| 2024+ | Python 3.10.5 | Use `abqPy2to3` for script migration; `abqPip` for packages |
| 2025 | Python 3.10.x | Continued Py3 |

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

- [Bug Reports](https://github.com/Tomsabay/abaqus_agent/issues/new?template=bug_report.yml)
- [Feature Requests](https://github.com/Tomsabay/abaqus_agent/issues/new?template=feature_request.yml)
- [Contributing Guide](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)

### Acknowledgments

- **[@ganansuan647](https://github.com/ganansuan647)** (GLY2024) — first external contributor.
  Verified end-to-end pipeline on Abaqus 2026, contributed Python 3 compatibility fixes
  ([PR #1](https://github.com/Tomsabay/abaqus_agent/pull/1)) and the `tools/abaqus_cmd.py`
  module for Windows `.bat` path resolution ([PR #2](https://github.com/Tomsabay/abaqus_agent/pull/2)).
  See [docs/CASE_STUDY_GLY2024.md](docs/CASE_STUDY_GLY2024.md).

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

## Roadmap

- [x] 7-stage pipeline (validate -> build -> syntaxcheck -> submit -> monitor -> extract -> compare)
- [x] 4 benchmark cases with analytical references
- [x] Static AST security guard + schema validation
- [x] LLM integration (Anthropic / OpenAI / template fallback)
- [x] MCP server + HTTP bridge for AI agent integration
- [x] FastAPI REST API with SSE streaming
- [x] Web frontend
- [x] 5 premium features (coupling, adaptivity, parametric, geometry, autorepair)
- [x] 197 unit tests
- [x] CI/CD + PyPI packaging
- [ ] Multi-step auto-repair with failure analysis loop
- [ ] Additional geometry types (shell, wire, assembly)
- [ ] Cloud deployment templates (AWS, Azure)
- [ ] Abaqus 2025 Python 3 migration tooling

---

## License

Apache 2.0 -- see [LICENSE](LICENSE) for details.
