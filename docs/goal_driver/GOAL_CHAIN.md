# GOAL_CHAIN

## Purpose

Keep Codex aligned with the Pro strategy while preventing expensive, open-ended
autonomous runs. Goal Chain is now a short-ticket workflow, not an overnight
project autopilot.

## Roles

- Pro strategy thread: product strategy, user/market/launch priority, roadmap judgment.
- User: approves strategy changes, budgets, external side effects, and publishing.
- Codex: executes one repo-local engineering ticket at a time with verification.

## Current Strategy Source

- ChatGPT Project: `Abaqus Agent - Goal Driver`
- Pro thread: `Abaqus Agent 项目战略`
- Local files:
  - `docs/goal_driver/CURRENT_STATE.md`
  - `docs/goal_driver/DECISION_LOG.md`
  - `docs/goal_driver/NEXT_TICKETS.md`
  - latest `docs/goal_driver/CODEX_HANDOFF.md`

## Product Position

AbaqusAgent is an Abaqus FEA simulation QA / regression / evidence agent. The
strategic product directions are subordinate to one main product workflow:

> existing `.inp` or spec -> real Abaqus run -> ODB KPI extraction -> Physics
> Contract pass/fail -> Simulation Diff vs previous run -> deliverable report.

The product should become strong on this workflow before expanding sideways.
Supporting capabilities are:

- Experiment Capsule
- Physics Contract
- ODB Lens / KPI DSL
- Solver Doctor
- Simulation Diff
- Case Memory
- offline / portable evidence
- real Abaqus smoke/evidence validation when a real environment is available

These capabilities are not equal-priority product lines. They should be selected
only when they directly strengthen the main workflow above, remove friction from
it, or produce customer-visible proof that it works.

Do not reposition the product without Pro/user approval.

## Environment Boundary

- The local Mac shell alone does not prove real Abaqus execution.
- Real Abaqus evidence is valid only when it comes from an explicitly verified
  licensed Abaqus environment, such as the Tailscale-connected Windows machine
  with preserved command output, logs, ODB/KPI artifacts, and screenshots.
- Dry-run, mock-real, source-supported, and offline fixture evidence must not be
  described as real Abaqus validation.
- Docker, PyPI, GitHub release, commit/push/merge, credentials, account
  permissions, and public publishing require explicit user approval.

## Default `/goal 继续推进项目` Behavior

When the user sends a shorthand such as `/goal 继续推进项目`:

1. Read only the strategy/current-state files needed to choose one ticket.
2. Choose one highest-value repo-local product ticket from the strategy.
3. Rewrite the shorthand into a complete concise goal ticket and show it before
   editing. Include:
   - objective
   - allowed scope
   - forbidden scope
   - acceptance criteria
   - verification commands
   - stop condition
   - expected user-visible evidence
4. Execute only that ticket unless the refined ticket is risky, unclear, or
   conflicts with the Pro strategy; in that case stop and ask for direction.
5. Verify changed behavior.
6. Capture user-visible evidence.
7. Update a short handoff.
8. Stop.

Default time budget: 45-90 minutes. Do not run a multi-hour chain unless the
user explicitly gives a new budget and asks for consecutive tickets.

## Ticket Selection

Ticket selection must favor depth in the main workflow over breadth in adjacent
features. A good ticket should make this path stronger, faster, more reliable,
or more convincing to a real Abaqus user:

`existing .inp/spec -> real run -> ODB KPI -> contract -> diff -> report`.

Priority order:

1. Real workflow execution: run or harden real Abaqus cases, especially
   `custom_inp`, benchmark cases, compare_expected, contract checks, ODB KPI,
   and report generation.
2. Customer-facing workflow proof: one-command real/offline command that a user
   can run and inspect, with clear PASS/FAIL and report artifacts.
3. Core deterministic kernel: ODB Lens/KPI DSL, Physics Contract semantics,
   Simulation Diff, capsule provenance, and Solver Doctor only when tied to the
   main workflow.
4. Usability around the main workflow: minimal CLI/report/frontend affordances
   that reduce friction for the core run/check/diff/report path.
5. Platform parity, extra UI polish, demos, MCP/API expansion, vault browsing,
   and documentation cleanup only after the core workflow has become stronger
   or when they unblock a real user evaluation.

Prefer work that creates or protects user-visible product evidence on the main
workflow:

- one-command demo / verification flow
- frontend/CLI action that exposes the main workflow's value
- portable report or ZIP artifact
- API/MCP surface only when needed by a real workflow
- real-validation enabler tied to real Abaqus or user-supplied `.inp/.odb`

Avoid:

- adding side features before the run/KPI/contract/diff/report workflow is
  stronger
- status-only tickets
- repeated repo scans
- ledger/doc bloat
- broad refactors
- low-impact wording polish
- frontend/MCP/API parity work that does not improve the main workflow
- new gallery/demo-pack/report variants that only package existing offline proof
- repeated full verification when a focused check is sufficient

## Cost Control

- Keep progress notes short.
- Do not repeatedly read or append huge `GOAL_PROGRESS.md` / `CODEX_RUN_LEDGER.md`
  histories.
- For docs-only/static changes, prefer `git diff --check` and a focused source
  check.
- For runtime changes, run focused tests first; run full ruff/pytest only when
  behavior or shared contracts changed.
- Stop after 2 consecutive test failures on the same issue.
- Stop before spending a large new budget if the next step is not clearly
  product-visible or strategically necessary.

## User-visible Evidence

Each ticket must produce evidence a user or buyer can inspect.

- Frontend/UI tickets: run the app when practical and capture a small screenshot
  set showing the changed user flow or final visible result.
- CLI/API/report tickets: provide the exact command or endpoint plus generated
  artifact paths, such as Markdown, HTML, ZIP, JSON, or vault entry.
- If browser/screenshot tooling is unavailable, state that and provide the
  closest credible alternate evidence: static source probe, served HTML check,
  downloaded artifact, or command output summary.
- Do not count internal ledger updates as user-visible evidence.

## Final Handoff

For each `/goal`, write a compact `docs/goal_driver/CODEX_HANDOFF.md`:

- completed ticket
- files changed
- verification run
- user-visible evidence / screenshots
- blockers / decisions needed
- paste-ready Pro summary under 1000 Chinese characters

Do not append long historical narratives. Keep old detail in git history, not in
the active prompt surface.
