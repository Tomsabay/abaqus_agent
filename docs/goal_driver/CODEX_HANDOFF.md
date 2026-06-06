# CODEX_HANDOFF

## Project
abaqus-agent

## Mode
Goal: v0.2.0-dev GitHub technical preview release and publish

## Ticket Completed
`V0.2-DEV-RELEASE-PUBLISH-001`：完成 v0.2.0-dev 发布准备，修复 rebase 后 release gate 兼容问题，跑完整 release verification；准备提交、推送、打 tag 并创建 GitHub Release。

## Files Changed
- `pyproject.toml`
- `capsule/store.py`
- `contracts/evaluator.py`
- `simdiff/kpi_diff.py`
- `evidence/case_memory_diff.py`
- `runner/build_model.py`
- `runner/submit_job.py`
- `runner/syntaxcheck.py`
- `post/extract_kpis.py`
- `scripts/validate_abaqus_env.py`
- `server.py`
- `mcp_bridge.py`
- `mcp_server.py`
- `frontend/index.html`
- `docs/goal_driver/CODEX_HANDOFF.md`

## Verification
- Source install: `/tmp/abaqus-agent-release-venv/bin/python -m pip install -e ".[dev]"` passed, package version `0.2.0.dev0`.
- Full static check: `/tmp/abaqus-agent-release-venv/bin/python -m ruff check .` passed.
- Whitespace check: `git diff --check` passed.
- Full test suite: `/tmp/abaqus-agent-release-venv/bin/python -m pytest -q` -> `465 passed, 1 warning`.
- Benchmark dry-run: `/tmp/abaqus-agent-release-venv/bin/python run_benchmark.py --dry-run` -> 5/5 `DRY_RUN_PASS`.
- Local CLI smoke: `abaqus-agent-local-cli-smoke --out-dir /tmp/abaqus-agent-release-cli-smoke --json` -> `overall_status=PASS`, 11 steps PASS.
- CLI smoke ZIP verify: `abaqus-agent-verify-local-cli-smoke /tmp/abaqus-agent-release-cli-smoke/local_cli_smoke.zip --json` -> `overall_status=PASS`, checked 4 files, nested demo pack verify PASS.
- Demo pack ZIP verify: `abaqus-agent-verify-local-demo-pack /tmp/abaqus-agent-release-cli-smoke/copied-local-demo-pack.zip --json` -> `overall_status=PASS`, checked 31 files.
- Real Abaqus evidence parse:
  - `evidence/real_abaqus_smoke_20260606_force_fix_pass/smoke_evidence.json`: `overall_status=real-env-verified`, `real_env_verified=true`
  - `contract_diff/real_smoke_contract_diff.json`: `overall_status=PASS`, `contracts=PASS`, `diff=PASS`, `real_env_verified=true`
  - KPIs: `U_tip=-0.0025716267991811037`, `MISES_MAX=0.38309070467948914`

## User-visible Evidence / Screenshots
- Latest real PASS bundle: `evidence/real_abaqus_smoke_20260606_force_fix_pass/`
- Latest real report: `evidence/real_abaqus_smoke_20260606_force_fix_pass/contract_diff/real_smoke_contract_diff.html`
- Local release smoke bundle: `/tmp/abaqus-agent-release-cli-smoke/local_cli_smoke.zip`
- Copied demo pack bundle: `/tmp/abaqus-agent-release-cli-smoke/copied-local-demo-pack.zip`

## Blockers / Next Decision
- No Abaqus/Tailscale/license blocker encountered in this publish-prep pass.
- Do not publish PyPI. GitHub Release only.
- `v0.1.0` must remain untouched.
- Proceeding next: amend/create the release-prep commit, push `main`, create/push annotated `v0.2.0-dev`, create GitHub Release.

## Message For ChatGPT Project
本轮完成 `V0.2-DEV-RELEASE-PUBLISH-001` 发布准备。rebase 后的 capsule/contracts/simdiff/build_model/ODB KPI/runner/env/server/MCP 兼容问题已修复；`pyproject.toml` 版本为 `0.2.0.dev0`。验证：source install PASS；`ruff check .` PASS；`git diff --check` PASS；full pytest `465 passed, 1 warning`；benchmark dry-run 5/5 PASS；local CLI smoke PASS（11 steps）；smoke ZIP verify PASS；demo pack ZIP verify PASS（31 files）；真实 Windows Abaqus bundle `evidence/real_abaqus_smoke_20260606_force_fix_pass/` 为 `real-env-verified=true`，contract/diff `PASS/PASS/PASS`，KPI=`U_tip=-0.0025716267991811037`、`MISES_MAX=0.38309070467948914`。下一步执行 GitHub-only release：提交/推 main/打 `v0.2.0-dev` tag/创建 GitHub Release；不发 PyPI，不动 `v0.1.0`。
