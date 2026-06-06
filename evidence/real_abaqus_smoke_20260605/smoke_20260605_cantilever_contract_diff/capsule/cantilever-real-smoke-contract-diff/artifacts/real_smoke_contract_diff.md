# Abaqus Agent Real Smoke Contract/Diff Report

## Verdict Summary

| Area | Status | Detail |
|---|---|---|
| Overall | `FAIL` | Real smoke KPI values were checked against contracts and expected KPI baselines. |
| Physics Contracts | `FAIL` | 1 pass / 0 warning / 3 fail. |
| Simulation Diff | `FAIL` | 2 KPI rows; 2 changed, 0 added, 0 removed. |
| Real Abaqus smoke | `verified` | Source smoke status: `real-env-verified`. |

## Run Metadata

- Project: `abaqus-agent`
- Workflow: `real-smoke-contract-diff`
- Case: `cantilever`
- Run ID: `cantilever-real-smoke-contract-diff`
- Generated at: `2026-06-05T16:20:34Z`
- Real environment required: `true`
- Real environment verified: `true`

## Real Smoke Source

- Smoke evidence: `evidence/real_abaqus_smoke_20260605/smoke_20260605_cantilever_kpi_float/smoke_evidence.json`
- KPI result: `evidence/real_abaqus_smoke_20260605/smoke_20260605_cantilever_kpi_float/run/_kpi_result.json`
- ODB artifact: `evidence/real_abaqus_smoke_20260605/smoke_20260605_cantilever_kpi_float/run/Cantilever.odb`
- Source mode: `require-real`

| Stage | Status | Real Verified |
|---|---|---|
| environment_preflight | completed | true |
| input_job_preparation | completed | true |
| syntaxcheck | completed | true |
| submit_job | completed | true |
| monitor_status_collection | completed | true |
| odb_kpi_adapter_probe | completed | true |
| evidence_report_generation | completed | false |

## KPI Values

| KPI | Expected Baseline | Real ODB Candidate |
|---|---:|---:|
| MISES_MAX | 0.6 | 1.07003 |
| U_tip | -0.002 | -1.08433e-05 |

## Physics Contracts

Status: `FAIL`

| Contract | Status | Message |
|---|---|---|
| tip deflects downward | PASS | U_tip=-1.084326231648447e-05 satisfies < 0.0 |
| tip deflection near reference | FAIL | U_tip is outside tolerance |
| max stress plausible range | FAIL | MISES_MAX=1.0700273513793945 is above max 1.0 |
| max stress near reference | FAIL | MISES_MAX is outside tolerance |

## Simulation Diff

# Simulation Diff: KPI

- Status: `FAIL`
- Total KPIs: `2`
- Changed: `2`
- Added: `0`
- Removed: `0`

| KPI | Status | Baseline | Candidate | Delta | Rel Delta | Tolerance |
|---|---|---:|---:|---:|---:|---|
| MISES_MAX | FAIL | 0.6 | 1.07003 | 0.470027 | 0.783379 | rtol=0.2, atol=0.01 |
| U_tip | FAIL | -0.002 | -1.08433e-05 | 0.00198916 | 0.994578 | rtol=0.1, atol=1e-06 |

## Verification Boundary

This report does not rerun Abaqus. It extends an already captured `require-real` smoke bundle by checking its extracted ODB KPI values against Physics Contracts and expected KPI baselines.
