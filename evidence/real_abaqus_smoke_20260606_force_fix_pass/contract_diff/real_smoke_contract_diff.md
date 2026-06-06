# Abaqus Agent Real Smoke Contract/Diff Report

## Verdict Summary

| Area | Status | Detail |
|---|---|---|
| Overall | `PASS` | Real smoke KPI values were checked against contracts and expected KPI baselines. |
| Physics Contracts | `PASS` | 4 pass / 0 warning / 0 fail. |
| Simulation Diff | `PASS` | 2 KPI rows; 0 changed, 0 added, 0 removed. |
| Real Abaqus smoke | `verified` | Source smoke status: `real-env-verified`. |

## Run Metadata

- Project: `abaqus-agent`
- Workflow: `real-smoke-contract-diff`
- Case: `cantilever`
- Run ID: `cantilever-require-real-contract-diff`
- Generated at: `2026-06-06T02:42:29Z`
- Real environment required: `true`
- Real environment verified: `true`

## Real Smoke Source

- Smoke evidence: `D:\code\abaqus_agent_force_fix_evidence\smoke_20260606_force_fix_pass\smoke_evidence.json`
- KPI result: `D:\code\abaqus_agent_force_fix_evidence\smoke_20260606_force_fix_pass\run\_kpi_result.json`
- ODB artifact: `D:\code\abaqus_agent_force_fix_evidence\smoke_20260606_force_fix_pass\run\Cantilever.odb`
- Source mode: `require-real`

| Stage | Status | Real Verified |
|---|---|---|
| environment_preflight | completed | true |
| input_job_preparation | completed | true |
| syntaxcheck | completed | true |
| submit_job | completed | true |
| monitor_status_collection | completed | true |
| odb_kpi_adapter_probe | completed | true |

## KPI Values

| KPI | Expected Baseline | Real ODB Candidate |
|---|---:|---:|
| MISES_MAX | 0.383091 | 0.383091 |
| U_tip | -0.00257163 | -0.00257163 |

## Physics Contracts

Status: `PASS`

| Contract | Status | Message |
|---|---|---|
| tip deflects downward | PASS | U_tip=-0.0025716267991811037 satisfies < 0.0 |
| tip deflection near reference | PASS | U_tip is within tolerance |
| max stress plausible range | PASS | MISES_MAX=0.38309070467948914 is within range |
| max stress near reference | PASS | MISES_MAX is within tolerance |

## Simulation Diff

# Simulation Diff: KPI

- Status: `PASS`
- Total KPIs: `2`
- Changed: `0`
- Added: `0`
- Removed: `0`

| KPI | Status | Baseline | Candidate | Delta | Rel Delta | Tolerance |
|---|---|---:|---:|---:|---:|---|
| MISES_MAX | PASS | 0.383091 | 0.383091 | 0 | 0 | rtol=0.2, atol=0.01 |
| U_tip | PASS | -0.00257163 | -0.00257163 | 0 | 0 | rtol=0.1, atol=1e-06 |

## Capsule Provenance

- Manifest: `D:\code\abaqus_agent_force_fix_evidence\smoke_20260606_force_fix_pass\contract_diff\capsule\cantilever-require-real-contract-diff\capsule.json`
- Capsule hash: `4213c60b74e769377ebce76f29afd5a372d2c2a90832e86a945b903af0570c20`
- Inputs: `5`
- Artifacts: `12`

## Verification Boundary

This report does not rerun Abaqus. It extends an already captured `require-real` smoke bundle by checking its extracted ODB KPI values against Physics Contracts and expected KPI baselines.
