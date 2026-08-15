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

The reason is specific rather than pious. CalculiX, given a load card it does
not recognise, silently drops the card, exits 0, and hands back a model with
every displacement equal to `0.000000E+00`. A blast-loading deck "completed
successfully" that way during development. Anything that trusts an exit code,
or trusts that a feature works because the manual lists it, will eventually
report a confident wrong number — which in this domain is worse than an error.

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

**CalculiX fallback** — for the majority of visitors who do not have an Abaqus
licence. It is deliberately narrow. As of now it covers:

| | Supported |
|---|---|
| Geometry | `cantilever_block`, `custom_inp` |
| Analysis | `Static` |
| Loads | `concentrated_force` |
| KPIs | nodal displacement, field min, max reaction force (all readable at a named set); field max and derived stress concentration (**whole model only**) |

Everything else is **refused before the run**, naming the offending spec field
in plain language. Two gates do that, because they read different things and a
spec field is not always what the solver will run: the capability matrix reads
the spec, and a card-by-card whitelist reads the deck. For
`geometry.type: custom_inp` the deck *is* the model and the spec has no field
that could describe its procedure, so only the second one can see a
`*FREQUENCY` step. Until 2026-08-06 it could not either — the procedure cards
were on the allowlist on the bar "ccx implements it", which is the wrong bar,
and a modal deck came back with a mode shape reported as a tip displacement.
On the shipped cantilever case CalculiX agrees with the Abaqus
baseline to seven significant figures. Its Mises stress does not, and cannot:
CalculiX reports nodal-averaged stress where Abaqus reports unaveraged
`ELEMENT_NODAL`. That number is tagged with its provenance and excluded from
pass/fail comparison rather than quietly graded against an Abaqus baseline.

**Interfaces** — HTTP server with a single-file workbench frontend, and an MCP
server so an LLM client can drive it directly.

## Next

**Widen the CalculiX subset.** Each of these is a separate check-harness item
and lands independently:

- Pressure loads. Blocked on translating Abaqus surface names into CalculiX
  element-face numbering; the translation is not hard, verifying it is the work.
- Modal analysis (`*FREQUENCY`). CalculiX has the keyword, and on the shipped
  modal beam it gets the answer right — 210.24 / 416.36 / 1303.99 Hz against
  the frozen Abaqus 210 / 416 / 1304. It is refused today because one agreeing
  model is not a verification item, and because the mode shapes it writes are
  mass-normalised eigenvectors that the displacement extractor would read as
  millimetres.
- Prescribed displacement boundary conditions.
- Plasticity. Needs a baseline comparison before it can be trusted, since the
  hardening definitions are where two solvers most often quietly disagree.

**A free mesher for curved geometry.** The single largest gap. Every mesher in
this project currently lives inside `abaqus cae noGUI`, so the CalculiX path has
only the pure-Python structured mesher written for it — which is why
`plate_with_hole`, the most-requested tutorial model in existence, is refused on
the fallback backend. Approximating a hole with a structured mesh changes the
stress concentration factor, so refusing is currently the right answer, and the
fix is a real unstructured mesher rather than a fudge.

**Result visualisation without an ODB.** CalculiX writes `.frd`; there is no
contour plot on the fallback path today, only numbers.

## Later

- More case archetypes, each with a frozen baseline and a physics contract.
- Broader solver coverage, if and only if the same evidence bar can be met.
- Deeper capsule provenance, so a result can be replayed and audited years on.

## Not planned

- **Bundling or auto-downloading a solver.** Neither Abaqus nor CalculiX ships
  with this, and no installer will fetch one. The user installs what they are
  entitled to install; this project locates and invokes it. See `NOTICE`.
- **Approximating a refused feature.** If the backend in use cannot do a thing
  faithfully, the answer is a refusal with a reason, not a nearby number.
- **A licence-key feature gate.** There was one; it was removed when the project
  moved to AGPL. Every feature in the repository is in every copy of it.
  Commercial licensing (`LICENSING.md`) removes copyleft obligations; it does
  not unlock code.
