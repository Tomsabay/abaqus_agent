# CAPABILITY_AUDIT

## Project
abaqus-agent

Latest local checkpoint: `V0.2-FRONTEND-MOBILE-EVIDENCE-SMOKE-001` adds mobile responsive layout hardening for the frontend Evidence workspace and verifies a 390px Demo Pack flow with no document-level horizontal overflow.

## Ticket
README-CAPABILITY-AUDIT-001

Updated by ABAQUS-ENV-VALIDATION-001 with a local environment validation entry.
Updated by REAL-ABAQUS-SMOKE-HARNESS-001 with a real Abaqus smoke/evidence harness.
Updated by EVIDENCE-REPORT-001 with a Markdown renderer for smoke evidence bundles.
Updated by README-VALIDATION-MATRIX-001 to replace mixed-evidence roadmap
checkboxes with a README validation matrix.
Updated by MCP-STDIO-SMOKE-001 with a real MCP stdio client smoke test.
Updated by MCP-BRIDGE-SUBPROCESS-SMOKE-001 with a real HTTP-to-MCP bridge
subprocess smoke test.
Updated by FASTAPI-REST-SSE-SMOKE-001 with local FastAPI REST/SSE endpoint
smoke tests.
Updated by FASTAPI-PREMIUM-API-SMOKE-001 with local premium endpoint smoke
tests and premium feature gate reset around API smoke tests.
Updated by FRONTEND-BROWSER-SMOKE-001 with a local browser smoke test of the
served frontend.
Updated by PRODUCT-POSITIONING-METADATA-001 with Local Simulation QA /
Regression Framework positioning in README and package metadata.
Updated by MCP-BRIDGE-LIFESPAN-DEPRECATION-001 with FastAPI lifespan migration
for the HTTP-to-MCP bridge.
Updated by MCP-BRIDGE-REAL-SSE-SMOKE-001 with real subprocess bridge SSE smoke
over the no-Abaqus simulated pipeline.
Updated by MCP-BRIDGE-PREMIUM-SUBPROCESS-SMOKE-001 with real subprocess
bridge coverage for premium feature status, empty activation failure, and
dev-key activation success.
Updated by MCP-STDIO-PREMIUM-SMOKE-001 with real MCP stdio client coverage for
premium tools and `premium://features` resource.
Updated by MCP-BRIDGE-BENCHMARK-RUN-SUBPROCESS-SMOKE-001 with real
HTTP-to-MCP subprocess coverage for benchmark dry-run trigger.
Updated by MCP-STDIO-BENCHMARK-RUN-SMOKE-001 with real MCP stdio client
coverage for benchmark dry-run trigger.
Updated by FASTAPI-BENCHMARK-RUN-SMOKE-001 with direct REST API coverage for
benchmark dry-run trigger.
Updated by FASTAPI-RUN-START-SSE-SMOKE-001 with direct REST API coverage for
no-Abaqus simulated run start and SSE stream to done.
Updated by TESTCLIENT-HTTPX-WARNING-AUDIT-001 with local audit of the remaining
external Starlette TestClient/httpx fallback warning.
Updated by FRONTEND-SETTINGS-PREMIUM-STATIC-AUDIT-001 with source audit of
Settings/Premium direct API/MCP URL and localStorage paths.
Updated by LLM-PLANNER-PROVIDER-MOCK-SMOKE-001 with local mock tests for
OpenAI/Anthropic adapter plumbing and API-key env override restoration.
Updated by FASTAPI-SERVER-POSITIONING-METADATA-001 after aligning direct
FastAPI app metadata to the Local Simulation QA / evidence positioning.
Updated by PYDANTIC-RUNNER-CFG-DEFAULT-FACTORY-001 after replacing mutable
`runner_cfg` request defaults in direct API and MCP bridge models.
Updated by MCP-BRIDGE-POSITIONING-METADATA-001 after aligning bridge FastAPI
metadata to Local Simulation QA / evidence workflow positioning.
Updated by EXTRACT-KPIS-FAKE-SUBPROCESS-001 with local fake-subprocess tests for
outer `post.extract_kpis.extract_kpis` command construction, spec/result files,
missing executable, timeout, and no-result stderr fallback.
Updated by MONITOR-JOB-FILE-STATE-FIXTURE-001 with public `monitor_job()`
fixture coverage for absent files, `.sta` progress, `.log/.msg` diagnostic
dedupe, completed log plus `.odb`, and failed `.sta` status precedence.
Updated by UPGRADE-ODB-FAKE-SUBPROCESS-001 with local fake-subprocess tests for
outer `post.upgrade_odb.upgrade_odb_if_needed` command construction,
result parsing, missing executable, timeout, no-result stderr fallback, and
inner-script `odbAccess` upgrade-call content.
Updated by EXTRACT-KPIS-INNER-FAKE-ODB-001 with pure-Python fake ODB tests for
common `_extract_single_kpi` calculation branches and missing-field handling.
Updated by EXTRACT-KPIS-LOCATION-ALIAS-001 with benchmark location alias
coverage for `tip_center -> TIP_NODES` and `hole_edge_set -> HOLE_EDGE`.
Updated by LOCAL-VERIFY-AFTER-KPI-ADAPTERS-001 after refreshing editable
install, full-project ruff, full diff whitespace check, dirty worktree status,
and full pytest on the accumulated local changes.
Updated by EXTRACT-KPIS-FIELD-LOCATION-SUBSET-001 with fake ODB coverage for
field KPI `location` subset selection on element and node sets.
Updated by EXTRACT-KPIS-FIELD-VARIABLE-INFERENCE-001 with fake ODB coverage
for `field_max` displacement component inference (`U1/U2/U3` -> `U` field).
Updated by EXTRACT-KPIS-EXPLICIT-LOCATION-ALIASES-001 with explicit-impact
location aliases (`fixed_face`/`top_face`) and `reaction_force_max` subset
coverage.
Updated by LOCAL-VERIFY-AFTER-KPI-MAPPING-FIXES-001 after refreshing
full-project ruff, full diff whitespace check, dirty worktree status, and full
pytest after accumulated KPI mapping/subset/inference fixes.
Updated by README-SAFETY-CLAIM-ALIGNMENT-001 after aligning the README design
principles safety row with the audited static guard enforcement boundary.
Updated by README-SYNTAXCHECK-LICENSE-CLAIM-ALIGNMENT-001 after replacing
README no-license/no-token syntaxcheck wording with a pre-solver gate boundary.
Updated by README-API-SIMULATION-PIPELINE-BOUNDARY-001 after making the README
validation matrix distinguish API/frontend no-Abaqus simulated flow from
7-stage real orchestrator/solver evidence.
Updated by SOURCE-SYNTAXCHECK-LICENSE-COMMENT-ALIGNMENT-001 after aligning
orchestrator/core pipeline syntaxcheck stage text with the pre-solver/license
evidence boundary.
Updated by FRONTEND-SYNTAXCHECK-LICENSE-COPY-ALIGNMENT-001 after aligning
frontend syntaxcheck copy with the pre-solver/license evidence boundary.
Updated by RUN-ID-IDEMPOTENCY-COPY-BOUNDARY-001 after aligning README/frontend
run-id wording with deterministic spec-run IDs and separate benchmark run
records.
Updated by LOCAL-VERIFY-AFTER-CLAIM-BOUNDARY-COPY-001 after refreshing
full-project ruff, full diff whitespace check, dirty worktree status, and full
pytest after accumulated README/frontend/source claim-boundary wording changes.
Updated by NEXT-TICKETS-LICENSE-WORDING-BOUNDARY-001 after aligning the real
Abaqus blocked-branch wording to record actual license behavior and
license-aware minimal-scope evidence.
Updated by README-AUDIT-RECOMMENDED-LICENSE-WORDING-001 after aligning
recommended real-Abaqus next-step wording to license-aware minimal-scope
language.
Updated by CAPABILITY-AUDIT-7STAGE-RISK-WORDING-001 after aligning the
7-stage risk wording with the current README validation matrix and API/UI
simulation boundary.
Updated by CLAIM-BOUNDARY-ACTIVE-SURFACE-SCAN-001 after scanning active
launch/developer surfaces for stale positioning, install, test-count,
license, and idempotency claims.
Updated by FRONTEND-COPY-HTTP-SMOKE-001 after verifying the served frontend
HTML includes updated syntaxcheck/run-id copy and omits stale claim-boundary
copy.
Updated by SCHEMA-ENV-FOCUSED-REFRESH-001 after refreshing focused schema and
local environment validator tests without writing benchmark report artifacts.
Updated by API-MCP-FOCUSED-SMOKE-REFRESH-001 after refreshing focused direct
FastAPI, MCP stdio, and HTTP-to-MCP bridge subprocess smoke tests.
Updated by RUNNER-KPI-FOCUSED-SMOKE-REFRESH-001 after refreshing focused
syntaxcheck, submit_job, monitor_job, KPI outer-subprocess, and fake-ODB KPI
tests.
Updated by BUILD-COMPARE-REPORT-FOCUSED-REFRESH-001 after refreshing focused
build_model custom input/handoff, compare_expected, and benchmark report
fixture tests.
Updated by SOLVER-DOCTOR-LOG-EVIDENCE-001 with deterministic JSON/Markdown
Solver Doctor reports over existing `.msg/.dat/.sta/.log` artifacts and local
fixture coverage for common diagnostic categories.
Updated by PHYSICS-CONTRACT-EVALUATOR-001 with a pure-Python Physics Contract
evaluator over KPI dictionaries and local unit coverage for range, direction,
relative-error, ordering, warning severity, and structured failure paths.
Updated by EXPERIMENT-CAPSULE-STORE-001 with a minimal local capsule store that
copies inputs/artifacts and writes a hashed `capsule.json` manifest.
Updated by SIMULATION-DIFF-KPI-EVIDENCE-001 with deterministic KPI dictionary
diffing and Markdown rendering.
Updated by SMOKE-HARNESS-CAPSULE-ARTIFACT-001 after integrating capsule
manifest creation into the smoke/evidence harness for case inputs and stage
artifacts.
Updated by PHYSICS-CONTRACT-IO-001 with JSON/YAML contract loading and legacy
`expected.json` KPI tolerance conversion.
Updated by BENCHMARK-CONTRACT-REPORT-001 after benchmark Markdown reports
gained a Physics Contracts section for supplied contract evaluation results.
Updated by RUN-CASE-CONTRACT-EVALUATION-001 after benchmark case execution
started attaching Physics Contract results from expected/contract files when KPI
values are available.
Updated by V0.2-OFFLINE-EVIDENCE-SLICE-001 after adding a runnable offline
evidence slice that produces `evidence.json`, `evidence.md`, and a capsule from
supplied KPI JSON plus Physics Contracts and Simulation Diff.
Updated by V0.2-OFFLINE-EVIDENCE-API-001 after extracting the offline evidence
service and exposing it through `POST /api/evidence/offline`.
Updated by V0.2-OFFLINE-EVIDENCE-FRONTEND-001 after adding a browser Evidence
workspace and verifying it with Chrome UI smoke.
Updated by V0.2-REPORT-POLISH-001 after turning offline `evidence.md` into a
clearer verdict/metadata/provenance report and verifying it through CLI/API/UI.
Updated by V0.2-OFFLINE-EVIDENCE-MCP-PARITY-001 after exposing offline evidence
through MCP stdio and the HTTP-to-MCP bridge.
Updated by V0.2-CAPSULE-RUN-LIFECYCLE-001 after standardizing capsule evidence
metadata across offline evidence and smoke harness outputs.
Updated by V0.2-EVIDENCE-ARTIFACT-SURFACE-001 after adding Direct API and MCP
bridge artifact retrieval URLs for generated offline evidence deliverables.
Updated by V0.2-EVIDENCE-BUNDLE-ZIP-001 after adding Direct API and MCP bridge
ZIP bundle retrieval for offline evidence deliverables.
Updated by V0.2-SIMULATION-DIFF-API-FRONTEND-001 after exposing standalone
Simulation Diff through Direct API, MCP bridge, MCP stdio, frontend, vault, and
Case Memory surfaces.
Updated by V0.2-SOLVER-DOCTOR-PATTERN-GALLERY-001 after exposing Solver Doctor
diagnostic categories and parser patterns through Direct API, MCP bridge, MCP
stdio, and frontend surfaces.
Updated by V0.2-EVIDENCE-RUN-HISTORY-001 after adding Direct API and MCP bridge
recent evidence artifact listing plus frontend recent Evidence run links.
Updated by V0.2-EVIDENCE-EXAMPLE-GALLERY-001 after adding multi-case offline
evidence KPI fixtures and frontend case selector support.
Updated by V0.2-EVIDENCE-EXAMPLES-API-001 after exposing the offline evidence
example gallery through Direct API and MCP bridge endpoints.
Updated by V0.2-EVIDENCE-EXAMPLES-MCP-RESOURCE-001 after exposing the offline
evidence example gallery through MCP stdio resource/tool.
Updated by V0.2-OFFLINE-DEMO-GALLERY-CLI-001 after adding a one-command offline
demo gallery CLI with top-level index and per-case bundles.
Updated by V0.2-OFFLINE-DEMO-GALLERY-API-001 after exposing the demo gallery
through Direct API, MCP bridge, frontend action, and top-level downloadable ZIP.
Updated by V0.2-SOLVER-DOCTOR-API-FRONTEND-001 after exposing deterministic
Solver Doctor log-text diagnosis through Direct API, MCP bridge, and frontend.
Updated by V0.2-SOLVER-DOCTOR-MCP-STDIO-001 after exposing deterministic
Solver Doctor log-text diagnosis through MCP stdio.
Updated by V0.2-LOCAL-EVIDENCE-VAULT-001 after adding configurable local vault
storage plus Direct API/MCP bridge list/download endpoints for generated
offline evidence, demo gallery, and Solver Doctor deliverables.
Updated by V0.2-EVIDENCE-VAULT-FRONTEND-001 after surfacing local evidence
vault refresh/list/download links in the frontend Evidence workspace.
Updated by V0.2-ONE-COMMAND-LOCAL-DEMO-PACK-001 after adding a one-command
local demo pack CLI combining Offline Demo Gallery and Solver Doctor sample
evidence.
Updated by V0.2-LOCAL-DEMO-PACK-API-FRONTEND-001 after exposing local demo pack
generation through Direct API, MCP bridge, frontend action, and vault ZIP
download.
Updated by V0.2-DEMO-PACK-MCP-STDIO-001 after exposing local demo pack
generation through MCP stdio `create_local_demo_pack_tool`.
Updated by V0.2-LOCAL-DEMO-PACK-HTML-REPORT-001 after adding a self-contained
`index.html` demo pack overview across CLI/API/MCP/frontend/ZIP surfaces.
Updated by V0.2-CASE-MEMORY-VAULT-SEARCH-001 after adding local vault-backed
Case Memory search across Direct API, MCP bridge, MCP stdio, and frontend.
Updated by V0.2-KPI-RECIPE-GALLERY-001 after exposing ODB Lens KPI extraction
recipes across Direct API, MCP bridge, MCP stdio, and frontend.
Updated by V0.2-DEMO-GALLERY-HTML-CASE-REPORTS-001 after carrying per-case
`evidence.html` reports into Offline Demo Gallery case bundles and top-level
gallery ZIP output.

## Date
2026-06-03

## Baseline Used
- Project identity confirmed: `docs/goal_driver/PROJECT_ID.md` says `abaqus-agent`.
- Python runtime verified: `python3.11 --version` -> Python 3.11.15.
- Install verified in `/tmp/abaqus-agent-audit-venv`: `pip install -e ".[dev]"` passed and installed `mcp-1.27.2`.
- Package metadata / CLI verified: metadata name `abaqus-agent`; console script `abaqus-agent -> server:main`.
- Default tests verified: `pytest tests/ -v` -> 197 passed, 5 warnings.
- Benchmark dry-run verified: 4/4 cases `DRY_RUN_PASS`.
- Local environment validation entry added: `python scripts/validate_abaqus_env.py --dry-run`, `--json --dry-run`, and `--require-real`.
- Validation entry reports stable JSON fields: capability name, status, evidence, real-env requirement/verification, and missing reason.
- Real Abaqus smoke/evidence harness added: `python scripts/run_real_abaqus_smoke.py --dry-run|--mock-real|--require-real --json --out-dir <dir>`.
- Smoke harness evidence bundle includes `smoke_evidence.json`, per-stage `stage_*.json`, and `missing_report.json` when `--require-real` fails preflight.
- Smoke evidence Markdown renderer added: `python scripts/render_smoke_evidence_report.py <out-dir>/smoke_evidence.json --out <out-dir>/smoke_evidence.md`.
- Smoke harness dry-run and mock-real paths exercise reproducible evidence plumbing but do not mark real Abaqus stages as verified.
- README roadmap checkboxes were replaced with a validation matrix that separates
  command-verified, test-covered, dry-run/mock-real, source-supported, and
  environment-limited capabilities.
- MCP stdio server integration is now verified by a real client smoke test that
  starts `mcp_server.py` as a subprocess and exercises initialize/list tools/call
  tool/list resources/read resource over stdio.
- HTTP-to-MCP bridge subprocess integration is now verified by a FastAPI
  TestClient smoke test that routes health, spec validation, and benchmark
  resource requests through a real `mcp_server.py` subprocess.
- HTTP-to-MCP bridge SSE over a real subprocess is now verified for the
  no-Abaqus simulated pipeline by starting a run and consuming
  `/mcp/api/run/{run_id}/stream` until `done`.
- FastAPI REST/SSE endpoints are now verified by TestClient smoke tests for
  `/health`, `/api/spec/generate`, `/api/spec/validate`, `/api/benchmark`, and
  `/api/run/{run_id}/stream` using a preloaded completed run.
- FastAPI premium endpoints are now verified by TestClient smoke tests for
  `/api/premium/features`, empty activation failure, and dev-key activation
  success.
- Frontend browser smoke verified local page load, visible API/simulation status,
  spec generation/validation, benchmark table load, benchmark dry-run PASS
  updates, and absence of browser console errors during the checked flow.
- Latest full pytest after local runner/evidence hardening, offline evidence
  API/MCP/UI work, capsule metadata standardization, example gallery fixtures,
  MCP examples resource, offline demo gallery CLI, custom `.inp` deck evidence
  example, Case Memory vault diff, and accumulated
  verification:
  320 passed, 1 warning.
- Real Abaqus executable/license/syntaxcheck/solver execution was not run.

## Evidence Categories
- `Verified by command`: this ticket or recent baseline ran a command and it passed.
- `Covered by tests`: tests cover the behavior and full pytest passed.
- `Supported by source`: source entry point or implementation exists, but integration/runtime was not executed.
- `Dry-run only`: only no-Abaqus validation/dry-run passed.
- `Environment-limited`: requires Abaqus executable/license/ODB or external client/environment.
- `Available`: a visible real-environment prerequisite was found, such as an Abaqus executable path.
- `Candidate`: enough visible prerequisites exist to attempt a real command later, but the command was not run by the validator.
- `Documentation-only / Unverified`: README/config claim exists but no local command/test/source proof was established in this audit.
- `Mismatch / Risk`: README wording overstates or differs from verified evidence.

## Local Abaqus Environment Validation Entry

Run these commands from the repository root:

```bash
python scripts/validate_abaqus_env.py --dry-run
python scripts/validate_abaqus_env.py --json --dry-run
python scripts/validate_abaqus_env.py --require-real
```

Expected behavior without real Abaqus on the current machine:
- default and `--dry-run` modes exit 0 and clearly report local import/entry/dry-run readiness.
- `--require-real` exits non-zero and lists missing prerequisites, including the Abaqus executable and license hint.
- `real_abaqus_e2e_pipeline` remains `environment-limited` because the validator does not run CAE noGUI, syntaxcheck, solver submit/monitor, ODB KPI extraction, or compare_expected.

Environment variables recognized as explicit hints:
- Abaqus executable: `ABAQUS_EXECUTABLE`, `ABAQUS_COMMAND`, `ABAQUS_PATH`, or `abaqus` on `PATH`.
- License hint: `LM_LICENSE_FILE`, `ABAQUSLM_LICENSE_FILE`, `ABAQUS_LICENSE_FILE`, `DSLS_CONFIG`, or `ABAQUS_AGENT_LICENSE_CONFIRMED=1`.

These hints make a machine a candidate for real validation; they are not solver or license-checkout evidence by themselves.

## Real Abaqus Smoke/Evidence Harness

Run these commands from the repository root:

```bash
python scripts/run_real_abaqus_smoke.py --dry-run --json --out-dir /tmp/abaqus-agent-smoke
python scripts/run_real_abaqus_smoke.py --mock-real --json --out-dir /tmp/abaqus-agent-mock-smoke
python scripts/run_real_abaqus_smoke.py --require-real --json --out-dir /tmp/abaqus-agent-real-smoke
```

Expected behavior without real Abaqus on the current machine:
- `--dry-run` exits 0, writes pipeline stage/command evidence, and keeps `real_env_verified=false`.
- `--mock-real` exits 0 with a fake Abaqus executable/files, exercises syntaxcheck/submit/monitor code paths, and keeps ODB KPI `environment-limited` because no real `odbAccess` reader is used.
- `--require-real` exits 2 and writes `missing_report.json` when executable/license/prerequisites are absent.

The harness covers these stages: environment preflight, input/job preparation,
syntaxcheck command/path, submit command/path, monitor/status collection, ODB
KPI adapter/probe, and evidence/report generation. It reuses
`scripts.validate_abaqus_env.collect_report`, `runner.build_model.build_model`,
`runner.syntaxcheck.syntaxcheck_inp`, `runner.submit_job._build_cmd`,
`runner.submit_job.submit_job`, `runner.monitor_job.monitor_job`, and
`post.extract_kpis.extract_kpis`.

This changes Environment-limited items by giving them a repeatable smoke/evidence
path. It does not convert syntaxcheck, submit/monitor, ODB KPI extraction, or the
7-stage real pipeline to `Verified by command` unless the harness is run against
a real Abaqus executable/license and records `real_env_verified=true` for the
actual stages.

## Smoke Evidence Markdown Report

Render an existing evidence bundle into a human-readable handoff report:

```bash
python scripts/render_smoke_evidence_report.py /tmp/abaqus-agent-smoke/smoke_evidence.json \
  --out /tmp/abaqus-agent-smoke/smoke_evidence.md
```

The report includes mode, case, overall status, `real_env_verified`, missing
prerequisites, a per-stage summary table, commands, artifact paths, and evidence
lines. It is a rendering step only: it does not run Abaqus and does not convert
dry-run, mock-real, missing-prerequisite, or environment-limited evidence into
real Abaqus verification.

## Capability Matrix

Latest addendum:
- Evidence Vault now supports `query` text search plus `kind` / `status` filtering in `evidence.vault.list_vault_entries()`, Direct API `/api/evidence/vault`, MCP bridge `/mcp/api/evidence/vault`, and the frontend Evidence Vault panel.
- Browser smoke on `127.0.0.1:8035` verified `query=local-demo-pack.zip` isolates the pack row and `query=case-memory-diff&kind=case-memory-diff&status=FAIL` isolates the diff row with no browser console errors.
- Evidence Vault detail endpoints `/api/evidence/vault/{vault_id}` and `/mcp/api/evidence/vault/{vault_id}` return one record with `vault_urls`; frontend rows expose `详情` and render summary/files. Browser smoke on `127.0.0.1:8036` verified a searched demo pack opens detail containing `overall_status=PASS` and `local-demo-pack.zip`.
- MCP stdio now exposes `evidence-vault://entries`, `search_evidence_vault_tool`, and `get_evidence_vault_record_tool`; direct MCP tests and real stdio client smoke passed.
- MCP stdio `read_evidence_vault_file_tool` now reads safe text vault artifacts with truncation metadata and rejects unsupported ZIP/unsafe filenames with structured errors; direct MCP tests and real stdio client smoke passed.
- `scripts/inspect_evidence_vault.py` now exposes no-server `list`, `detail`, safe text `read`, and artifact `copy` subcommands. `list` supports `query` / `kind` / `status` / `limit`; `read` returns content, size, and truncation metadata for `.json` / `.md` / `.html` and rejects unsupported ZIP reads with structured JSON errors; `copy` exports text or binary vault artifacts such as ZIP bundles to a chosen local path through the same vault file validation.
- `scripts/inspect_case_memory.py` now exposes no-server `search`, `detail`, and `diff` subcommands. `search` supports `query` / `kind` / `status` / `limit`; `diff` compares two vault entries with optional safe nested `evidence.json` / `diff.json` filenames and writes local `diff.json` / `diff.md` without invoking Abaqus.
- `scripts/inspect_kpi_recipes.py` now exposes no-server `list`, `detail`, and `export` subcommands. `list` supports `case` / `kpi-type`; `export` writes the recipe `kpi_spec` JSON list and returns an Abaqus Python command hint plus no-real-ODB boundary metadata.
- `scripts/inspect_solver_doctor_patterns.py` now exposes no-server `list` and `detail` subcommands. `list` supports `category` / `severity`; `detail` returns one stable pattern id with source file, regex pattern, explanation, recommendation, severity, and no-real-env boundary.
- `scripts/run_local_cli_smoke.py` now exercises Evidence Vault list/detail/read/copy, Case Memory search/detail/nested diff, KPI Recipe list/export, and Solver Doctor Pattern list/detail through real subprocess calls, then writes `local_cli_smoke.json` / `local_cli_smoke.md` with per-step command/status evidence.
- The local CLI smoke report now creates a `local-cli-smoke` vault entry containing `local_cli_smoke.json` and `local_cli_smoke.md`; focused tests verify the smoke entry is discoverable through Evidence Vault and Case Memory inspect CLIs.
- Local CLI smoke now also writes `local_cli_smoke.html` and persists it in the `local-cli-smoke` vault entry; focused tests verify the HTML includes overall smoke evidence, step table, smoke vault id, and no-real-Abaqus boundary.
- `pyproject.toml` now exposes `abaqus-agent-local-cli-smoke`, `abaqus-agent-verify-local-cli-smoke`, `abaqus-agent-vault`, `abaqus-agent-case-memory`, `abaqus-agent-kpi-recipes`, and `abaqus-agent-doctor-patterns`; `scripts/__init__.py` makes the script modules importable as package entry point targets.
- Editable install smoke passed with `/tmp/abaqus-agent-audit-venv/bin/python -m pip install -e ".[dev]"`; all five new no-server console commands returned `--help`; `abaqus-agent-kpi-recipes list --case modal --kpi-type eigenfrequency` returned JSON with `workflow=kpi-recipe-gallery` and `total=1`.
- Installed smoke command passed: `/tmp/abaqus-agent-audit-venv/bin/abaqus-agent-local-cli-smoke --out-dir /tmp/abaqus-agent-installed-cli-smoke-manifest --json` exited 0, returned `workflow=local-cli-smoke`, `overall_status=PASS`, 11 PASS steps, manifest path, ZIP path, and a `local-cli-smoke-*` smoke vault id. Artifact probe verified JSON/Markdown/HTML/manifest/ZIP outputs, ZIP members including `copied-local-demo-pack.zip` and `local_cli_smoke_manifest.json`, and manifest size/SHA-256 entries matching disk files.
- `RELEASE_INSTRUCTIONS.md` now includes the installed no-server CLI smoke in Local Verification, release highlights, verified audit evidence, install command examples, and an explicit boundary that the smoke is not real Abaqus execution proof.
- MCP stdio now exposes `run_local_cli_smoke_tool(out_dir="")`, returning workflow/status, step summaries, vault ids, report paths, Markdown, and HTML. Direct MCP tests and real stdio client smoke passed.
- HTTP-to-MCP bridge now exposes `POST /mcp/api/evidence/local-cli-smoke`, which calls MCP stdio `run_local_cli_smoke_tool` through `MCPConnection`; real bridge subprocess smoke passed.
- Direct API now exposes `POST /api/evidence/local-cli-smoke`, calling the same local CLI smoke collector with the server Evidence Vault root; focused TestClient smoke verifies PASS status, 10 PASS steps, generated JSON/Markdown/HTML paths/content, and Vault/Case Memory discoverability.
- Direct API local CLI smoke now returns `smoke_vault_urls` for JSON/Markdown/HTML reports; frontend Evidence workspace exposes `运行 CLI Smoke`, renders PASS/step/vault/report-link details, and adds `local-cli-smoke` to Vault/Case Memory filters and row links. Static frontend parse/source probe passed, and local HTTP probe against `127.0.0.1:8037` returned `local-cli-smoke PASS 10` with smoke vault report URLs. Browser automation was not completed because Playwright/browser tooling was unavailable in the current tool environment.
- Local CLI smoke now also writes `local_cli_smoke.zip`, containing JSON/Markdown/HTML reports, and persists it in the `local-cli-smoke` vault entry. Direct API smoke URLs and frontend Evidence/Vault/Case Memory rows expose the ZIP as a downloadable portable report bundle.
- MCP stdio `run_local_cli_smoke_tool` now returns `zip_path` and `smoke_vault_files`, and direct MCP, real MCP stdio, and HTTP-to-MCP bridge subprocess tests verify `local_cli_smoke.zip` exists and contains the JSON/Markdown/HTML reports.
- Evidence Vault no-server CLI `copy` command now exports vault artifacts such as ZIP bundles to a chosen local path; focused CLI tests verify ZIP export while `read` still rejects ZIP as text.
- Local CLI smoke now includes an `evidence-vault-copy` step that exports `local-demo-pack.zip` from the generated vault; CLI/API/MCP surfaces now report 11 PASS steps for the no-server product smoke.
- MCP stdio now exposes `copy_evidence_vault_file_tool`, allowing agent clients to export text or binary vault artifacts to a requested local path without shelling out. Direct MCP and real stdio tests verify artifact copy/export metadata and output files.
- `local_cli_smoke.zip` is now self-contained: it includes JSON/Markdown/HTML smoke reports plus the copied `local-demo-pack.zip` artifact. Local/API/MCP focused tests verify the bundled member list.
- Local CLI smoke now writes `local_cli_smoke_manifest.json` with `filename`, `size_bytes`, and `sha256` for the bundled smoke reports and copied demo pack ZIP; the manifest is included in `local_cli_smoke.zip` and persisted in the `local-cli-smoke` vault entry. Local/API/MCP focused tests verify ZIP membership and checksum fields.
- `scripts/verify_local_cli_smoke_bundle.py` and installed `abaqus-agent-verify-local-cli-smoke` verify a local CLI smoke ZIP against its embedded manifest without extraction. Focused tests verify PASS on a generated bundle and FAIL on a tampered Markdown member; installed CLI probe against `/tmp/abaqus-agent-installed-cli-smoke-manifest/local_cli_smoke.zip` returned PASS with 4 checked files.
- MCP stdio now exposes `verify_local_cli_smoke_bundle_tool`, allowing agent clients to verify a local CLI smoke ZIP path through MCP without shelling out. Direct MCP and real stdio client smoke verify PASS after generating a smoke ZIP through `run_local_cli_smoke_tool`.
- Evidence Vault no-server CLI now exposes `verify-smoke <vault_id>`, resolving `local_cli_smoke.zip` through existing vault path validation and verifying it against the embedded manifest. Focused local smoke/vault tests and installed `abaqus-agent-vault --root ... verify-smoke ...` probe passed.
- MCP stdio now exposes `verify_evidence_vault_smoke_bundle_tool`, resolving `local_cli_smoke.zip` through existing vault path validation with optional `vault_root`. Direct MCP and real stdio client smoke verify PASS after generating a local CLI smoke vault entry.
- HTTP-to-MCP bridge now exposes `POST /mcp/api/evidence/vault/{vault_id}/verify-smoke`, calling the MCP stdio vault verifier. Real bridge subprocess smoke verifies PASS after `POST /mcp/api/evidence/local-cli-smoke`.
- Direct API now exposes `POST /api/evidence/vault/{vault_id}/verify-smoke`, resolving `local_cli_smoke.zip` through the server Evidence Vault root and verifying it against the embedded manifest. Focused TestClient smoke verifies PASS after `POST /api/evidence/local-cli-smoke`.
- Frontend Evidence workspace now calls Direct API `verify-smoke` after `运行 CLI Smoke` succeeds and renders ZIP verification status, checked file count, and per-file manifest status. Static source/JS syntax probe passed; browser automation was not available in the current tool environment.
- Frontend Evidence Vault rows for `local-cli-smoke` now render a `VERIFY` action that calls Direct API `verify-smoke` and displays PASS/FAIL plus checked manifest file data in the vault detail panel. Static source/JS syntax probe passed; browser automation remained unavailable.
- Local demo pack ZIPs now include `local-demo-pack-manifest.json`, with size/SHA-256 entries for bundled demo artifacts. Focused local/API/MCP direct/MCP stdio/real bridge tests verify manifest membership plus recomputed sample hashes, and an actual CLI probe generated `/tmp/abaqus-agent-local-demo-pack-manifest` with PASS status and 31 manifest entries.
- Local demo pack ZIPs can now be verified independently with `scripts/verify_local_demo_pack_bundle.py` or installed `abaqus-agent-verify-local-demo-pack`. Focused tests cover valid ZIP, missing manifest/member, size mismatch, SHA mismatch, unsafe manifest filenames, invalid ZIP, and missing path; installed CLI probe returned PASS with 31 checked files.
- MCP stdio now exposes `verify_local_demo_pack_bundle_tool`, allowing agent clients to verify a received local demo pack ZIP path without shelling out. Direct MCP and real stdio client smoke verify PASS after generating a local demo pack through `create_local_demo_pack_tool`.
- Evidence Vault CLI now exposes `verify-demo-pack <vault_id>`, resolving `local-demo-pack.zip` through the existing vault path boundary and verifying it against the embedded manifest. Focused vault CLI tests cover PASS plus invalid stored ZIP failure, and installed `abaqus-agent-vault` probe returned PASS with 31 checked files.
- MCP stdio now exposes `verify_evidence_vault_demo_pack_bundle_tool`, resolving vault-stored `local-demo-pack.zip` by vault id/root through existing vault validation. Direct MCP and real stdio tests verify PASS after creating a stored local demo pack vault entry.
- HTTP-to-MCP bridge now exposes `POST /mcp/api/evidence/vault/{vault_id}/verify-demo-pack`, calling the MCP stdio vault demo pack verifier. Real bridge subprocess smoke verifies PASS after `POST /mcp/api/evidence/demo-pack`.
- Direct API now exposes `POST /api/evidence/vault/{vault_id}/verify-demo-pack`, resolving `local-demo-pack.zip` through the server Evidence Vault root and verifying it against the embedded manifest. Focused TestClient smoke verifies PASS after `POST /api/evidence/demo-pack`.
- Frontend Evidence Vault rows for `local-demo-pack` now render a `VERIFY` action that calls Direct API `verify-demo-pack` and displays PASS/FAIL plus checked manifest file data in the vault detail panel. Static source/JS syntax probe passed; browser automation remained unavailable.
- Local CLI smoke ZIP verification now deep-checks nested `copied-local-demo-pack.zip` against its embedded demo pack manifest. Focused tests include a nested tamper case where the outer smoke manifest is updated to match the modified copied ZIP but the nested demo pack manifest check fails.
- Frontend local CLI smoke results now display nested `copied_demo_pack_verification` status/count when Direct API smoke ZIP verification returns it. Static source/JS syntax probe passed; browser automation remained unavailable.
- Direct API, MCP stdio, vault MCP stdio, and HTTP-to-MCP bridge smoke verification tests now explicitly assert nested `copied_demo_pack_verification` PASS with 31 checked demo pack files.
- Frontend Evidence Vault row verification detail now summarizes nested `copied_demo_pack_verification` for existing `local-cli-smoke` vault rows, so stored smoke ZIP verification shows both outer smoke ZIP status and inner copied demo pack status/count. Static source/JS syntax probe passed; browser automation remained unavailable.
- Frontend static contract tests now include `tests/test_frontend_static_contracts.py`, locking the nested Evidence Vault smoke verification detail markers and immediate local CLI smoke nested verification line into pytest. Focused frontend static contract tests passed with 2 passed.
- Latest full verification after this addendum: `git diff --check` passed, full `ruff check .` passed, and full pytest passed with `355 passed, 1 warning`.

| Capability | README claim | Current evidence | Trust status | Risk | Recommended next step |
|---|---|---|---|---|---|
| Local Abaqus environment validator | README now documents `scripts/validate_abaqus_env.py` for checking real-validation prerequisites. | `scripts/validate_abaqus_env.py` exists; `tests/test_validate_abaqus_env.py` covers no-Abaqus default, no-Abaqus `--require-real`, simulated executable, executable plus license hint, and parseable JSON. | Verified by command for focused tests; Dry-run only for local readiness; Environment-limited for real execution. | Validator checks prerequisites only. It does not prove license checkout, syntaxcheck, submit/monitor, ODB KPI, or full e2e. | Run this command on a machine with Abaqus installed, then run a separate real command ticket for syntaxcheck/solver/KPI evidence. |
| Real Abaqus smoke/evidence harness | README now documents `scripts/run_real_abaqus_smoke.py` for stage evidence around the real Abaqus pipeline. | Harness supports `--dry-run`, `--mock-real`, `--require-real`, `--json`, and `--out-dir`; tests cover dry-run JSON/evidence plus capsule manifest, missing `--require-real` plus missing-report capsule artifact, fake syntaxcheck/submit/monitor, ODB KPI remaining environment-limited, and standardized capsule metadata (`workflow=real-abaqus-smoke-harness`, `evidence_source=smoke-harness:<mode>`, mode/status-derived `evidence_level`, and real-env flags). CLI dry-run probe wrote a `cantilever-dry-run` capsule with case inputs and stage artifacts. | Verified by command for focused tests and dry-run CLI; Dry-run/mock-real only locally; Environment-limited for actual Abaqus runtime. | Mock-real and capsule creation prove harness/artifact plumbing, not Abaqus license checkout, solver correctness, real ODB KPI extraction, or artifact physical validity. | Run `--require-real` on the Abaqus machine and preserve the evidence bundle/capsule when stages become real-env verified. |
| Smoke evidence Markdown report | README now documents rendering `smoke_evidence.json` into a Markdown handoff report. | `scripts/render_smoke_evidence_report.py` exists; `tests/test_render_smoke_evidence_report.py` covers dry-run boundary text, CLI output, missing evidence, and invalid schema; dry-run bundle rendered to `/tmp/abaqus-agent-report-smoke/smoke_evidence.md`. | Verified by command for focused tests and local render command. | It is a presentation/reporting layer only; it must not be read as new solver evidence. | Use it for future dry-run/mock-real/require-real handoffs and attach real-env reports only after real stages verify. |
| Offline v0.2 evidence slice | README Quick Start starts with a runnable offline Simulation QA evidence command and documents Direct API plus MCP bridge endpoints; frontend now has an Evidence workspace with artifact links, recent runs, an API-backed multi-case example selector, a one-click Demo Gallery action, a one-click Demo Pack action, and an Evidence Vault list. | `evidence/offline.py` combines supplied baseline/candidate KPI JSON, `contracts.io`/`contracts.evaluator`, `simdiff.kpi_diff`, Markdown/HTML rendering, and `capsule.store.create_capsule`. `evidence/demo_gallery.py` runs all public examples and builds a top-level `offline-demo-gallery.zip`. `evidence/vault.py` persists generated offline evidence, demo gallery, local demo pack, Solver Doctor, and Simulation Diff deliverables into `ABAQUS_AGENT_EVIDENCE_VAULT` or `~/.abaqus-agent/evidence-vault`; Direct API and MCP bridge expose `/api/evidence/vault` and `/mcp/api/evidence/vault` list/download endpoints; frontend `Evidence Vault` section refreshes/list entries and renders MD/ZIP/JSON links. `scripts/run_offline_evidence_slice.py` is a CLI wrapper, `scripts/run_offline_demo_gallery.py` is a one-command demo runner over all public examples, and `scripts/run_local_demo_pack.py` creates a one-command local product demo folder/ZIP/HTML overview combining Offline Demo Gallery, Solver Doctor sample evidence, and standalone Simulation Diff sample evidence. `POST /api/evidence/offline` and MCP stdio `run_offline_evidence_tool` expose the single-case workflow; `POST /mcp/api/evidence/offline` exposes it through the HTTP-to-MCP bridge; `frontend/index.html` exposes it as a browser workspace using the active transport base. `POST /api/evidence/demo-gallery` and `POST /mcp/api/evidence/demo-gallery` return a four-case PASS/FAIL summary plus downloadable `index.json`, `index.md`, and `offline-demo-gallery.zip` URLs. `POST /api/evidence/demo-pack`, `POST /mcp/api/evidence/demo-pack`, and MCP stdio `create_local_demo_pack_tool` generate the combined local demo pack, return index Markdown/HTML, and expose `index.html` plus `local-demo-pack.zip` by vault URL or local path; the pack ZIP includes `simulation-diff/diff.json` and `simulation-diff/diff.md` alongside gallery and doctor artifacts. Example inputs live under `examples/kpis/`, `examples/contracts/`, and `examples/inp/`, now covering cantilever, plate-hole, modal, explicit-impact public cases, and `custom_inp_deck` for packaging a supplied `.inp` deck into capsule/report evidence. `evidence/examples.py` powers `/api/evidence/examples`, `/api/evidence/examples/{case}`, bridge equivalents, MCP stdio `evidence://examples`, and `get_offline_evidence_example_tool`; focused tests, real stdio smoke, and HTTP probe verify list/per-case payloads including the custom `.inp` deck example. CLI/API/MCP probes with the cantilever examples produced `overall_status=PASS`, `contracts.status=PASS`, `diff.status=PASS`, polished `evidence.md`, `evidence.html`, and capsule manifests with `workflow=offline-evidence-slice`, `evidence_source=supplied-kpi-json`, `evidence_level=offline`, and real-env flags. Direct API and MCP bridge responses now include `artifact_id` plus artifact URLs for `evidence.json`, `evidence.md`, `evidence.html`, `capsule.json`, and `bundle.zip`; tests retrieve those URLs and assert JSON/Markdown/HTML/capsule/ZIP content. ZIP bundles contain `evidence.json`, `evidence.md`, `evidence.html`, `capsule.json`, and `bundle_manifest.json`. Direct API and MCP bridge recent-list endpoints return run id, artifact id, sequence, generated time, status, contract/diff summaries, capsule summary, and artifact URLs; tests verify latest-first ordering. Gallery tests run all four public examples through the full offline evidence workflow; actual plate-hole CLI probe passed with PASS verdict and capsule manifest. Actual custom `.inp` CLI probe generated `/tmp/abaqus-agent-custom-inp-evidence` with PASS verdict and capsule input `custom_cantilever.inp`; actual custom `.inp` HTTP probe on `127.0.0.1:8014` loaded `custom_inp_deck`, posted offline evidence, and downloaded a capsule artifact containing `custom_cantilever.inp` plus request metadata. Actual offline evidence HTML HTTP probe on `127.0.0.1:8017` posted `/api/evidence/offline`, downloaded `evidence.html` as `text/html`, verified the no-real-Abaqus boundary text, confirmed `bundle.zip` includes `evidence.html`, and downloaded vault `evidence.html`. Actual demo gallery CLI probe generated `/tmp/abaqus-agent-demo-gallery` with four per-case bundles and top-level `index.json` / `index.md`; actual local demo pack CLI probe generated `/tmp/abaqus-agent-local-demo-pack` with `overall_status=PASS`, 4 gallery cases, Solver Doctor `FAILED` sample, Simulation Diff `FAIL` sample, and `local-demo-pack.zip`; actual demo pack HTTP probes on `127.0.0.1:8007` and `127.0.0.1:8008` generated PASS, 4 gallery cases, Solver Doctor `FAILED` sample, downloaded `index.html` as `text/html`, and inspected ZIP files including `index.html`; real MCP stdio smoke generated the same demo pack through `create_local_demo_pack_tool` and inspected expected ZIP members; actual demo gallery HTTP probe on `127.0.0.1:8004` generated a PASS gallery and downloaded a ZIP containing `gallery_manifest.json`, `index.json`, `index.md`, and checked case artifacts. Actual vault HTTP probe on `127.0.0.1:8006` wrote a Solver Doctor report to `/tmp/abaqus-agent-http-vault`, downloaded `doctor.md`, and listed the `solver-doctor` entry. Static frontend probe confirmed Evidence Vault and Demo Pack UI strings, HTML/ZIP link rendering, refresh/action calls, and MD/ZIP/JSON link rendering hooks. Actual HTTP probes on `127.0.0.1:8003` posted offline evidence, retrieved artifacts, inspected ZIP contents, verified recent-run ordering after two same-second runs, and verified explicit-impact example payload. Chrome UI smoke clicked Evidence, ran the preloaded example, and observed PASS verdicts, artifact paths, capsule hash, and polished Markdown report; screenshots saved to `/tmp/abaqus-agent-offline-evidence-ui-smoke.png` and `/tmp/abaqus-agent-offline-evidence-report-polish-ui-smoke.png`. | Verified by command for demo gallery CLI probe, local demo pack CLI/API/MCP stdio/HTML probes, demo gallery HTTP ZIP probe, vault HTTP probe, vault/frontend static probe, CLI probe, Direct API smoke, examples API HTTP probe, artifact/ZIP/recent-list/HTML HTTP probe, MCP stdio examples resource/tool smoke, MCP bridge smoke, Chrome UI smoke, report section probe, and multi-case gallery tests; Covered by focused tests; Supported by source. | This is a real runnable product slice over supplied KPI JSON, supplied `.inp` deck, and submitted/sample log text, but it does not invoke Abaqus, read real ODBs, authenticate users, provide a multi-user permission model, certify physical KPI values, or prove the KPI source came from a solver run. Recent history is in-process; vault storage is local filesystem persistence only. | Connect it to real run artifacts once Abaqus-generated KPI bundles are available, and add auth/permissions only if product usage needs shared artifact storage. |
| Case Memory over local vault | README now documents local Case Memory search and vault-to-vault diff over evidence artifacts. | `evidence/case_memory.py` converts vault records into memory entries with `memory_id`, kind, title, created time, status, summary, file list, and artifact links. `evidence/case_memory_diff.py` loads comparable candidate KPI dictionaries from saved root or safe nested `evidence.json` / `diff.json` vault artifacts, runs the shared Simulation Diff service, appends Case Memory source ids/filenames to `diff.md`, and writes a new `case-memory-diff` vault report. Direct API exposes `GET /api/case-memory` and `POST /api/case-memory/diff`; MCP bridge exposes `GET /mcp/api/case-memory` and `POST /mcp/api/case-memory/diff`; MCP stdio exposes `search_case_memory_tool`, `diff_case_memory_tool`, and `case-memory://vault`; frontend Evidence workspace can search Case Memory, filter by kind/status, pick baseline/candidate vault ids from memory rows, optionally fill baseline/candidate filenames with datalist suggestions from the selected row's comparable JSON files, run `/api/case-memory/diff`, render the Simulation Diff report/artifact links, refresh the vault/memory lists while preserving filters, and show a visible refresh error if the active API base is unreachable. Focused API/MCP tests create vault entries and assert query/kind/status filtering plus artifact links; Case Memory diff tests verify Direct API, real MCP bridge subprocess, MCP direct tool, and real MCP stdio paths. Actual HTTP probes covered two root offline evidence vault entries and same-vault nested cantilever vs plate-hole demo pack evidence, with unsafe `../evidence.json` returning 400. Frontend browser smoke on `127.0.0.1:8028` generated a Demo Pack and nested diff, verified row-specific filename suggestions without auto-fill, and confirmed `case-memory-diff + FAIL` / `local-demo-pack + PASS` filters isolate the expected rows. | Verified by command for focused API/MCP tests, static frontend source probe, actual search HTTP probe, actual root/nested diff HTTP probes, and frontend browser smoke; Covered by tests; Supported by source. | This is local filesystem-backed search/diff only. It does not provide embeddings/vector search, cloud sync, team permissions, deletion/mutation, semantic similarity, ODB reads, or proof that stored artifacts came from real Abaqus. | Extend toward richer Case Memory only after real run artifacts and user workflows clarify what should be indexed. |
| Local Simulation QA / evidence pipeline positioning | README first viewport now presents the project as a Local Simulation QA and Regression Framework: spec or `.inp` -> syntaxcheck -> solver -> ODB KPI -> physics contract -> diff/report. | `agent/orchestrator.py`, `runner/`, `post/`, evidence smoke scripts, report renderer, API/MCP/frontend smoke tests, and package metadata support the local evidence positioning. NL/spec generation remains available as one input path through `agent/llm_planner.py` and template fallback tests. | Supported by source; Covered by tests for local/template/mocked paths; Dry-run/mock-real verified for evidence plumbing; Environment-limited for real solver. | The positioning is now safer than the old NL-to-solver headline, but real solver/KPI/report evidence still requires Abaqus runtime validation. | Keep evidence-level matrix prominent; run real Abaqus environment validation before claiming real e2e simulation QA. |
| 7-stage real pipeline | README validation matrix presents the 7-stage orchestrator as source-supported, mock/fixture covered, and environment-limited for true execution. | `agent/orchestrator.py` implements validate/build/syntaxcheck/submit/monitor/extract/compare_expected. `tests/test_real_pipeline.py` mocks real dispatch. `tests/test_orchestrator_compare_expected.py` verifies expected KPI comparison without Abaqus. `tests/test_monitor_job.py` verifies public monitor file-state behavior without Abaqus. `tests/test_upgrade_odb_subprocess.py` verifies the outer ODB upgrade helper subprocess contract without Abaqus. `tests/test_extract_kpis_subprocess.py` verifies the outer KPI extraction subprocess contract without Abaqus. `tests/test_extract_kpis_inner_fake_odb.py` verifies common inner KPI calculations, benchmark/explicit-impact location aliases, field/RF location subsets, and displacement field inference with fake ODB objects. `core/pipeline.py` API/UI path defines 6 stages and simulated fallback. | Supported by source; Covered by tests via mocks/fixtures/fake subprocesses; Environment-limited for true execution. | README now distinguishes the 7-stage real orchestrator boundary from the API/frontend 6-stage simulated path, but real build/solver/ODB stages still require Abaqus. | Validate orchestrator on real Abaqus when an Abaqus environment is available, preserving evidence for build/syntaxcheck/submit/monitor/extract/compare stages. |
| `spec.yaml` validation | README says Problem Spec is validated against schema before code runs. | `tools/schema_validator.py`; `schema/spec_schema.json`; `tests/test_schema.py` and `tests/test_premium_schema.py`; benchmark dry-run validates 4 specs. | Verified by command; Covered by tests. | Strong for local schema validation; does not prove downstream physical correctness. | Keep as verified local capability; extend later with physics contracts if planned. |
| Deterministic run IDs | README/frontend now say spec-based runs use deterministic `sha256(spec)[:16]` run IDs, while benchmark runs create separate records. | `core.helpers.make_run_id` returns the first 16 hex chars of `sha256(spec_yaml)`. Direct API and MCP `start_run` use `make_run_id(spec_yaml)`. Direct API and MCP benchmark runs use separate `bench_*` IDs. `tests/test_core_pipeline.py` covers deterministic and different-input run IDs. | Covered by tests; Supported by source. | Deterministic IDs are proven for spec-based API/MCP runs, not a blanket guarantee that all reruns reuse every artifact or that benchmark runs are idempotent. | Keep wording scoped to deterministic spec-run IDs unless cache semantics are designed and tested end-to-end. |
| `build_model` CAE noGUI -> `.inp` | README lists `runner/build_model.py` and pipeline stage. | `runner/build_model.py` generates CAE noGUI scripts and handles `custom_inp`; orchestrator calls it. `tests/test_build_model_custom_inp.py` verifies `custom_inp` copies an existing `.inp`, writes the custom script marker, returns `cached=False`, and does not call Abaqus CAE; missing custom source decks raise structured `AbaqusAgentError(FILE_NOT_FOUND)`; existing cached `.inp` behavior remains covered; normal generated-script handoff is fake-runner tested by asserting `build_model_script.py` exists, `_run_cae_nougui` receives the expected script/workdir/release, and the returned `.inp` path is detected after the fake runner writes it. No real `abaqus cae noGUI` command run. | Covered by tests for custom_inp no-CAE/error paths and generated-script handoff; Supported by source; Environment-limited for real generated CAE execution. | Generated CAE script handoff is locally tested, but script semantics and real `.cae/.inp` generation still require Abaqus executable. | Run syntax/build-only validation in Abaqus environment for generated CAE cases. |
| Safety AST guard | README says safety is a command-tested static guard plus prompt constraints for generated script text; automatic enforcement across every generation path is not claimed. | `tools/static_guard.py`; `tests/test_static_guard.py`; `prompts/script_generator.txt` includes guard constraints. Source audit found no automatic call from `runner/build_model.py` into `check_script`; the current `build_model` CAE template imports `os`, which the guard intentionally blocks for prompt-generated scripts. Full pytest passed. | Verified by command for guard behavior; Covered by tests; Source-audited for integration boundary. | Guard tests cover representative patterns and prompt constraints, but automatic enforcement is not wired/proven across every generated script path. Real generated-script execution still depends on Abaqus environment validation. | Keep README claim scoped to tested guard/prompt constraints; design a separate integration ticket before enforcing guard on template-generated CAE scripts. |
| Abaqus syntaxcheck | README, source-facing stage text, and frontend copy now frame syntaxcheck as a pre-solver fail-fast gate and no longer state no-license/no-token behavior as a locally verified fact. | `runner/syntaxcheck.py` source calls `abaqus job=... syntaxcheck interactive`; orchestrator calls it when enabled. `agent/orchestrator.py` stage docstring, `core/pipeline.py` simulated stage label, and `frontend/index.html` UI copy use pre-solver/check wording. `tests/test_syntaxcheck_runner.py` verifies command args, cwd, log writing, `.dat` warning/error parsing, `ok` behavior, and structured `ABAQUS_NOT_FOUND` error using mocked subprocesses. No real syntaxcheck run. | Covered by fake-subprocess tests; Supported by source; Environment-limited for real Abaqus execution. | Local audit verifies command plumbing but not actual Abaqus syntaxcheck/license behavior. Real license behavior is environment-specific until tested on an Abaqus machine. | Real Abaqus syntaxcheck validation without running solver. |
| Job submission | README says `submit_job` executes analysis. | `runner/submit_job.py` builds `abaqus job=...` command and handles interactive/background modes; orchestrator calls it. `tests/test_submit_job_runner.py` verifies interactive command/env/log/meta success, license failure classification, background `Popen` command behavior, `allow_license_queue=True` env behavior, and structured `ABAQUS_NOT_FOUND` error with mocked subprocesses. `submit_job` now forwards `lmhanglimit=1` to subprocess env when `allow_license_queue=False`. No solver job run. | Covered by fake-subprocess tests; Supported by source; Environment-limited for real Abaqus execution. | License availability, real queue behavior, path behavior inside Abaqus, Windows/Abaqus version compatibility, and actual solver execution remain unverified locally. | Real Abaqus run on a small case with license-aware safeguards. |
| Job monitoring | README says `.sta/.log` polling. | `runner/monitor_job.py`; `tests/test_monitor_job.py` covers parser behavior plus public `monitor_job()` file-state behavior using local fixtures: absent files return pending, live `.sta` progress is parsed, `.log/.msg` diagnostics are deduped, completed log plus `.odb` reports completed and `odb_path`, and failed `.sta` status wins even when an `.odb` exists. | Covered by fixture tests; Supported by source; Environment-limited for live Abaqus polling. | Fixture files prove local status parsing/aggregation, not timing behavior against a real running Abaqus job. | Pair with real job validation and collect `.sta/.log/.msg/.odb` evidence from a real run. |
| Solver Doctor log evidence | README says Solver Doctor reads existing solver log artifacts or submitted log text and renders deterministic evidence without invoking Abaqus or an LLM, and exposes its deterministic pattern catalog. | `doctor/solver_doctor.py` creates JSON/Markdown reports from `.msg/.dat/.sta/.log` artifacts via the existing log parser, and `diagnose_log_texts()` accepts API/UI/log-text payloads through a temp workdir before reusing the same parser. `premium/autorepair/log_parser.py` exposes deterministic parser pattern specs, and `doctor/solver_doctor.py` combines them with category guidance through `list_doctor_patterns()`. Direct API exposes `POST /api/doctor/diagnose` and `GET /api/doctor/patterns` with `category` / `severity` filters; MCP bridge exposes `POST /mcp/api/doctor/diagnose` and `GET /mcp/api/doctor/patterns`; MCP stdio exposes `diagnose_solver_logs_tool`, `get_solver_doctor_patterns_tool`, and `doctor-patterns://catalog`; frontend `Solver Doctor` workspace can load sample logs, submit diagnosis, render status/category/findings/Markdown, and show a Pattern Gallery panel with category/severity filters plus row-level detail inspection for regex, explanation, recommendation, and real-env boundary. `tests/test_solver_doctor.py` covers completed/no-finding reports, license/convergence/distortion/rigid-body/path/ODB/syntax/memory/output classifications, Markdown evidence tables, CLI JSON/Markdown output, text payload diagnosis, bad job names, empty payloads, unsupported suffixes, and pattern gallery filtering. `tests/test_server_api_smoke.py`, `tests/test_mcp_bridge_real_subprocess.py`, `tests/test_mcp_server.py`, and `tests/test_mcp_stdio_client.py` cover Direct API, bridge, direct MCP tool/resource, and real MCP stdio diagnosis/pattern catalog discovery. Actual HTTP probe on `127.0.0.1:8012` returned 24 parser patterns across 15 categories and 2 license/error filtered patterns. Browser smoke on `127.0.0.1:8032` verified LICENSE+ERROR filtering and `msg-10-license` detail rendering. | Covered by fixture/API/MCP tests; Verified by actual HTTP probe, static frontend source probe, frontend browser smoke, and real MCP stdio smoke; Supported by source. | Fixture/submitted logs and pattern catalog discovery prove deterministic classification/reporting/discovery paths, not real-world coverage across actual Abaqus failure logs. No Abaqus executable, license, or solver job was invoked. API/UI/MCP log text is processed in temporary local files and is not persistent evidence storage. | Feed anonymized real `.msg/.dat/.sta/.log` artifacts from real Abaqus runs into Solver Doctor and add recurring patterns with source-backed tests. |
| Physics Contract evaluator | README says Physics Contract checks can run over KPI dictionaries without Abaqus and benchmark runs/reports can attach/render contract results. | `contracts/evaluator.py` evaluates `range`, `direction`, `relative_error`, and `order` contracts; `contracts/io.py` loads JSON/YAML contract files and converts legacy `expected.json` KPI tolerances into `relative_error` contracts. `run_benchmark.run_case` attaches `contracts` results when KPI values and expected/contract files are available, and `generate_report` renders `contracts.checks` into a Physics Contracts section. Tests cover evaluator pass/fail/warning status, missing KPIs, zero-reference absolute tolerance, unsupported type failures, contract file loading, legacy expected conversion, benchmark contract report rendering, and fake-orchestrator run_case contract attachment/error handling. | Covered by unit tests/fake orchestrator; Supported by source. | Evaluator, IO, run_case attachment, and report rendering semantics are tested, but domain validity depends on real KPI extraction and carefully authored contract definitions. Real Abaqus contract evaluation remains environment-limited. | Add schema/examples and validate contract evaluation against real KPI values when a real Abaqus run is available. |
| Experiment Capsule store | README says Experiment Capsule store records copied input/artifact hashes and provenance metadata. | `capsule/store.py` creates `inputs/`, `artifacts/`, and `capsule.json`; `capsule/metadata.py` standardizes `metadata_schema_version`, `project`, `workflow`, `evidence_source`, `evidence_level`, `overall_status`, `real_env_required`, and `real_env_verified`; `tests/test_capsule_store.py` covers manifest persistence, SHA-256 hashes, copied input/artifact content, duplicate filename disambiguation, missing source errors, required run IDs, and the metadata helper. The smoke harness and offline evidence workflow now write standardized capsule evidence metadata. | Covered by unit tests; Integrated into smoke harness dry-run/require-real/mock-real evidence and offline evidence capsules. | Store semantics, evidence metadata, and artifact packaging are tested, but this does not prove artifact correctness, real Abaqus provenance, or a final real-run capsule schema. | Connect capsule manifests to persistent evidence browsing/export once product surface needs it. |
| Simulation Diff KPI report | README documents standalone Simulation Diff over supplied KPI JSON. | `simdiff/kpi_diff.py` compares baseline/candidate KPI dictionaries with optional `rtol`/`atol`; `simdiff/service.py` writes standalone `diff.json` and `diff.md` reports with explicit no-real-Abaqus verification boundary. Direct API exposes `POST /api/simdiff/kpis`; MCP bridge exposes `POST /mcp/api/simdiff/kpis`; MCP stdio exposes `run_simulation_diff_tool` and `simdiff://example`; frontend Evidence workspace includes a compact Simulation Diff panel. API and bridge paths persist `simulation-diff` entries into the local evidence vault, so Case Memory can discover generated diff reports. Focused tests cover service output, Direct API, real bridge subprocess, MCP direct tools/resources, and real MCP stdio discovery/call. Actual HTTP probe on `127.0.0.1:8011` returned a failing diff, downloaded `diff.md`/`diff.json`, and found a `simulation-diff` Case Memory entry. | Verified by command for focused API/MCP tests, static frontend source probe, and actual HTTP probe; Covered by tests; Supported by source. | Diff semantics are tested over supplied KPI values only. Source KPI correctness still depends on real extraction and stable run artifacts; this ticket did not compare real Abaqus runs or read ODB files. | Use this standalone surface as the user-facing Simulation Diff entry point, then extend toward real run/capsule comparisons after real Abaqus artifacts are available. |
| ODB upgrade helper | README lists ODB version mismatch handling through `upgrade_odb_if_needed()`. | `post/upgrade_odb.py` invokes `abaqus python _upgrade_inner.py -- ...`; `tests/test_upgrade_odb_subprocess.py` verifies default and explicit upgraded paths, command/capture/timeout options, result JSON parsing, missing executable error, timeout error, no-result stderr fallback, and inner script content containing expected `odbAccess.isUpgradeRequiredForOdb` / `upgradeOdb` calls. No real ODB or `odbAccess` run. | Covered by fake-subprocess tests for outer adapter and inner-script content; Supported by source; Environment-limited for real `odbAccess` runtime. | Local tests prove command/result plumbing, not Abaqus ODB version compatibility or upgrade success. | Run real ODB upgrade check on an older ODB when Abaqus runtime evidence is available. |
| KPI extraction | README says ODB -> KPI dict via Abaqus Python. | `post/extract_kpis.py` invokes `abaqus python` and uses `odbAccess`; orchestrator calls it. `tests/test_extract_kpis_subprocess.py` verifies outer command construction (`abaqus python post/extract_kpis.py -- ...`), cwd/timeout/capture options, `_kpi_spec.json` writing, `_kpi_result.json` success parsing, missing executable error, timeout error, and no-result stderr fallback without invoking real Abaqus. `tests/test_extract_kpis_inner_fake_odb.py` verifies `_extract_single_kpi` with fake ODB objects for nodal displacement subset/component minimum, field max Mises, field min component, reaction-force absolute max, eigenfrequency mode lookup, derived stress concentration element subset, missing-field error behavior, benchmark aliases `tip_center -> TIP_NODES` / `hole_edge_set -> HOLE_EDGE`, explicit-impact aliases `fixed_face -> FIXED_END` / `top_face -> LOAD_END`, field/RF `location` subset selection, and `field_max` displacement component inference (`U1/U2/U3` -> `U`). No real ODB extraction run. | Covered by fake-subprocess tests for outer adapter and fake-ODB tests for inner calculations/location aliases/location subsets/field inference; Supported by source; Environment-limited for real `odbAccess` runtime. | Fake ODB objects prove Python branch semantics and alias/subset/inference plumbing, not real Abaqus ODB object compatibility, region naming, field output availability, or Abaqus Python runtime behavior. | Real ODB KPI extraction on one completed benchmark case. |
| ODB Lens KPI recipe gallery | README documents built-in ODB Lens KPI recipes. | `post/kpi_recipes.py` exposes 6 built-in recipes covering all currently implemented extractor types: `nodal_displacement`, `field_max`, `field_min`, `reaction_force_max`, `eigenfrequency`, and `derived_stress_concentration`. Direct API exposes `/api/kpi-recipes` with `case` / `kpi_type` filters and `/api/kpi-recipes/{recipe_id}`; MCP bridge exposes matching `/mcp/api/kpi-recipes...`; MCP stdio exposes `kpi-recipes://examples` and `get_kpi_recipe_tool`; frontend Evidence workspace includes a KPI Recipes panel with case/type filters plus row-level detail inspection that renders each recipe's `kpi_spec`, `kpi_types`, and verification boundary. Focused tests verify list/filter/get, MCP resource/tool, real stdio discovery, and that recipe KPI types match extractor-supported types. Actual HTTP probe on `127.0.0.1:8010` returned 6 recipes, filtered plate-hole recipes, and loaded the modal frequency recipe. Browser smoke on `127.0.0.1:8030` verified `case=modal`, opened `modal-first-three-frequencies` detail, and rendered three `eigenfrequency` specs plus the boundary. | Verified by command for focused API/MCP tests, fake-ODB alignment tests, static frontend source probe, actual HTTP probe, and frontend browser smoke; Covered by tests; Supported by source. | Recipes are source-supported and fake-ODB aligned only. They do not prove real Abaqus ODB extraction on this machine, and they do not add new extractor semantics. | Use these recipes as the discoverable ODB Lens entry point, then validate on real ODBs when an Abaqus environment is available. |
| `compare_expected` / result report | README says compare_expected -> `result.json` + benchmark report. | `agent/orchestrator.py` compares extracted KPIs against expected JSON and saves `result.json`; `tests/test_orchestrator_compare_expected.py` covers PASS within tolerance, FAIL outside tolerance, MISSING KPI, zero-reference INFO behavior, result shape, and progress callback data without Abaqus; `run_benchmark.py` writes Markdown/JSON reports; `tests/test_run_benchmark_report.py` verifies benchmark report summary counts, KPI rendering, PASS/FAIL labels, KPI comparison table, and error details from fixture results. Dry-run report has no KPIs/regression. | Covered by fixture tests for compare logic and report rendering; Supported by source; Dry-run only for benchmark report command. | Current dry-run benchmark report still shows `Regression passed 0/4` because no real KPIs are produced; fixture tests do not prove real ODB extraction values. | Verify compare/report on real extracted KPIs when Abaqus/ODB evidence is available. |
| Benchmark runner | README says benchmark runner and report generator. | `run_benchmark.py --dry-run` passed; generated Markdown/JSON reports then removed because `reports/` is outside allowed scope. `tests/test_run_benchmark_report.py` now verifies report generation from fixture result data without writing report artifacts. | Verified by command for dry-run and fixture report rendering; Dry-run only for real case execution. | Dry-run validates specs only; fixture report tests do not prove solver, KPI, or regression correctness. | Real benchmark for at least cantilever when Abaqus is available. |
| 4 benchmark cases | README lists cantilever, plate_hole, modal, explicit_impact. | `cases/*/{spec.yaml,expected.json,runner.json}` exists for all 4; schema tests cover all; dry-run found all 4 and passed. | Verified by command; Covered by tests; Dry-run only. | Analytical references are not proven by solver output in this audit. | Real Abaqus validation matrix for the 4 cases, starting with cantilever. |
| FastAPI REST API with SSE and premium endpoints | README says local API/frontend smoke passes through the simulated API/UI path and is not 7-stage real orchestrator, solver, or ODB evidence. | `server.py` defines FastAPI app, REST endpoints, run start, benchmark run trigger, SSE stream, premium endpoints, frontend static mount, FastAPI metadata aligned to Local Simulation QA / regression positioning, `StartRunRequest.runner_cfg` with `Field(default_factory=dict)`, offline evidence/demo-gallery endpoints, and Solver Doctor log-text diagnosis endpoint. `tests/test_server_api_smoke.py` verifies `/health`, template spec generation, spec validation, `/api/run/start`, `/api/run/{run_id}/stream` to `done` over the no-Abaqus simulated pipeline, benchmark resource, `/api/benchmark/run?dry_run=true`, offline evidence/artifact/demo-gallery paths, `/api/doctor/diagnose`, SSE stream for a preloaded completed run, `/api/premium/features`, empty activation failure, dev-key activation success, and per-instance runner config defaults. | Verified by command for local REST/SSE/premium/benchmark/offline-evidence/doctor smoke; Supported by source. | Smoke does not start a real Abaqus solver job, validate long-running real background solver behavior, run real Abaqus benchmark cases, process real-world solver failure logs, or test real commercial license/payment integration. | Keep as local API run/SSE/benchmark/premium/evidence/doctor smoke verified; pair with real Abaqus smoke and real license policy decisions when those become relevant. |
| MCP server | README says MCP server for AI agent integration. | `mcp_server.py` uses `FastMCP`; `tests/test_mcp_server.py` directly calls tools/resources; `tests/test_mcp_stdio_client.py` starts `mcp_server.py` as a subprocess through the MCP stdio client and verifies initialize, tool listing, `health_check`, spec validation, `run_benchmark_tool(dry_run=True)`, `run_offline_evidence_tool`, `get_offline_evidence_example_tool`, `create_local_demo_pack_tool`, `diagnose_solver_logs_tool`, `get_premium_features`, empty premium activation failure, dev-key activation success, resources, `benchmark://cases`, `premium://features`, and `evidence://examples`. | Verified by command for stdio transport, benchmark dry-run trigger, offline evidence tool, offline examples resource/tool, local demo pack generation/ZIP inspection, Solver Doctor diagnosis tool, premium tools/resources, install/tests, and direct functions. | Stronger than direct calls, but still does not exercise real Abaqus execution. Offline evidence/examples/demo packs use supplied KPI values and sample log text only. Solver Doctor uses fixture/submitted log text and does not prove real-world pattern coverage. Premium checks are dev/test license behavior, not commercial license or payment policy validation. MCP stdio returns file paths/report content; browser artifact URLs are provided by the HTTP bridge/direct API surfaces. | Keep as MCP stdio benchmark/offline-evidence/examples/demo-pack/doctor/premium smoke verified; add deeper client workflows only when needed. |
| HTTP-to-MCP bridge | README says HTTP bridge for web clients. | `mcp_bridge.py` spawns `mcp_server.py`, exposes FastAPI bridge through FastAPI lifespan startup/shutdown, uses `Field(default_factory=dict)` for `StartRunRequest.runner_cfg`, and has FastAPI metadata aligned to browser-facing Local Simulation QA evidence workflows and dry-run/mock-real/real-runtime boundaries; `tests/test_mcp_bridge.py` mocks endpoint behavior and verifies per-instance runner config defaults; `tests/test_mcp_bridge_real_subprocess.py` uses FastAPI TestClient with a real `MCPConnection` subprocess and verifies health, spec validation, `benchmark://cases`, `/mcp/api/benchmark/run?dry_run=true`, `/mcp/api/evidence/offline`, bridge-scoped `/mcp/api/evidence/artifacts/{artifact_id}/...` retrieval for report/capsule/ZIP artifacts, ZIP content inspection, recent artifact listing/latest-first ordering, premium feature status, empty premium activation failure, dev-key activation success, run start, and `/mcp/api/run/{run_id}/stream` until `done` over the no-Abaqus simulated pipeline. A real bridge HTTP probe on port 8002 returned PASS offline evidence and a capsule manifest. | Verified by command for bridge subprocess smoke, lifecycle cleanup, benchmark dry-run trigger, offline evidence routing/artifact/ZIP retrieval/recent listing, premium endpoint routing, simulated SSE stream, request model defaults, and metadata alignment; Covered by tests via mocks for endpoint variants. | Smoke does not run real Abaqus benchmark cases, cover commercial license/payment policy, or validate every long-running real solver condition. Offline evidence uses supplied KPI values only and bridge artifact registry is in-process. | Keep as bridge subprocess benchmark/offline-evidence/SSE/premium smoke verified; pair with real Abaqus smoke when an Abaqus environment is available. |
| LLM planner | README says Anthropic/OpenAI/template fallback. | `agent/llm_planner.py`; `core/spec_generator.py`; tests cover template fallback and keyword cases; `tests/test_llm_planner_provider_mock.py` covers mocked OpenAI message extraction, mocked Anthropic text extraction, and `generate_spec_async` temporary OpenAI env override restoration. Optional dependencies exist under `llm` extra. No external LLM API call run. | Covered by tests for template and provider adapter plumbing; Supported by source for provider paths; Environment-limited for real API keys/network. | Real provider SDK/API behavior, model availability, and live key handling remain unverified; model names may need current-provider validation before production use. | Run explicit provider API smoke only when keys/network are available and the user authorizes external API calls. |
| Frontend | README says web frontend and dashboard. | Browser smoke opened `http://127.0.0.1:8000`, confirmed title/main UI/topbar `API · ABAQUS ✗ sim · 4 cases`, generated and validated a cantilever spec, loaded benchmark cases, ran benchmark dry-run to PASS, and recorded no console errors. The benchmark smoke screenshot is now committed as `docs/assets/dashboard-preview.jpg`; original smoke screenshots were saved under `/tmp/abaqus-agent-frontend-smoke-*.png`. Follow-up reload confirmed stale `TESTS: 39 ✓` was replaced by `LOCAL SMOKE ✓` and benchmark copy now says local smoke/pytest can run without Abaqus. Settings/Premium browser smoke ran direct API on `127.0.0.1:8000` and MCP bridge on `127.0.0.1:8002/mcp`, saved direct/MCP URLs, tested MCP bridge connection (`ok · transport: mcp`), activated premium dev keys through direct and MCP UI paths, observed all five premium features as ENABLED, confirmed empty bridge activation returns `No license key provided`, recorded no browser console errors, and saved `/tmp/abaqus-agent-settings-premium-mcp-smoke.png`. Served-frontend HTTP smoke on `127.0.0.1:8000` confirmed the updated Benchmark copy for syntaxcheck license boundary and deterministic run IDs is present, while old no-license/license-token and all-case idempotency copy is absent. Offline Evidence UI smoke opened the new Evidence workspace, ran the preloaded example against the local API, observed PASS/contract/diff/capsule summaries plus artifact paths and Markdown report, and saved `/tmp/abaqus-agent-offline-evidence-ui-smoke.png`. Case Memory Diff browser smoke on `127.0.0.1:8000` listed two temporary-vault entries, picked baseline/candidate ids, posted `/api/case-memory/diff`, rendered `FAIL · 2 rows`, displayed the Markdown report, and refreshed Case Memory to include the new diff record. Same-origin API-base browser smoke on `127.0.0.1:8016` cleared the saved Direct API override and confirmed frontend requests for health, examples, vault, Case Memory, KPI recipes, Doctor patterns, and benchmark hit the 8016 server instead of a hard-coded 8000 URL. The Evidence workspace now renders JSON/MD/CAPSULE/ZIP artifact links, recent Evidence runs with MD/ZIP links from `artifact_urls`, an API-backed case selector for cantilever/plate-hole/modal/explicit-impact examples with local fallback, a Demo Gallery action that calls `/api/evidence/demo-gallery`, and an Evidence Vault section that refreshes `/api/evidence/vault` and renders MD/ZIP/JSON links. The frontend now also includes a Solver Doctor workspace with sample log loading, `/api/doctor/diagnose` submission, status/category/findings summaries, and Markdown report rendering. Recent Evidence list layout hardening constrains right-side links/details, wraps long regexes/nested filenames, and uses a single-column fallback at narrow widths; browser smoke on `127.0.0.1:8033` verified no horizontal overflow for LICENSE pattern rows/detail. Mobile responsive smoke on `127.0.0.1:8040/?v=mobilefix4` used a 390x844 Chrome viewport, generated a Demo Pack, observed `PASS · demo pack`, `GALLERY HTML`/`DOCTOR MD`/`DIFF MD` artifact links, no console errors, `document.body` and `documentElement` `scrollWidth == clientWidth == 390`, and saved `/tmp/abaqus-agent-mobile-evidence-smoke-final.png`; the only remaining overflow offender was the intentionally horizontal mobile nav. Served frontend probe on `127.0.0.1:8005` confirmed Doctor nav/panel/button/API strings; static frontend probe confirmed Evidence Vault UI/API/link hooks. In-app browser was unavailable during some artifact-link/ZIP/history/gallery/examples-API/doctor/vault tickets, so those rendering paths were verified by source/static checks and Direct API HTTP/CLI probes where browser screenshots were not available. | Verified by browser/CDP smoke for local direct API mode, Offline Evidence UI, Case Memory Diff UI, same-origin non-8000 Direct API default, Evidence list overflow hardening, mobile 390px Evidence Demo Pack flow, and Settings/Premium direct/MCP UI paths; HTTP-verified for served copy boundary, Direct API artifact retrieval, ZIP bundle retrieval, recent run listing, examples API, demo gallery ZIP retrieval, Doctor API/served frontend strings, and vault API/static frontend hooks; Supported by source and focused gallery/doctor/vault/frontend static tests. | Browser/HTTP smoke and README preview asset do not validate real Abaqus execution, commercial license/payment behavior, multi-user persistent artifact storage, real physical KPI certification, or real-world Solver Doctor pattern coverage. Dev-key premium activation is development behavior only. Offline Evidence UI uses supplied KPI values only. Mobile smoke covered the Evidence Demo Pack path at 390px; it is not exhaustive coverage of every panel and device size. | Keep mobile smoke focused on product-critical Evidence flows; broaden device coverage only if the frontend becomes launch-critical. |
| Premium features | README says 5 premium features: coupling, adaptivity, parametric, geometry, autorepair. | `premium/` modules exist; tests cover coupling/adaptivity/parametric/geometry/autorepair/licensing/schema; full pytest passed. | Verified by command; Covered by tests; Supported by source. | Tests do not run generated CAE code in Abaqus; premium license/product boundary is code-level only. | Keep as tested code-generation/log-parser capability; require Abaqus validation before claiming production simulation support. |
| Unit tests | README formerly said 197 unit tests. | Latest accumulated dirty-worktree verification passed with full-project ruff, full `git diff --check`, and 356 full pytest tests after adding local evidence smoke tests, bridge SSE smoke, premium API smoke, LLM provider adapter mock tests, orchestrator compare_expected fixture tests, benchmark report fixture tests, custom_inp no-CAE/error and fake-CAE handoff build_model tests, syntaxcheck/submit_job/KPI extraction/ODB upgrade fake-subprocess tests, fake-ODB inner KPI calculation/location-alias/location-subset/field-inference tests, explicit-impact location alias tests, monitor_job public file-state fixture tests, Physics Contracts, Experiment Capsule, Simulation Diff, benchmark contract wiring, smoke-harness capsule packaging, the offline v0.2 evidence slice, offline evidence FastAPI/MCP/UI paths, standardized capsule evidence metadata, artifact/ZIP/recent-list retrieval, multi-case offline evidence gallery tests, custom `.inp` deck evidence example tests, MCP examples resource/tool tests, offline demo gallery CLI/API tests, Solver Doctor text/API/MCP tests, Solver Doctor MCP stdio tool tests, local evidence vault tests, local demo pack API/frontend tests, local demo pack MCP stdio tests, local demo pack bundle verifier tests, local CLI smoke nested demo pack verifier tests, frontend static contract tests for nested Evidence Vault smoke verification detail, immediate local CLI smoke nested verification rendering, and mobile responsive Evidence layout, Case Memory vault search/diff tests, ODB Lens KPI recipe gallery tests, standalone Simulation Diff API/MCP/frontend/vault tests, and Solver Doctor pattern gallery API/MCP/frontend tests. Local audit found FastAPI 0.136.3, Starlette 1.2.1, httpx 0.28.1, and no `httpx2`; the remaining warning is emitted by installed `starlette.testclient` when it falls back from missing `httpx2` to `httpx`. | Verified by command. | One warning remains from external Starlette TestClient/httpx compatibility, not project runtime code. Bridge `on_event` deprecations have been removed. | Decide in a separate ticket whether to add/evaluate `httpx2` for tests or deliberately filter the external warning if warning-free output becomes a release criterion. |
| CI/CD | README says CI/CD. | `.github/workflows/ci.yml` and `publish.yml` exist. `gh run list --repo Tomsabay/abaqus_agent --branch main --limit 10` showed the latest 10 visible `main` CI runs succeeded. Latest run `26815338911` on remote head `62c3eb541bddc583c01a1e9d86e4409f07260ce2` passed build plus Python 3.10/3.11/3.12 test jobs. | Verified remotely for current visible GitHub Actions status; Supported by source. | Local checkout is behind remote `main` and has uncommitted Goal Chain changes; remote CI green does not cover current local dirty state or real Abaqus execution. | Re-run CI after committing/pushing the current local evidence hardening batch. |
| PyPI packaging | README formerly had PyPI badge and `pip install abaqus-agent` commands. | `pyproject.toml` metadata, dependencies, optional extras, scripts, build target exist; editable install and metadata/entry point passed locally. Public PyPI JSON API request to `https://pypi.org/pypi/abaqus-agent/json` returned 404. README now uses source install as the primary path and states PyPI is not published yet. | Verified by command for local packaging metadata/install; Verified remotely as unpublished on PyPI. | No published artifact exists under `abaqus-agent` as of this audit. | Decide whether to publish to PyPI or keep source-only distribution for now. |
| Docker / compose deployment | README says `docker compose up -d`, API at 8000, MCP bridge at 8001. | `Dockerfile` and `docker-compose.yml` exist and were inspected. Intended smoke path is API port 8000 with `/health` plus dry-run benchmark endpoint, but `docker --version`, `docker compose version`, and `docker compose config` failed with `docker: command not found` in the local shell. README now notes Docker runtime is unverified in the latest local audit. | Supported by config; Environment-limited locally. | Container runtime may fail despite files existing; no Docker build or HTTP container probe was executed. | Run Docker smoke on a machine with Docker CLI/daemon available. |

## Main Mismatches / Risks
- README no longer uses `[x]` roadmap items for mixed-evidence capabilities. It now presents a validation matrix tied to this audit.
- Local command evidence verifies install, metadata/CLI, default tests, benchmark dry-run, smoke dry-run/mock-real, and smoke report rendering, but not real Abaqus execution.
- README validation matrix now states API/frontend shared pipeline smoke completes through the no-Abaqus simulated API/UI path and is not 7-stage real orchestrator, solver, or ODB evidence.
- Frontend browser smoke passes in direct API simulation mode; stale static `TESTS: 39 ✓` metadata has been replaced with stable local-smoke wording.
- `core/pipeline.py` uses 6 stages in API/UI tests, while README/orchestrator describe a 7-stage real pipeline including compare.
- MCP server stdio transport and HTTP bridge subprocess path now have real smoke tests; bridge lifecycle uses FastAPI lifespan; bridge SSE over real subprocess is verified for no-Abaqus simulated runs.
- Benchmark dry-run reports `DRY_RUN_PASS` for all 4 cases but produces no KPI/regression evidence.
- Remote GitHub CI is currently green on the latest visible remote `main` run, but it does not cover the current local dirty state.
- PyPI is not published under `abaqus-agent`; README now avoids PyPI badge/install claims.
- Docker config exists but container runtime is a blocked branch because Docker CLI is unavailable in the current shell.

## Recommended Priority
Ready next ticket should run the new validation entry on a real Abaqus machine, then execute a license-aware minimal-scope cantilever syntaxcheck/build/solver/KPI/compare baseline. That remains the largest evidence gap behind README's central pipeline claim.
