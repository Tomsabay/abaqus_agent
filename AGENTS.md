# Abaqus Agent Project Rules

These rules apply inside `/Users/zhaoshaofeng/abaqus-agent`.

## Project

- Project: `abaqus-agent`
- Domain: Abaqus FEA simulation QA / regression / evidence agent.
- Project identity source: `docs/goal_driver/PROJECT_ID.md`.
- Do not mix state, tickets, plans, or handoffs from other projects into this repo.

## Global Rules

- Also honor `/Users/zhaoshaofeng/AGENTS.md`.
- Communicate concisely in Chinese by default.
- Before guessing recurring Abaqus context, check the migrated Codex memory.
- Never expose plaintext secrets. Use Keychain-backed secret references only.
- Do not commit, push, publish, release, merge, or run real external side effects unless the user explicitly asks.

## Strategy Source

- Product strategy comes from the ChatGPT Project `Abaqus Agent - Goal Driver` / Pro strategy thread plus local strategy files:
  - `docs/goal_driver/GOAL_CHAIN.md`
  - `docs/goal_driver/CURRENT_STATE.md`
  - `docs/goal_driver/DECISION_LOG.md`
  - `docs/goal_driver/NEXT_TICKETS.md`
  - latest `docs/goal_driver/CODEX_HANDOFF.md`
- Codex executes repo-local engineering tickets. It does not invent product strategy.
- If strategy is unclear, stale, or conflicts with repo evidence, stop and ask for Pro/user direction instead of improvising.

## `/goal` Policy

- Use `/goal` for one bounded, verifiable engineering ticket.
- Default target size: 45-90 minutes, not multi-hour rolling execution.
- A valid goal must have:
  - objective
  - allowed scope
  - forbidden scope
  - acceptance criteria
  - test commands or smallest credible verification
  - stop condition
- If the user says `/goal 继续推进项目`, treat it as shorthand for:
  - read the Pro/local strategy sources
  - choose one highest-value repo-local product ticket
  - rewrite the shorthand into a complete concise goal ticket before editing
  - execute only that ticket
  - verify it
  - stop with a short handoff
- Before executing a shorthand goal, briefly show the refined goal text in the conversation: objective, scope, acceptance criteria, verification, and stop condition. Then proceed unless the refined goal is risky, unclear, or conflicts with the strategy.
- Do not automatically start another ticket after finishing one unless the user explicitly gives a new budget and asks for consecutive tickets.

## Scope And Cost Control

- Prefer product-visible, runnable evidence: demo flow, verification command, frontend action, report artifact, API/MCP surface, or real-validation enabler.
- Avoid low-value work: ledger grooming, claim polish, repeated status scans, broad cleanup, and documentation churn unless it protects a concrete product slice.
- Keep reads narrow. Do not repeatedly open huge progress/ledger files.
- Do not append long historical narratives to Goal Driver docs.
- Stop if the work would require broad refactoring, unclear strategy, real Abaqus, Docker, publishing, credentials, account permissions, or commit/push/merge without explicit approval.

## Testing

- Test changed behavior with real execution evidence.
- For runtime code, run focused tests plus full `ruff check .` / full pytest when risk justifies it.
- For docs-only or static-contract changes, `git diff --check` plus a focused source/static check is enough unless nearby behavior changed.
- Stop after 2 consecutive test failures on the same issue and report the blocker.

## User-visible Evidence

- Every product ticket should end with evidence from the user's point of view, not just internal test logs.
- For frontend/UI changes, run the app when practical and provide a screenshot set showing the changed flow, key before/after state, or final user-visible result.
- For CLI/API/report changes, provide the command or endpoint used plus the generated report/HTML/ZIP/artifact path that a user can inspect.
- If screenshots cannot be captured because browser tooling is unavailable, state that and provide the smallest credible alternate visual/static evidence.

## Handoff

- For normal work: concise final reply with files changed and verification.
- For `/goal`: update `docs/goal_driver/CODEX_HANDOFF.md` with a short handoff:
  - ticket completed
  - files changed
  - verification
  - user-visible evidence / screenshots
  - blockers / next decision
  - paste-ready Pro summary under 1000 Chinese characters
