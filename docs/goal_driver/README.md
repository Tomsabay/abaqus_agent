# Goal Driver Workflow

This project uses Goal Driver to keep Codex execution scoped, reviewable, and project-isolated.

## Roles

- The ChatGPT Project / Pro strategy thread is the planning, goal-splitting, review, and state-compression source.
- Codex `/goal` executes one bounded, verifiable engineering ticket at a time.
- The user confirms tasks, confirms merges, and confirms when to enter the next step.

## Operating Loop

1. The strategy source produces or implies a goal that can support about 45-90 minutes of Codex work.
2. If the user says `/goal 继续推进项目`, Codex reads the Pro/local strategy sources, chooses one highest-value repo-local product ticket, briefly rewrites it into a concise complete goal, then executes it unless it is risky, unclear, or conflicting.
3. Codex executes only the current goal, runs the requested checks or smallest credible verification, writes a handoff, and stops.
4. The user pastes `CODEX_HANDOFF.md` or the final summary into the matching ChatGPT Project / Pro strategy thread when needed.
5. The strategy source reviews the result and proposes the next `/goal`.
6. Codex does not start the next ticket unless the user explicitly gives a new budget and asks for consecutive tickets.

## Hard Boundaries

- Codex must not automatically open ChatGPT App.
- Codex must not automatically talk to the Pro strategy thread.
- Codex must not autonomously continue into the next phase.
- Project state must not be mixed across repositories or ChatGPT Projects.
- All state in this directory belongs only to the project in `PROJECT_ID.md`.

## Files

- `PROJECT_ID.md`: project identity and boundary.
- `GOAL_CHAIN.md`: short-ticket strategy and execution boundaries.
- `CURRENT_STATE.md`: compressed project state.
- `DECISION_LOG.md`: important decisions.
- `CODEX_RUN_LEDGER.md`: Codex run ledger.
- `NEXT_TICKETS.md`: candidate future goals.
- `CODEX_HANDOFF.md`: current or latest handoff.
- `GOAL_PROGRESS.md`: short progress for the active goal.
- `TICKET_TEMPLATE.md`: reusable `/goal` template.
