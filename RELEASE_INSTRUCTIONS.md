# Abaqus Agent Release Instructions

## Current Verified Status

Latest local audit date: 2026-06-06.

- Repository: `Tomsabay/abaqus_agent`
- Product positioning: Local Simulation QA and Regression Framework for Abaqus FEA.
- Remote `main`: `62c3eb541bddc583c01a1e9d86e4409f07260ce2`
- Latest visible GitHub Actions CI on remote `main`: success.
- CI jobs verified: build, test (3.10), test (3.11), test (3.12).
- Open PRs: none.
- Open issues: none.
- Remote tag: `v0.1.0` exists.
- GitHub Releases: no release currently exists.
- PyPI: `abaqus-agent` is not published; public PyPI JSON API returns 404.
- Docker runtime: config exists, but latest local audit could not run Docker because `docker` was unavailable in the shell.
- Real Abaqus runtime: still environment-limited on the local Mac, but a fresh
  Windows `--require-real` bundle now verifies one real cantilever PASS chain.
  Do not generalize that evidence beyond the recorded bundle and case.

## Release Readiness Gate

Latest release gate check: 2026-06-06.

Decision: **CONTENT GO / RELEASE ACTION GO for `v0.2.0-dev` GitHub technical preview.**

Recommended target: **prepare `v0.2.0-dev` as a technical-preview release**,
from the current release-prep commit after the verified changes are committed
and pushed. Do not publish PyPI.

Reason:

- `v0.1.0` already has a remote tag and points to an older commit.
- Current local work has moved into the v0.2 Simulation QA direction:
  evidence capsule, Physics Contract, Simulation Diff, Solver Doctor, local
  evidence vault, no-server CLI smoke, and real-smoke contract/diff plumbing.
- Releasing the old `v0.1.0` tag would underrepresent the current product
  direction.
- Final local release verification now passes from the intended release-prep
  tree: source install, full ruff, full pytest, benchmark dry-run, local CLI
  smoke, ZIP verification, demo pack verification, and the preserved real
  Abaqus PASS evidence parse.
- The latest real Windows cantilever chain now passes contract/diff, so the
  release content can honestly claim one verified real Abaqus PASS path:
  spec -> CAE/INP -> syntaxcheck -> submit -> ODB KPI -> Physics Contract ->
  Simulation Diff -> report.

Read-only preflight evidence:

- `git ls-remote origin refs/heads/main refs/tags/v0.1.0 refs/tags/v0.1.0^{}`:
  - remote `main`: `62c3eb541bddc583c01a1e9d86e4409f07260ce2`
  - tag `v0.1.0`: annotated tag object `55ab63fcedee458655d322072e3426e784c45d8e`, peeled commit `7fed2fe8f17e39a1a3b250779a8064bebc601025`
- `git ls-remote origin refs/tags/v0.2.0-dev refs/tags/v0.2.0-dev^{}`:
  no remote `v0.2.0-dev` tag was listed.
- `gh run list --repo Tomsabay/abaqus_agent --branch main --limit 5`: latest visible remote `main` CI runs are `success`.
- `gh release list --repo Tomsabay/abaqus_agent --limit 10`: no releases listed.
- Local release branch was rebased onto live remote `main` and verified before
  publishing.

Local release smoke evidence from the final publish gate:

- Source install in Python 3.11 release venv: passed, package version
  `0.2.0.dev0`.
- `/tmp/abaqus-agent-release-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-release-venv/bin/python -m pytest -q`: `465 passed,
  1 warning`.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-release-venv/bin/python run_benchmark.py --dry-run`:
  5/5 cases `DRY_RUN_PASS`.
- `abaqus-agent-local-cli-smoke --out-dir /tmp/abaqus-agent-release-cli-smoke --json`:
  `overall_status=PASS`, 11 steps PASS, `real_env_verified=false`.
- `abaqus-agent-verify-local-cli-smoke /tmp/abaqus-agent-release-cli-smoke/local_cli_smoke.zip --json`:
  `overall_status=PASS`, nested copied demo pack verification `PASS`.
- `abaqus-agent-verify-local-demo-pack /tmp/abaqus-agent-release-cli-smoke/copied-local-demo-pack.zip --json`:
  `overall_status=PASS`, 31 files checked.

Fresh Windows Abaqus PASS evidence added after the gate:

- Source snapshot was copied to `D:\code\abaqus_agent_force_fix_src` on
  `DESKTOP-PH97BKO` without changing the Windows main repo.
- Command:
  `scripts/run_real_abaqus_smoke.py --require-real --json --out-dir D:\code\abaqus_agent_force_fix_evidence\smoke_20260606_force_fix_pass`
  with `LM_LICENSE_FILE=27800@localhost` and
  `ABAQUS_AGENT_LICENSE_CONFIRMED=1`.
- Local copied evidence bundle:
  `evidence/real_abaqus_smoke_20260606_force_fix_pass/`.
- Result: `overall_status=real-env-verified`, `real_env_verified=true`.
- Verified real stages: environment preflight, input job preparation,
  syntaxcheck, submit job, monitor status collection, ODB KPI extraction, and
  integrated `contract_diff`.
- Real ODB KPIs: `U_tip=-0.0025716267991811037`,
  `MISES_MAX=0.38309070467948914`.
- Contract/diff result: `PASS` (`contracts=PASS`, `diff=PASS`).
- User-visible report:
  `evidence/real_abaqus_smoke_20260606_force_fix_pass/contract_diff/real_smoke_contract_diff.html`.
- Historical failing evidence is preserved separately at
  `evidence/real_abaqus_smoke_20260606_contract_diff/`; do not cite it as the
  latest release gate result.

Hard blockers before GO:

- None remaining for GitHub-only `v0.2.0-dev` technical preview after the final
  verification above.
- Keep scope boundary: no PyPI release, no Docker runtime claim, no broad
  multi-case real Abaqus certification, and do not mutate the existing
  `v0.1.0` tag.

## v0.2.0-dev Release Target

`v0.2.0-dev` should be treated as a **technical preview**, not a full production
release.

### Product Claim

Use this claim:

> Local Simulation QA and regression framework for Abaqus FEA. Turn Abaqus
> runs and supplied KPI evidence into reproducible capsules with Physics
> Contracts, Simulation Diff, Solver Doctor diagnostics, and deliverable
> reports.

Do not claim:

- SaaS-hosted Abaqus execution,
- PyPI availability,
- Docker runtime smoke in the current Mac shell,
- broader real Abaqus validation beyond the preserved Windows cantilever
  `--require-real` PASS bundle,
- that offline/local demo pack evidence proves real solver execution.

### Minimum GO Criteria

All of these must pass before creating a `v0.2.0-dev` release:

1. **Target commit decided and clean**
   - fetch remote,
   - choose whether current Goal Chain changes become the release commit,
   - commit intentionally or remove them from the release checkout,
   - worktree clean.
2. **Fresh local verification from the target commit**
   - source install with Python 3.11,
   - full `ruff check .`,
   - full `pytest`,
   - `run_benchmark.py --dry-run`,
   - installed `abaqus-agent-local-cli-smoke`,
   - local CLI smoke ZIP verification,
   - copied demo pack ZIP verification.
3. **Fresh real-Abaqus evidence boundary**
   - 2026-06-06 Windows evidence exists at
     `evidence/real_abaqus_smoke_20260606_force_fix_pass/`,
   - `smoke_evidence.json` reports `overall_status=real-env-verified` and
     `real_env_verified=true`,
   - the integrated `contract_diff` stage is completed and real-env verified,
   - the Physics Contract / Simulation Diff verdict is `PASS`,
   - release notes must state this is one real cantilever PASS chain, not broad
     multi-case real Abaqus certification.
4. **Release notes boundary**
   - distinguish real Abaqus evidence from dry-run/mock/offline evidence,
   - if fresh real evidence is unavailable, reference only the preserved
     2026-06-05 real smoke bundle and state that integrated `contract_diff`
     has not been rerun on Windows yet.

### Suggested Tag and Title

Use a new tag after the target commit is clean and approved:

```bash
git tag -a v0.2.0-dev -m "v0.2.0-dev technical preview"
```

Suggested release title:

```text
v0.2.0-dev - Simulation QA evidence preview for Abaqus FEA
```

### Suggested Release Notes Skeleton

Use this only after the GO criteria above pass:

```markdown
## Abaqus Agent v0.2.0-dev

Abaqus Agent is a local Simulation QA and regression framework for Abaqus FEA.
This technical preview focuses on turning simulation runs and supplied KPI
evidence into reproducible engineering evidence: capsule -> KPI -> Physics
Contract -> Simulation Diff -> report.

### Highlights

- Experiment Capsule store with hashed input/artifact provenance.
- Physics Contract evaluator for KPI range, direction, relative-error, and order checks.
- Simulation Diff reports over KPI dictionaries.
- Offline evidence slice and multi-case demo gallery.
- Local no-server CLI smoke with manifest and ZIP verification.
- Solver Doctor diagnostic reports and pattern discovery.
- ODB Lens KPI recipe gallery.
- Real Abaqus smoke harness with explicit dry-run/mock/require-real evidence boundaries.
- Real-smoke contract/diff plumbing for verified ODB KPI evidence.

### Verified In This Release

- Full local test suite: `465 passed, 1 warning`.
- Full ruff: `ruff check .` passed.
- Benchmark dry-run: 5/5 cases `DRY_RUN_PASS`.
- Local CLI smoke: `overall_status=PASS`, 11 steps PASS.
- CLI smoke ZIP verification: `overall_status=PASS`, 4 checked files, nested demo pack verification PASS.
- Demo pack ZIP verification: `overall_status=PASS`, 31 checked files.
- Fresh real Abaqus smoke: `overall_status=real-env-verified`, `real_env_verified=true`.
- Fresh real Abaqus contract/diff: `PASS` / `contracts=PASS` / `diff=PASS`,
  evidence path `evidence/real_abaqus_smoke_20260606_force_fix_pass/`.

### Evidence Boundary

Offline demo gallery and local CLI smoke use supplied KPI fixtures and sample
logs. They do not invoke Abaqus, read ODB files, or prove real solver execution.

Real Abaqus claims are limited to preserved or freshly generated `--require-real`
evidence bundles that explicitly show `real_env_verified=true`.

### Install

PyPI is not published yet. Install from source:

```bash
git clone https://github.com/Tomsabay/abaqus_agent.git
cd abaqus_agent
pip install -e ".[dev,mcp]"
```
```

## Release Boundary

This release path is GitHub-only unless the user separately approves PyPI publishing.

Do not:

- publish to PyPI,
- mutate the existing tag,
- force-push,
- create a release from a dirty or stale checkout,
- claim real Abaqus solver, ODB KPI, or full 7-stage e2e validation from dry-run/mock evidence.

## Preflight

Run these before creating the release:

```bash
cd /Users/zhaoshaofeng/abaqus-agent

git status --short
git ls-remote origin refs/heads/main
gh run list --repo Tomsabay/abaqus_agent --branch main --limit 3
gh release list --repo Tomsabay/abaqus_agent --limit 10
gh api repos/Tomsabay/abaqus_agent/tags --jq '.[0:5] | map({name, sha:.commit.sha})'
```

Requirements:

- local checkout is synced to the intended remote `main`,
- worktree is clean or intentionally committed,
- latest relevant CI is green,
- release `v0.2.0-dev` does not already exist,
- tag `v0.2.0-dev` does not already exist until the approved release action,
- existing tag `v0.1.0` is left untouched.

If local `main` is behind remote or the worktree is dirty, stop and resolve that first. Do not create a release from the current local dirty Goal Chain checkout.

## Local Verification

Use Python 3.11. The default `python` command is absent in the latest local audit.

```bash
/tmp/abaqus-agent-audit-venv/bin/python -m pip install -e ".[dev]"
/tmp/abaqus-agent-audit-venv/bin/abaqus-agent-local-cli-smoke \
  --out-dir /tmp/abaqus-agent-release-cli-smoke --json
/tmp/abaqus-agent-audit-venv/bin/python -m pytest
/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .
/tmp/abaqus-agent-audit-venv/bin/python run_benchmark.py --dry-run
```

The installed no-server CLI smoke should exit 0, write
`local_cli_smoke.json`, `local_cli_smoke.md`, `local_cli_smoke.html`,
`local_cli_smoke_manifest.json`, and `local_cli_smoke.zip`, and report
`overall_status=PASS` with 11 smoke steps `PASS`. The ZIP should include
`copied-local-demo-pack.zip` plus the smoke manifest, whose entries record file
sizes and SHA-256 hashes. The copied demo pack ZIP should also contain
`local-demo-pack-manifest.json` with bundled demo artifact sizes and SHA-256
hashes. Verify a copied or received demo pack ZIP with
`/tmp/abaqus-agent-audit-venv/bin/abaqus-agent-verify-local-demo-pack
/tmp/abaqus-agent-release-cli-smoke/copied-local-demo-pack.zip --json`, or verify
a stored demo pack vault entry with
`/tmp/abaqus-agent-audit-venv/bin/abaqus-agent-vault --root <vault-root>
verify-demo-pack <vault-id>`. Verify
the smoke ZIP with
`/tmp/abaqus-agent-audit-venv/bin/abaqus-agent-verify-local-cli-smoke
/tmp/abaqus-agent-release-cli-smoke/local_cli_smoke.zip --json`; the verifier
should return `copied_demo_pack_verification.overall_status=PASS` for the nested
copied demo pack. It uses
supplied KPI fixtures and sample log text only; it does not start FastAPI/MCP,
invoke Abaqus, read ODB files, or prove real solver execution.

If a real Abaqus machine is available, also run:

```bash
/tmp/abaqus-agent-audit-venv/bin/python scripts/run_real_abaqus_smoke.py \
  --require-real --json --out-dir /tmp/abaqus-agent-real-smoke
```

Only include real Abaqus claims in release notes if `--require-real` succeeds against a visible executable/license and the evidence bundle confirms `real_env_verified=true` for the relevant stages.

## Repository Metadata

Expected repository metadata:

```bash
gh repo edit Tomsabay/abaqus_agent \
  --description "Local simulation QA and regression framework for Abaqus FEA"

gh repo edit Tomsabay/abaqus_agent \
  --add-topic abaqus,fea,finite-element-analysis,mcp,odb,regression-testing,simulation-devops,cae
```

These values were already observed remotely in the 2026-06-04 audit. Re-run only if GitHub metadata drifts.

## Create GitHub Release

Create `v0.2.0-dev` only after the user explicitly approves the exact target
commit, tag, and release action. Do not reuse or mutate the existing `v0.1.0`
tag.

~~~bash
git tag -a v0.2.0-dev -m "v0.2.0-dev technical preview"
git push origin v0.2.0-dev

gh release create v0.2.0-dev \
  --repo Tomsabay/abaqus_agent \
  --title "v0.2.0-dev - Simulation QA evidence preview for Abaqus FEA" \
  --notes "$(cat <<'EOF'
## Abaqus Agent v0.2.0-dev

Abaqus Agent is a local Simulation QA and regression framework for Abaqus FEA.
This technical preview turns simulation runs and supplied KPI evidence into
reproducible engineering evidence: capsule -> KPI -> Physics Contract ->
Simulation Diff -> report.

### Highlights

- Experiment Capsule store with hashed input/artifact provenance.
- Physics Contract evaluator for KPI range, direction, relative-error, and order checks.
- Simulation Diff reports over KPI dictionaries.
- Offline evidence slice and multi-case demo gallery.
- Local no-server CLI smoke with manifest and ZIP verification.
- Solver Doctor diagnostic reports and pattern discovery.
- ODB Lens KPI recipe gallery.
- Real Abaqus smoke harness with explicit dry-run/mock/require-real evidence boundaries.
- Real-smoke contract/diff plumbing for verified ODB KPI evidence.

### Verified In Current Audit

- Local verification: <fill in final target-commit pytest/ruff results>.
- Benchmark dry-run: <fill in result>.
- Local CLI smoke and ZIP verification: <fill in result>.
- Fresh real Windows Abaqus cantilever smoke:
  `overall_status=real-env-verified`, `real_env_verified=true`.
- Fresh real Windows Abaqus contract/diff:
  `PASS` / `contracts=PASS` / `diff=PASS`.
- Real evidence path:
  `evidence/real_abaqus_smoke_20260606_force_fix_pass/`.

### Not Yet Claimed

- Real Abaqus executable/license validation on the local Mac.
- Broad multi-case real Abaqus certification.
- No-server CLI smoke as proof of real Abaqus execution. It is offline/local
  product evidence over supplied fixtures and sample logs.
- Docker runtime smoke in the latest local shell.
- PyPI distribution.

### Install

PyPI is not published yet. Install from source:

```bash
git clone https://github.com/Tomsabay/abaqus_agent.git
cd abaqus_agent
pip install -e ".[dev,mcp]"
```

Useful installed no-server commands after source install:

```bash
abaqus-agent-local-cli-smoke --out-dir /tmp/abaqus-agent-local-cli-smoke --json
abaqus-agent-verify-local-cli-smoke /tmp/abaqus-agent-local-cli-smoke/local_cli_smoke.zip --json
abaqus-agent-vault --root /tmp/abaqus-agent-local-cli-smoke/evidence-vault verify-smoke <local-cli-smoke-vault-id>
abaqus-agent-vault --help
abaqus-agent-case-memory --help
abaqus-agent-kpi-recipes --help
abaqus-agent-doctor-patterns --help
```
EOF
)" \
  --latest
~~~

## Post-Release Verification

```bash
gh release view v0.2.0-dev --repo Tomsabay/abaqus_agent
gh run list --repo Tomsabay/abaqus_agent --branch main --limit 1
curl -fsSL https://api.github.com/repos/Tomsabay/abaqus_agent/releases/tags/v0.2.0-dev
```

Record the release URL and any remaining limitations in `docs/goal_driver/CURRENT_STATE.md` and `docs/goal_driver/CODEX_HANDOFF.md`.

## Optional Follow-Ups

- Decide whether to publish to PyPI now or defer to `v0.2.0-dev`.
- Run Docker compose smoke on a Docker-capable machine.
- Add more real Abaqus cases, especially `custom_inp`, before claiming broad real-case coverage.
