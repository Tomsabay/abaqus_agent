# Abaqus Agent Strategy

## Positioning

Abaqus Agent is moving from:

```text
Natural language -> YAML/spec -> Abaqus script
```

to:

```text
Local Simulation QA & Regression Framework for Abaqus
```

The product should feel like `pytest`, CI, diff, diagnostics, and reporting for Abaqus simulations.

## Why Not Just NL To YAML

General-purpose agents, MCP servers, GUI automation, and coding copilots are making tool control cheaper. The durable value is not whether an AI can operate Abaqus. The durable value is whether a simulation run is:

- reproducible
- comparable
- physically plausible
- diagnosable when it fails
- reportable to a team or customer
- safe to run in a local BYOL environment

LLMs can remain useful as an intent layer, but the kernel must be deterministic and testable.

## Product Pillars

### Experiment Capsule

Every run should be packaged into a capsule:

```text
capsule/
  capsule.json
  input/
    spec.yaml
    model.inp
  scripts/
  logs/
    job.sta
    job.msg
    job.log
  results/
    job.odb
    kpis.json
  reports/
    report.md
  provenance.json
```

The capsule is the foundation for audit, diff, report, regression, and case memory.

### Physics Contracts

Expected values alone are not enough. A simulation QA layer should check contracts such as:

- deflection direction
- stress range
- frequency ordering
- relative tolerance to baseline
- energy balance
- warning vs error severity

### ODB Lens

ODB post-processing should be reusable and declarative:

```yaml
kpis:
  - name: max_mises
    source: odb
    field: S
    invariant: MISES
    region: set:CRITICAL_ZONE
    frame: last
    reducer: max
```

This matters because many real users already have `.inp` and `.odb` files. They need repeatable KPI extraction and reports more than from-scratch model generation.

### Solver Doctor

Solver Doctor reads `.sta`, `.msg`, `.log`, and `.dat` files and returns:

- category
- severity
- evidence snippet
- suggested fix

Initial categories: license, convergence, contact, material, syntax, ODB, path/environment, resources, explicit dynamics.

### Simulation Diff

Simulation Diff compares two runs like software diff:

- inputs
- materials
- boundary conditions
- mesh settings
- solver setup
- KPIs
- contracts
- report conclusions

The MVP now compares KPI changes, contract status, spec fields, capsule inputs, artifacts, and provenance.

### Case Memory

Customer-local capsules are now searchable deterministic memory:

- similar geometry
- similar materials
- previous failures
- known KPI recipes
- report templates
- internal expert workflows

The MVP scans local run/capsule directories and ranks cases by metadata, status,
KPI overlap, contract results, Solver Doctor diagnosis IDs, input hashes, and
simple similarity signals. It is available through CLI, HTTP API, and MCP.

## v0.2 Scope

Do not add more complex physics demos before the QA kernel is credible.

v0.2 should deliver:

- `custom_inp` first-class path
- capsule manifest and hash store
- KPI DSL / ODB Lens MVP
- physics contract evaluator
- Simulation Diff report
- 30+ Solver Doctor patterns
- MCP tools for deterministic QA kernels
- README and GitHub presentation aligned with the new positioning
- CI green

Current v0.2-dev implementation status:

- Implemented: `custom_inp` no-CAE path, orchestrator-produced capsules, capsule manifest helpers, ODB Lens recipe normalization and KPI Markdown reports, physics contract evaluator, Simulation Diff reports, 30+ Solver Doctor patterns, CLI/API/UI report workflows, MCP QA tools, report templates, validation matrix, Case Memory search, Case Memory UI, and Markdown report export actions.
- Validated: full local test/build pipeline, CI on Python 3.10/3.11/3.12, real Windows Abaqus 2021 execution for all 5 public cases, a real cantilever baseline/candidate Simulation Diff, ODB Lens on real ODBs, and Case Memory search against real capsule history.
- Planned next: PDF/downstream document export, Linux/Abaqus validation, Abaqus 2026 repeat validation, and deeper Case Memory ranking/search controls.

## Commercial Path

Use BYOL local runner. The customer's Abaqus license and data stay on their machines.

Best early offers:

- automation diagnostic: one workflow review and automation plan
- single-case automation package: `.inp` -> run -> KPI -> report
- simulation regression package: baselines, contracts, reports, failure diagnosis
- private team runner later: queue, permissions, audit, private recipes

Do not host third-party Abaqus workloads on a server controlled by this project without explicit legal review.

## What Not To Do

- Do not make “NL -> YAML” the homepage promise.
- Do not make hosted Abaqus SaaS the business model.
- Do not publicly optimize for weapon/penetration/kill-chain scenarios.
- Do not compete on “who can connect an AI to Abaqus”; compete on QA, evidence, reports, and memory.
- Do not keep adding premium prototypes before the open core is trusted.
