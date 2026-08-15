# Roadmap

This is a statement of direction, not a set of promises with dates. It is a
one-person project; items move when the evidence for them exists.

One rule governs everything below, and it is worth stating first because it
explains why the list is shorter than you might expect:

> **A capability ships as "supported" only when a real solver run proves it.**
> Not when the code path exists, not when the keyword is documented upstream.
> The gate is a passing item in `scripts/run_*_check.py`, and its output is
> committed as evidence.

What "committed as evidence" means, precisely, because it was overstated here
until 2026-08-06: `evidence/gates/*.json` carries each gate's item ids, its
pass or fail, the identity each item checks, the numbers it measured and the
Abaqus release it measured them on. It does not carry the solve — no `.odb`,
no `.dat`, no geometry. One measured run directory is 178 MB, and the raw JSON
carries the run machine's absolute paths, so what is published is the
reduction `scripts/collect_gate_evidence.py` performs, by field allowlist. The
harness that produces it is published too: an unpublished harness is an
unfalsifiable claim.

The reason is specific rather than pious. `elemShape=HEX` on a body with no
hexes in it is accepted by Abaqus: it meshes nothing, raises nothing, and the
job completes. A cut whose holes miss the solid removes nothing and returns 0.
Anything that trusts an exit code, or trusts that a feature works because the
manual lists it, will eventually report a confident wrong number — which in
this domain is worse than an error.

## Where it stands today

**Abaqus backend** — the full pipeline: natural language to spec, spec to model,
solve, KPI extraction from the ODB, physics contracts, regression against frozen
baselines, report and capsule export. Verified against theory on the shipped
cases.

**The model layer** — a spec describes `parts`, `assembly`, `interactions`,
`steps` and `conditions`, and names the Abaqus method it wants rather than
picking from a closed list: `getattr(obj, spec["call"])(**kwargs)`. That is what
makes multi-part models with contact, ties, connectors, patterns and booleans
reachable at all — an enumerated schema could only build the shapes somebody had
already written a branch for, and Abaqus exposes 292 callables on `Part` alone.
What generic dispatch gives up is a schema that knows what each call was
supposed to produce, so `expect:` blocks replace it and are checked against the
built model: geometry counts and volume, element count and shape quality, where
each instance landed, the measured gap between a contact pair. Five worked cases
ship in the dialect — `bearing_block`, `two_plate_tie`, `two_plate_contact`,
`block_friction_slide`, `plate_hole_v2` — with `scripts/run_generic_*_check.py`
as their gates and the summaries under `evidence/gates/`.

The selector layer is part of this and is worth stating separately, because it
is where a wrong answer would otherwise come from: a spec says
`Bolt:face@y=min` rather than an index into a list Abaqus is free to reorder,
and every selector carries a count assertion, so picking the wrong face is a
refusal instead of a load applied somewhere plausible.

**One solver, and it is Abaqus.** A CalculiX fallback shipped 2026-08-01 and
was removed 2026-08-15, together with the demo walkthrough that ran when no
solver was found at all. Both were removed for the same reason: someone with no
Abaqus is not a user of an Abaqus workbench, and serving them cost a capability
matrix — a per-feature statement of what a second solver could be trusted with —
that had to be kept honest forever. Without Abaqus the run is now refused, in
one sentence that names the environment variable to set.

The parts of that work which were never about CalculiX all stayed: no numeric
KPI is produced without a solver behind it; a KPI whose definition differs from
Abaqus is tagged with its provenance and excluded from pass/fail rather than
graded against a baseline it does not mean the same thing as; and a refusal
names the spec field it is refusing.

**Interfaces** — HTTP server with a single-file workbench frontend, and an MCP
server so an LLM client can drive it directly.

## Next

**A free mesher for curved geometry.** Every mesher in this project currently
lives inside `abaqus cae noGUI`. Nothing depends on that today, but it is the
one part of the pipeline with no in-process alternative, which makes it the
first thing to break if the geometry path ever has to run outside CAE.

**More case archetypes.** Each with a frozen baseline and a physics contract,
which is the only way one gets to be called supported.

## Later

- Deeper capsule provenance, so a result can be replayed and audited years on.

## Not planned

- **Bundling or auto-downloading a solver.** No solver ships with this, and no
  installer will fetch one. The user installs what they are entitled to
  install; this project locates and invokes it. See `NOTICE`.
- **A second solver backend.** Tried, measured, removed — see above. Reopening
  it means committing to a capability matrix maintained forever, and the reach
  it buys is not reach this project wants.
- **Approximating a refused feature.** If a thing cannot be done faithfully,
  the answer is a refusal with a reason, not a nearby number.
- **A licence-key feature gate.** There was one; it was removed when the project
  moved to AGPL. Every feature in the repository is in every copy of it.
  Commercial licensing (`LICENSING.md`) removes copyleft obligations; it does
  not unlock code.
