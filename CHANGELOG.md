# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - 2026-08-10

### Changed — the deck oracle could not see the code it is meant to protect

`scripts/record_v2_decks.py` is the proof that a `runner/build_v2.py` refactor
changed nothing: it wraps `generate_script`, runs tests, and hashes every deck
emitted and every refusal raised. Its own docstring says "run the whole
suite". It did not — it ran `tests/test_build*.py` plus
`test_frozen_model_sections.py`, and a fallback line that named a file which
does not exist, so `test_build_v2.py` was passed twice.

Measured with coverage against `runner/build_v2.py`: **64 of 1073 statements
never executed under the oracle's selection, against 39 under the full
suite.** The 25-statement gap was not spread thin — it sat on every branch of
`_refuse_material_rebuild` and `_import_without_an_opener`, most of
`_one_part`, and part of `_dispatch_target`: four of the modules a split of
this file would create. The glob was also a slow leak, since a future
`tests/test_deck_*.py` would not match `test_build*` and would shrink the
oracle silently at exactly the moment new modules got their first tests.

It runs the whole suite now. 390 → 500 recorded calls; comparing the wider run
against the old baseline printed **"0 gone, 73 new"**, which is the shape a
purely additive change should have: no previously recorded deck differs.
Determinism re-checked, because a slow oracle that flaps is worse than a
narrow one — two independent full runs both gave digest `ebef370e331bc5bd`
and compared IDENTICAL, 500 decks byte for byte. Cost: ~15 s → ~2.5 min.

### Fixed — three things the registry move quietly broke or left uncovered

Found by re-auditing the commit above rather than by a failing test, which is
the point: none of these turned anything red.

**The artifact counter stopped resetting between tests.** It used to be a
module-level int, and four fixture lines zeroed it with
`server.EVIDENCE_ARTIFACT_SEQUENCE = 0`. It lives in the registry now, so that
assignment bound a name nothing reads — the counter climbed across the whole
session and every `sequence` the API reported was an arbitrary number instead
of 1, 2, 3. Nothing asserts an absolute sequence, so the suite stayed green.
The fixtures call `EVIDENCE.clear()` now, and
`tests/test_evidence_artifact_registry.py` pins that a clear resets the
counter — proven by making `clear()` skip the counter and watching that test
fail with `assert 3 == 1`.

**`evidence/` was invisible to the file-size gate.** It was in `SKIP_DIRS`
wholesale, so eight source modules were never sized — including
`evidence/real_smoke_contract_diff.py` at 465 lines, and
`evidence/artifact_registry.py`, which was created *by* a split done to
satisfy that gate. The skip existed for the 297 captured solver artefacts
under `evidence/real_abaqus_smoke_*/`; those are still skipped, now by a
named predicate that says so. Nine modules are checked now, all under 800.

**`evidence/` was missing from the subprocess-decoding gate.** That gate
scans production code for text-mode `subprocess` calls without `errors=`, and
it lists `copilot` and `workbench` — the two other route packages — but not
`evidence`. Moving evidence code out of `server.py` would have walked it out
of the gate's field of view. Nothing under `evidence/` shells out today, which
is exactly when a list like this is cheap to correct.

The "what under evidence/ is source" rule now lives once, in
`tests/repo_sources.py`, because two gates need the same answer and they had
already disagreed by omission.

### Changed — the evidence artifact registry existed twice, byte for byte

`server.py` and `mcp_bridge.py` each carried their own copy of the in-process
registry that keeps generated evidence artifacts reachable: 203 lines, ten
functions, identical except for three default `url_prefix` strings — one
serving `/api/evidence/...`, the other `/mcp/api/evidence/...`. Two copies of
a registry is two places to fix a leak and two chances for the record shape
the UI reads to drift.

It is now `evidence/artifact_registry.py`, and the mount point is a
constructor argument. The two callers stay independent exactly as before: an
artifact generated through the bridge is not reachable through the server's
URLs, and clearing one registry does not clear the other.
`EVIDENCE_ARTIFACTS` and `DEMO_GALLERY_ARTIFACTS` still exist in both modules
and are the same dict objects the registry holds, so the test fixtures that
clear them keep working.

The registry does not import FastAPI. A missing artifact raises
`ArtifactNotFound`; the route decides that means 404, with the same two detail
strings as before.

server.py 1726 → 1507 lines, mcp_bridge.py 1281 → 1057.

Verified over real HTTP on both apps: `POST /api/evidence/offline` → PASS,
all five artifact URLs 200, vault record and file 200, demo gallery 4/4 200,
a bad artifact id still 404 "Evidence artifact not found"; the bridge's four
artifacts 200 under `/mcp/api/evidence/demo-gallery/...`; registries verified
separate afterwards.

### Fixed — the diagnosis card on the results page fired on healthy runs

Every Abaqus/Standard `.msg` ends with a tally block, and one of its lines is

```
                       0  ANALYSIS WARNINGS ARE NEGATIVE EIGENVALUE MESSAGES
```

The pattern table matched the bare phrase `NEGATIVE EIGENVALUE`, so a clean run
raised a NUMERICAL warning and the card quoted, verbatim, a line stating the
count was zero. 326 of those lines across this repo's archived runs; every one
of them zero.

Negative eigenvalues are written on four line shapes and three of them carry
their own count. Those three are now matched with the count captured, and only
report when it is not zero. The fourth is the explanatory sentence Abaqus
prints under the warning and is not a finding on its own. The genuine
per-increment warning — `THE SYSTEM MATRIX HAS 2 NEGATIVE EIGENVALUES`, 740
occurrences in the archive — still fires, with its step and increment.

Measured on a real archived `.msg`: 1 NUMERICAL event before, 0 after; a
synthetic genuine warning still yields 1; a nonzero tally still yields 1.

`/api/doctor`'s pattern catalogue now carries `only_when` on a conditional
pattern, because a pattern that fires only under a condition reads as
always-on otherwise.

### Fixed — a stage log line announced "⚠ [] warnings"

`warnings` is one progress key with two meanings: `agent/orchestrator.py` sends
a count, five other sites and the CalculiX orchestrator send a list of texts.
The formatter only handled the count, so a list rendered with its Python repr
on screen, an empty list rendered as `⚠ [] warnings` — a warning banner saying
there were none — and a clean syntax check put `⚠ 0 warnings` on every
successful run. Each text is now its own line, and nothing is emitted for
zero, an empty list or a missing value.

### Changed — a diagnostic pattern's id no longer moves when a pattern is added

The catalogue numbered rows as it emitted them, so a pattern's id encoded its
position: `msg-10-license`. Inserting the two counted eigenvalue patterns above
it renamed it to `msg-12-license` and broke the offline smoke gate, which names
it — as do the Pattern Gallery and three shipped documents. Patterns now carry
a written-down slug (`msg-license`, `dat-license`), and the table is a frozen
`LogPattern` dataclass rather than tuples that were three or four wide
depending on the row.

The ids in `/api/doctor`, `list_doctor_patterns` and
`scripts/inspect_solver_doctor_patterns.py` change shape once, here. Nothing
persists them; the guidance text is keyed by category, not by id.

## [Unreleased] - 2026-08-09

### Fixed — the run id the API reported was never the directory the run was in

`POST /api/run/start` and MCP `start_run` hand back `core.helpers.make_run_id`,
which hashed the **raw YAML text**. The run directory is named by
`runner/build_model._run_id`, which hashes the **parsed spec**. On the shipped
cantilever: API `64f474736b4b2019`, disk `dd6ec1145b8de62f`. Anyone who copied
the id off the workbench to go find the evidence found nothing.

One definition now — `core.helpers.run_id_for_spec` — and both callers use it.
A consequence, and the right one: two spec files differing only in comments,
key order or quoting are one run, because they describe one model. An
unparseable spec still gets an id rather than raising on the way to the
validator that should report the syntax error.

`agent/ccx_orchestrator._run_id` stays deliberately separate and says so: it
mixes in the backend and solver version, which is what keeps a CalculiX run
out of the Abaqus run's cache directory where a frozen baseline lives.

### Fixed — every run started from the UI built in a random temp directory

Found while verifying the above on the real HTTP path. A spec that arrives as
text has no file, so the orchestrator picked its own working directory with
`mkdtemp(prefix="abaqus_run_")`. Measured before the fix, the API returned run
id `dd6ec1145b8de62f` and reported a `workdir` ending in
`Temp/abaqus_run_mbmomka_` — unrelated to the id, so the evidence could not be
found from it; different on every request, so the same spec re-solved from
scratch every time; and `ABAQUS_AGENT_RUN_ROOT` had no effect there at all (a
scratch root came back empty).

The directory is now `<run root>/abaqus_run_<run_id>`, still under the temp
dir when no run root is configured — an ad-hoc spec belongs to no case, and
the repo is not the place for it. Measured after: workdir
`<scratch>/abaqus_run_dd6ec1145b8de62f`, run root honoured.

### Fixed — a run that solved nothing exported a report that read like a real one

`_build_run_report` in `server.py` assembled the report from the run's KPIs,
regression, contracts and stages, and dropped every caveat the run carried:
`demo_mode`, `limitations`, `kpis_missing`, `kpi_notice`, `kpi_provenance`.
`reporting/templates.py` has always known how to render all of them — the demo
banner, the limitations table, the missing-KPI rows — so those branches were
dead on the whole `/api/run/{id}/report.{md,html,pdf,zip}` family.

The demo case was the damaging one. `core/pipeline.py` sets `demo_mode` on the
run and then finishes it as `COMPLETED`, not `DEMO`, so the renderer's status
fallback did not catch it either: a run in which nothing was solved exported
markdown, HTML and PDF with **no demo marking anywhere**. A report is the
artifact that outlives the session and gets mailed to someone who never saw
the screen it was rendered from.

Three tests, all three failing against the pre-fix code.

### Fixed — the two contract loaders disagreed on what a contract is

`contracts/evaluator.py` has always read `contract.get("check") or
contract.get("type")`, and the repo ships both dialects: everything under
`examples/contracts/` says `type:`, `cases/cantilever/contracts.yaml` says
`check:`. `contracts/io.load_contracts` demanded `type:` and so raised
`ValueError` on the only contract file the cases ship — reachable from
`evidence/offline.py` and `evidence/real_smoke_contract_diff.py`, both of
which take that path from their caller. Meanwhile `AbaqusOrchestrator._load_
contracts` parsed the YAML itself and validated nothing.

- One loader now. The orchestrator delegates to `contracts.io`, and contracts
  that arrive as data (embedded in a spec, or passed directly) go through the
  same `normalize_contracts`.
- Both spellings are accepted and normalized so either key can be read.
- A contract naming **neither** is now refused. It used to be accepted, and
  the evaluator's `.get("type", "range")` default then quietly made it a range
  check against whatever `min`/`max` the contract happened not to have.

### Fixed — nine verification gates existed that nothing ever ran

`scripts/run_all_real_checks.py` is the one command that produces a verdict
for the whole engine, and its `GATES` list is hand-maintained. Three separate
comments in that file record the same discovery — a gate written and never
registered, found by accident while adding an unrelated one — and there were
still nine unlisted: `assembly_preview`, `error_gallery`, `frontend_coherence`,
`i18n_static`, `i18n_ui`, `readme_quickstart`, `version_selector_ui`,
`workbench_browser`, `workbench_real`.

All nine are registered and were run through the harness: all PASS. Getting
there surfaced three more defects, none of which a hermetic test could see:

- **Seven of the nine printed no verdict the harness could read.** It reads
  one JSON object carrying `result` or `overall`; those gates printed only
  `RESULT: PASS`. Registering them as-is would have entered seven green gates
  into the summary as UNREADABLE, i.e. FAIL.
- **The reader required its payload to be the last byte of stdout.**
  `run_workbench_browser_check.py` prints an `evidence -> <path>` line after
  its JSON, so it was reported as "printed no JSON object" on a run whose
  payload said `"overall": "PASS"`. It now decodes each object where it
  starts and keeps the last one, which also lets a gate print an interim
  payload before its verdict.
- **`run_i18n_ui_check.py` needed `--serve` to work at all**, and the harness
  runs every gate as `python <script>` with no arguments. Serving is now the
  default, on a free port — a fixed one either collides with a server already
  running or, worse, silently checks that other server. `--no-serve --port N`
  attaches to one you started yourself.

`tests/test_gate_registry.py` closes the class: a gate script that exists and
is not registered fails, as does a registry entry pointing at a missing file,
a duplicate gate name, and a registered gate that never names `result` or
`overall`. That last test caught four gates during this change.

### Fixed — with `/static/i18n.js` missing, every label on both pages read as a raw key

Each page carries a small stand-in for the shared i18n engine, so that a
`<script>` which fails to load costs the language switch rather than every
event handler on the page. The stand-in's `register()` did `d = c || {}` — an
assignment. Both pages call `register()` twice: once for the page catalogue,
then again from `loadBackendMessages()` on boot with the strings the server
composes. The second call therefore threw the entire catalogue away.

Measured in Chromium against the pre-fix code, with `/static/i18n.js`
returning 404: **24 labels on `/` and 14 on `/workbench` rendered as their raw
keys** (`copilot.btn.execute`, `onboard.card1.title`, …).

- `scripts/run_i18n_ui_check.py` had a case for exactly this scenario and
  called it green throughout, because it asked "is there still Chinese on
  screen" — and the server-composed strings that had replaced the catalogue
  are Chinese too. It now asserts no raw key is on screen in the degraded
  state, which is the question that distinguishes the two.
- That leak check no longer guesses. It used to exclude dotted tokens by file
  extension, which both missed real keys and flagged `mdb.models.keys` from a
  seeded example prompt; it now flags a token only if its first segment is a
  namespace this page's catalogue actually uses — still catching a key built
  at runtime as `t('grade.' + verdict)`, which whole-key matching would not.
- Evidence: the strengthened gate fails against the pre-fix stand-in with the
  counts above and passes after (`RESULT: PASS`, both pages). A hermetic test,
  `test_the_stand_in_merges_catalogues_rather_than_replacing`, fails on both
  pages pre-fix without needing a browser.

### Changed — `server.py` was 2249 lines with 71 routes; it is now 1725 (#85)

The 21 `/api/copilot/*` routes moved to `copilot/routes.py` (577 lines), and
the session store they own moved with them — `COPILOT_SESSIONS`, its on-disk
mirror, the persistence and rehydrate-at-import helpers, and the five request
models. A group of routes that leaves its own state behind is not a module.
`workbench/routes.py` already proved the `APIRouter` pattern; this is the same
shape. All 20 route paths compared before and after: none lost, none added.

Two things the move would have broken silently, both caught by checking:

- **`Path(__file__).parent` meant the repo in `server.py` and means `copilot/`
  here.** Four sites: the replay recordings directory, and the `root=` argument
  to the release gate and to the alpha packager, twice. They now go through an
  explicit `REPO_ROOT`.
- **Re-exporting `COPILOT_SESSION_FILE` from `server.py` would have been a
  trap.** It is a `Path`, so a test that rebinds `server.COPILOT_SESSION_FILE`
  leaves the routes reading the original — green setup, wrong file. Only
  `COPILOT_SESSIONS` is re-exported, because it is a dict and both names point
  at the same object; everything else is patched where it lives.

Evidence: full suite 2591 passed, 1 skipped. Eight `/api/copilot/*` endpoints
driven against a live `server.py`, all 200 with the right payload shapes,
including the three that depend on `REPO_ROOT` — the replay recording loads,
the release gate returns its checks, and the alpha package is a valid 13.6 KB
zip. Publish tree check: PASS.

### Changed — `frontend/index.html` was 7029 lines; it is now 4399 (#85)

Same split as the workbench, on the bigger of the two pages:

| file | lines | what it is |
|---|---|---|
| `frontend/index.html` | 4399 | markup and behaviour |
| `frontend/index.css` | 1968 | the tools-page stylesheet |
| `frontend/index_i18n.js` | 672 | the zh/en catalogue |

A pure move: both extracted files are byte-for-byte substrings of the
committed original, and the load order is preserved — `design-system.css`
then `index.css`, and the catalogue script above the behaviour that calls
`t()`. Still over the 800-line rule; the behaviour splits next by panel
(copilot, evidence, doctor, bench), which is real surgery rather than a lift.

- Twelve tests went red on the move and none of them were wrong to: they read
  `index.html` as one file and the markers they guard had moved into the
  stylesheet and the catalogue. Repointed at `tests/frontend_sources.py`,
  which is the reason that helper exists.
- Verified in Chromium against the running server: both stylesheets parsed
  (34 + 287 rules), no page errors, no failed requests, `page.title` rendering
  from the catalogue as 「Abaqus Agent · 工具台」, and a screenshot showing the
  three-column layout, the 3D viewport and every panel intact.

### Changed — `frontend/workbench.html` was 3615 lines; it is now 2292 (#85)

Markup, stylesheet, translation catalogue and behaviour in one file:

| file | lines | what it is |
|---|---|---|
| `frontend/workbench.html` | 2292 | markup and behaviour |
| `frontend/workbench.css` | 966 | the workbench stylesheet |
| `frontend/workbench_i18n.js` | 379 | the zh/en catalogue |

Still no build step. These pages ship inside a frozen `.exe` and run on
air-gapped workstations, so assets are served as-is from `/static` and the
packaging spec copies `frontend/` wholesale — a new file needs no change on
either path, and `test_every_asset_the_workbench_asks_for_is_actually_served`
fails if one stops being reachable.

- Tests that read a page as text go through `tests/frontend_sources.py` now.
  A page is its markup plus what it loads; a test that keeps reading only the
  `.html` does not fail loudly, it quietly stops finding what it guards and
  reports PASS about a rule it no longer checks.
- Two guards had already become that: `test_no_page_declares_its_own_token_
  vocabulary` and `test_no_external_font_or_asset_requests` checked only the
  markup, so a second `:root` block or an `@import` of a webfont could enter
  through the stylesheet — the file most likely to grow either. Both now read
  every file a page is built from and name the offending one; verified by
  appending both violations to `workbench.css` and watching them fail.
- `scripts/run_i18n_static_check.py` follows the catalogue to its new file
  rather than checking a page it would now find no catalogue in at all.

### Changed — `runner/build_v2.py` was 6021 lines; it is now 2810 (#85)

One file held the spec compiler, the element lookup tables, the argument
grammar, the preview payload, and 1777 lines of Python 2.7 for the Abaqus
kernel. Nobody decided that — it accreted a commit at a time. Split along the
seams that were already there:

| module | lines | what it is |
|---|---|---|
| `runner/build_v2.py` | 2810 | the deck emitters and `generate_script` |
| `runner/kernel_runtime.py` | 1837 | the py2.7 the kernel runs, in 7 named chunks |
| `runner/arg_forms.py` | 693 | the value forms an API argument may take |
| `runner/preview.py` | 611 | the JSON the 3D preview reads |
| `runner/mesh_policy.py` | 231 | element / shape / technique tables |
| `runner/spec_base.py` | 26 | `SpecError`, `_parse`, `_is_generic` |

- **Proven a pure move, not argued to be one.** `tests/test_frozen_model_
  sections.py` hashes each shipped deck only from `# --- Materials` onward,
  deliberately, because the preamble grows whenever a check is added — so it
  cannot see a change to the thing being moved here. `scripts/record_v2_decks.py`
  wraps `generate_script`, runs the build suite, and hashes **every one of the
  390 decks it produces** plus every refusal it raises. Every step of this
  split reproduced digest `8a3376d5` exactly.
- Building that oracle turned up a defect in it first: two runs of an
  *unchanged* tree gave different digests (`82f8d2ec`, `ac6cbc91`). Twelve
  geometry-import decks embed pytest's `tmp_path` counter (`pytest-676` vs
  `pytest-677`) through the opener's `fileName`, and one refusal message did
  too. Both are scrubbed before hashing; the oracle self-checks by comparing an
  unchanged tree against itself.
- `_HELPERS` is split into seven topical chunks (54–420 lines) for navigation
  only. `tests/test_kernel_runtime.py` pins the concatenation, the chunk order,
  and that the list is not stale — a chunk defined but never concatenated fails
  rather than silently vanishing from every deck.
- Test references were repointed at the new modules rather than left working
  through a re-export facade. A facade would have kept `build_v2.X` resolving
  and defeated the point: a reader could still not tell where anything lives.
- `tests/test_module_sizes.py` makes the 800-line rule a test. It found 14
  files over the limit that this change did not create; each is listed with a
  ceiling at its current size and a stated reason, so a listed file that
  *grows* fails. Two categories are exempt by pattern with the reason given
  once: gate scripts (must run standalone on a machine that has Abaqus) and
  test files (a list of independent cases, not one program).

### Fixed — the grading layer never ran on any path a user walks (#84)

- **`core/pipeline.py` built the orchestrator without `expected_path` or
  `contracts_path`.** `AbaqusOrchestrator` compares KPIs only `if
  self.expected`, so every run started through that module — workbench Accept,
  `POST /api/run/start`, MCP `start_run`, and the benchmark loop — finished
  with `regression: {}` and `contracts: {}`. Measured on the real HTTP path
  before the fix: `COMPLETED`, two KPIs on screen, both verdict fields empty.
  The 2532-test suite passed in that state; nothing asserted the wiring.
- **The benchmark also discarded the case's own `runner.json`** (`runner_cfg:
  {}` fell through to the orchestrator's bare defaults — cpus=1, timeout
  1800s — which no shipped case uses), and never passed `expected.json`,
  so per-case `regression` and `contracts` were empty by construction.
- **"Not compared" is now distinct from "passed", everywhere.**
  `_stage_no_baseline` records `passed: null` with the reason instead of
  leaving `{}`; `_stage_contracts` with zero contracts stops reporting
  `{"passed": true, "results": []}` — that was 11 of the 12 shipped cases, and
  `case_memory` indexed all of them as contract-passing runs.
- The report honours the verdict written **on top of** the comparisons. A run
  blocked by dat-integrity keeps every comparison at `PASS` on purpose —
  equilibrium holds however the load gets carried — and only `regression.
  passed` goes False; `_regression_status` derived its answer from the
  comparisons alone and printed `Regression: PASS`, re-asserting the exact
  claim `_block_regression_on_integrity` exists to withdraw.
- The workbench grows a verdict block. It previously rendered none at all
  (`regression.passed === false` was read only to decide whether to open the
  diagnosis panel), so three different runs looked identical on screen: one
  whose every KPI matched, one with no baseline, one whose contracts were
  never loaded. `regression` and `contracts` now also survive into the session
  record, so an archived run does not lose its verdict when RUNS empties.
- A `passed: null` stage no longer renders as a red `FAIL`, and no longer
  spins at "running" forever (the terminal test was `passed is not None`).
- Evidence: 14 new hermetic tests, **8 of which fail against the pre-fix
  code**; `scripts/run_grading_ui_check.py` (registered as `grading_ui`,
  10 items, real Chromium) pins the three states apart and guards the two that
  must not be swallowed by the new amber one. Real Abaqus, cantilever through
  the fixed benchmark path: 2 KPI comparisons ran (PASS/PASS), 3 physics
  contracts evaluated (all PASS). Real HTTP `POST /api/run/start`, same spec
  with no case dir: `NOT GRADED` with the missing input named.

### Fixed — the results viewport drew an assembly that did not exist (#81)

- **A node label is not a key.** Every part instance in an ODB numbers its
  nodes from 1, and `post/export_odb_mesh.py` keyed coordinates, displacement,
  Mises and — worst — face identity by the bare label. Measured on the
  bearing-block acceptance ODB (3 instances, 57030 nodes, 34831 elements):
  only **37622 distinct labels**, so 19408 nodes were unreachable and Housing,
  walked last, overwrote every coordinate Bushing and Cap had.
- **The half that mattered was not the overwrite.** `exterior_faces` counts a
  face by its sorted node labels, so one instance's face and another's collide
  into a single key, the count reaches two, and **both** are dropped as
  interior. Measured: **10590 real exterior faces, of which the bare-label
  walk found 3928 — 6662 (62.9%) deleted.** Worst case, also measured: two
  instances of the same part make every count double, `build_surface` returns
  0 nodes and 0 triangles, and the exporter still writes mesh.json, still
  exits 0 and still reports success.
- Everything is now keyed by `(instance name, node label)`; the field values
  supply it directly (measured: all 57030 U values carry `.instance`, none is
  None). Re-exported from the same ODB without re-solving: **bbox y [0,40] →
  [0,50]** (the Cap is back), **surface edges over 20 mm 25.7% → 0.0%**,
  longest edge 107.70 mm → 9.87 mm on a mesh seeded 1.5–7 mm, 3 instances,
  0 cross-instance triangles, 0 unattributable field values. Rendered
  side by side through the real viewport, edge density **0.0769 → 0.0125**.
- Format `abaqus-agent-mesh/1` → `/2`, adding `instances[]` (per-part triangle
  and node ranges) plus `cross_instance_tris` and `unscoped_field_values` as
  self-checks that travel with the data. The grouping key is deliberately NOT
  named `parts`: `workbench_viewport.js:292` dispatches on that name and would
  have silently rerouted results into the flat-colour multipart renderer,
  losing contours and deformation.
- The ODB walk moved out of `_inner_main` into `scope_instance_geometry`, so
  the place the bug actually lived is now reachable by the hermetic suite —
  every previous fixture lived in one flat label space, which is exactly why
  the suite could not see it. `tests/test_export_odb_mesh_topology.py` gains 8
  tests including the counterexample (bare labels delete the whole surface)
  and a cap that must refuse **before** materialising (measured regression
  during this change: 10000 elements consumed under a cap of 5).
- `scripts/run_result_mesh_ui_check.py` (registered as `result_mesh_ui`,
  9 items): nothing in the harness had ever looked at what the RESULTS
  viewport draws. It judges on edge density, chosen by measuring three
  candidate metrics rather than guessing a threshold — coverage separated the
  clean and broken renders by 1.2x, speckle by 5.0x, edge density by 7.0x.
- The results tab now says when it cannot be trusted: a run directory is never
  regenerated (its id hashes the spec, not the exporter), so every pre-fix
  mesh.json is still on disk and still draws the wrong assembly. `/1` payloads
  now carry a warning naming the format, and a self-contradictory payload
  (node_count against coordinate count, short displacement array, any
  cross-instance triangle) says so instead of painting confident pixels.
- **Not fixed, measured and recorded:** the KPI numbers were never affected —
  `post/extract_kpis.py` reduces instance-scoped `getSubset(region=...)`
  results and builds no label-keyed dict — but "only a rendering bug" was too
  broad: the viewport **legend** printed min/max straight out of the corrupted
  dicts, and on run `640f2b9d` it read a Mises max of 0.11462 against the KPI
  card's 0.23960, a factor of 2.09. Also still open: the Bushing OD and the
  Housing bore are the same physical surface (2050 shared exterior node
  positions), so that interface is legitimately drawn twice and will still
  shimmer until the results tab can hide or fade a part.

## [Unreleased] - 2026-08-08

### Fixed — accepting a proposal no longer solves on one CPU with a 30-minute fuse

- **An empty `runner_cfg` on accept fell through to the orchestrator's bare
  defaults — cpus=1, timeout_seconds=1800 — which no shipped runner.json uses
  and no assembly survives.** Found by the acceptance recording: bearing_block
  accepted through the UI had finished its first two steps and was 17.5% into
  the friction step when the 30-minute ceiling loomed; at cpus=1 the full
  solve extrapolates past 90 minutes. The endpoint now fills measured
  defaults (cpus=2 — what every gate and every shipped runner.json runs —
  and a 7200 s ceiling); caller-provided values always win, and
  `state.runnerCfg` on the page is the hook a future solver-settings panel
  wires into. cpus=8 measured separately before use
  (`artifacts/_probe_cpus8.py`: cantilever COMPLETED, KPIs identical to the
  frozen baseline to every digit).

### Added — the acceptance recording (#80)

- `scripts/record_acceptance_demo.py`: one continuous take on the bearing
  block — tree @, claude_cli iteration, real CAE preview, part pick with
  toggle-off, face pick generating a measured selector, a second iteration
  that turns that selector into a measurement region + KPI, accept, the full
  Abaqus 3-step contact solve (cpus=8, 1898 s), six KPI cards. All three of
  the model's identities check by hand to every printed digit, and
  WATCH_MISES=0.20349 is a KPI whose region was born from a face click.
  Evidence: `artifacts/acceptance/20260808_interactions/` (marks.json + 11
  stills; the 204 MB .webm stays local). The take shows Abaqus output —
  internal acceptance only, re-record on CalculiX before publishing.

### Added — selection as context (@-mentions)

- **A tree row can be @-mentioned in chat, and the mention is the object, not
  its name.** Every model-tree row now carries the spec path it was drawn from
  (`parts[1].features[0]`, `steps[0].loads[0]`, …); clicking the row's @ pins a
  chip on the composer and the send resolves each ref server-side against the
  same spec text the tree rendered, injecting the actual YAML fragment into the
  planner prompt under `## 用户选中`. The resolver has no grammar of its own —
  what can be mentioned is exactly what can be seen, so the tree and the chat
  cannot drift apart.
- **Fail-closed on send.** A ref the tree never drew (renamed part, deleted
  step, diagnostic rows) is a 400 naming the offender; the transcript is left
  untouched and the chips stay so the user fixes the selection instead of
  retyping. An unresolved mention passed through would have the model edit an
  object that is not in the spec, confidently — the one outcome this repository
  exists to refuse. The template backend acknowledges mentions honestly: it
  matches keywords and says so, rather than pretending to aim.
- **A `selector` ref kind for viewport picks**, validated by the same
  `core.selectors.parse` the build uses, with measurement notes passed to the
  prompt verbatim ("不要改写它的数字"). Gate:
  `scripts/run_mention_ui_check.py` (registered as `mention_ui`) proves the
  chip survives into the transcript, the reply acknowledges it, and a dangling
  mention refuses with toast + chips kept + transcript unchanged.

### Added — clicking a body in the 3D preview mentions it

- **A left click on a part in the preview is the same gesture as clicking its
  tree row's @**: highlight follows, a chip lands on the composer, a second
  click removes it. Click and drag are told apart by pointer travel (5px), not
  timing, so orbiting never fires a pick; right button stays pan. The raycast
  reads the live part-handle list, so bodies added mid-stream are pickable the
  moment they draw, and a dimmed body stays pickable on purpose — clicking
  another part is how a selection moves. A body with no mentionable tree row
  (custom_inp ELSET parts) toasts instead of doing nothing.
- Both preview builders come through one `createPreviewViewport()`, so a
  viewport that can pick is never created without the handler. Gate:
  `scripts/run_pick_ui_check.py` (registered as `pick_ui`), 13 items — real
  pointer events against a deterministic camera prove the centre click hits
  the z=1 body at z=1.0000000000000002, a 60px drag picks nothing, and an
  unknown key toasts.

### Added — clicking a FACE generates the selector for you

- **Face mode: a click on a geometric face in the preview produces a
  `INST:face@box=…` selector generated from CAE's own measurements, never a
  face index.** The preview dump now walks each instance's geometric faces and
  records what CAE reports: the assembly-space bbox
  (`inst.faces[i:i+1].getBoundingBox()`), the mesh nodes on the face, radius
  and normal probed the way the selector runtime probes (raising IS the
  answer), and the area. Measured on Abaqus 2021 via plate_hole_v2: 7 faces,
  the hole comes back radius 6.0 with area 188.4956 = 2π·6·5 exactly, and —
  worth knowing — **getNormal() answers on a cylinder too** (the seed-vertex
  normal), so a normal's presence must never be read as planarity.
- **The hit count is computed the way the build will re-assert it**: which
  same-instance faces fit inside the padded box. A flat face whose box
  contains a coplanar boss honestly counts 2 and the selector goes plural
  (`faces@box=`); the note carries the count and the measured radius, and the
  prompt tells the model the numbers are measured, not typed. A triangle no
  face claims toasts instead of guessing; a face the dump shipped without a
  bbox is dropped and counted in `degraded`.
- Pick granularity toggles in the preview header (部件/面). Face chips ride
  the same rail as tree chips — toggle off on second click, cleared only on a
  successful send, 400 with the parser's own message on a selector the build
  would refuse. Gate: `run_pick_ui_check.py` grew to 20 items including a
  REAL chat round trip of a selector chip; frozen-deck pins updated (model
  half proven byte-identical, runs archived to
  `artifacts/runs_archive/20260808_frozen_pin_79/`).

### Added — the model layer

- **A spec can name any Abaqus modelling method instead of picking from a
  closed list.** `parts`, `assembly`, `interactions`, `steps` and `conditions`
  dispatch `getattr(obj, spec["call"])(**kwargs)`. Abaqus exposes 292 callables
  on `Part` and 71 on `ConstrainedSketch` and the lists grow every release, so
  an enumerated schema could only ever build the shapes somebody had already
  written a branch for. Five worked cases ship in the dialect: `bearing_block`,
  `two_plate_tie`, `two_plate_contact`, `block_friction_slide`,
  `plate_hole_v2`.
- **`expect:` blocks, checked against the built model**, because what generic
  dispatch gives up is a schema that knows what each call was supposed to
  produce. Geometry (volume, cells, faces, cylindrical faces), mesh (element
  count, shape-quality criteria, and how many elements a criterion did not
  apply to), assembly (instance count, where each instance landed, wire section
  coverage), and the measured gap between a contact pair's two surfaces.
- **`target:` can name a member of the default object, not only something an
  earlier call bound.** `{attr: keywordBlock}` and `{attr: engineeringFeatures}`
  are not the result of any call, so no `as:`/`{ref:}` could reach them and
  `m.keywordBlock` — the escape hatch for every card CAE's Python API has no
  method for — was unreachable from a spec. A `{bool:}` value form came with
  it, because `synchVersions(storeNodesAndElements=False)` is a real signature
  and a bare YAML boolean is refused on purpose. The keywordBlock half is
  measured end to end. The engineeringFeatures half opened the route — Abaqus
  answers `assignSeam` with `regions; found tuple, expecting Set`, a complaint
  about the argument, which only an object that has the method can make — and
  seams themselves are the next entry.
- **Seams.** `{set:}` in a part feature now builds a PART set, which is what
  `engineeringFeatures.assignSeam` takes, and a part that assigns one must say
  what it should come to: `expect.seams: [{set: SEAMFACE, duplicated: 9}]`.
  Both halves were decided by measurement rather than by design.

  The blocker was misdiagnosed. It looked like "an assembly operation cannot
  build a Set", so the part route was expected to sidestep it; measured, the
  part route answers a raw sequence with the same complaint. What was missing
  was a part set, which is a different object from an assembly set and which
  `{set:}` could not make because it assumed every set lives on the assembly.
  Part scope also turned out to be the right scope, not just a workable one:
  part features run before `generateMesh`, and a seam assigned after one
  leaves the node count untouched until something remeshes (27, then 36 only
  after a second `generateMesh()`). The assembly-operation refusal now names
  that route instead of calling the gap known.

  `expect.seams` is mandatory because the failure has no exception in it. On
  one 10×10×10 block partitioned at mid-height, seed 5: no seam 27 nodes, a
  seam on the interior face 36, **a seam on the top face 27 and on the bottom
  face 27 — accepted, no error, nothing changed**. A face not shared by two
  cells cannot be separated and Abaqus does not say so, so picking the wrong
  face with a selector yields a model with no crack in it that builds, solves
  and reports success. The check counts the seam's own set after the mesh: 18
  nodes at 9 positions where an unseamed face gives 9 at 9. `duplicated: 0` is
  not writable — that is the failure itself.

  `Crack` and `XFEMCrack` — contour integrals, crack fronts, q-vectors,
  enriched regions — are **not** part of this and have not been measured.
- **A part can be read out of a geometry file.** `parts[].import` opens a
  STEP, SAT, IGES, VDA, Parasolid or Pro/E file and hands it to
  `PartFromGeometryFile`. `open:` is a call mapping naming the Abaqus opener
  rather than an enum of formats, because each opener takes its own keywords —
  `openIges` alone has `msbo`, `trimCurve` and `topology`. A new `{file:}`
  argument form resolves a path against the SPEC file's directory (the rule
  `custom_inp` already used) and refuses a path that is not there at generation
  time, before Abaqus starts and before a licence is taken. The build cache
  gained `imported_files_sha256`: the generated script embeds the path and not
  the bytes, so without it a geometry file edited in place would have reused
  the old deck — the same defect this project already fixed once for
  `custom_inp`.
- **An imported part must state `expect.volume` or `expect.cells`**, and that
  rule is narrower than "state an expect block" because of what was measured.
  One 10 x 10 x 100 bar exported from CAE and read back: STEP and SAT return 1
  cell and volume 10000.0; **IGES returns 0 cells and volume 0.0, raising
  nothing** — and 6 faces either way. So `expect: {faces: 6}` passes on a
  hollow shell, which then takes an empty cell set, an empty section
  assignment, and meshes into nothing, all in silence.
- **A constraint can be given a control point.** `{reference_point: [x, y, z]}`
  creates the point and the one-member set that `Coupling`, `RigidBody` and
  `MultipointConstraint` each take as a Region — a round trip three objects
  deep (`ReferencePoint` returns a *Feature*; the point is
  `referencePoints[feature.id]`; the constraint wants a Region over that) which
  no spec could previously express, so none of the three was reachable.
  `{reference_point: {at: "<instance>:face@z=max"}}` puts it at an entity's
  centroid instead, which is the common case and removes the arithmetic.
- **`{named_set:}` names a set an earlier call in the same spec built.** It
  exists for one asymmetry: every other region form re-finds its region by
  geometry, so two calls on the same face just write the selector twice — but a
  reference point sits on no face and no edge, and no selector reaches it.
  Without this, a coupling could be created and then never loaded, which is the
  only reason to create one.
- **Misplacing a control point is not refused, and the measurement says why
  that matters.** Every *misuse* measured is loud — a coupling onto an empty
  surface dies with 6 fatal errors, one whose control point is a face set with
  74 — but position is silent. Same bar, same 100 N, point moved 50 mm past the
  end: 0 errors, 0 warnings, COMPLETED, and a `location: whole_model` KPI
  answering **-0.61471903** where beam theory is -0.19047619. That reading is
  the reference point's own node, which is not part of the structure; the bar's
  tip in the same run is -0.33120051. Both wrong, and the one a spec receives is
  the wronger. It is not refused because an offset control point is also how a
  moment is applied and the two are the same call with a different number — so
  what ships is `{at:}`, and the position written to `selectors.log` either way.
- **A spec can set launcher options.** `job:` passes `name: value` pairs to the
  `abaqus` command — `double`, `user`, `oldjob`, `gpus`, `scratch` — which are
  the things a deck cannot say, so before this there was nowhere in a spec to
  put them. A passthrough rather than a supported-flag list, decided on
  measurement: an unknown option, an unsupported value, a missing subroutine
  file and a missing restart odb are all rejected by the launcher, and **all
  four exit 0 and write no .dat and no .odb**, with the reason on stdout only.
  So the option is never judged here; what this side does is refuse to read the
  exit code, and raise the launcher's own sentence. The launcher also prints
  the 36 options it accepts, and that list is deliberately not used as a
  validator: it omits `gpus`, and `gpus=1` runs. `user` and `oldjob` are
  checked for existence first, because Abaqus checks them only after taking a
  licence. `job`, `input`, `interactive`, `background`, `cpus`, `mp_mode` and
  `memory` are refused with a pointer to runner.json — the pipeline already
  writes them, and a duplicate is resolved by the launcher without a word.
- **`double:` is passed through and explicitly not vouched for.** Measured
  across six combinations (Standard and Explicit x default, `double=both`,
  `output_precision=full`), `odb.jobData.precision` reads SINGLE_PRECISION
  every time, and a default run's `.dat`, `.msg` and `.sta` are identical to a
  `double=both` run's. Nothing on this machine records whether the option took
  effect, so the schema says so and the gate asserts the gap — if a later
  Abaqus reports it properly, that item fails and the claim has to be rewritten.
- **A buckling eigenvalue can be read.** `type: eigenvalue` on a `*BUCKLE`
  step: **10744.0 against Euler pi^2EI/4L^2 = 10794.88, 0.47% out**. Abaqus
  2021 publishes the value in exactly one place and it is a string —
  `frame.description`, five significant figures, which the `.dat` table
  repeats exactly — while `frame.frequency` is None, `frame.frameValue` is the
  mode *ordinal*, and `step.historyRegions` is empty. So the parser is strict
  and never falls back: both plausible fallbacks return a number that is not a
  buckling load. Building the gate also measured why the load matters: with a
  `Pressure` the eigenvalue came back **-25243**, wrong sign and 2.34x, because
  a distributed pressure follows the face as it rotates and a follower load is
  not what Euler's formula describes.
- **`outputs.kpis[].type` is a closed list, checked before anything runs.** It
  was an unconstrained string: a typo validated, built, meshed, solved, and
  then raised "Unknown kpi type" from inside the Python 2.7 kernel. The enum is
  safe rather than brittle because `tests/test_kpi_type_closed.py` holds three
  copies of the list together — the schema, the extractor's dispatch chain, and
  `odb_lens.recipe.SUPPORTED_TYPES`. That third copy is why the test exists:
  `eigenvalue` was added to the other two and a `*BUCKLE` spec validated,
  built, meshed and solved before being refused by the layer meant to be the
  cheap gate.
- **Fixed: `step: <name>` had never worked.** `odb.steps` is an Abaqus
  Repository, not a dict, and its membership test is type-checked; the KPI spec
  reaches the 2.7 kernel through `json.load` as unicode, so `u'Buckle' in
  odb.steps` was False against an ODB holding `'Buckle'` and every named step
  fell through to the numeric branch. The error printed the answer next to the
  question: `Step u'Buckle' not found. This odb has 'Buckle'`. It went
  unnoticed because every shipped case selects its step by ordinal.
- **Gate summaries are committed.** `evidence/gates/*.json` carries each real
  Abaqus gate's item ids, verdicts, identities and measured numbers, produced
  by `scripts/collect_gate_evidence.py` under a field allowlist. ROADMAP's rule
  says a capability ships as supported only when a real solver run proves it
  and that its output is committed as evidence; that last clause was true of
  this repository and false of the published tree until now.

### Added — a part read out of a deck

- **`node@` and `element@` selectors, and an `import:` that can make an orphan
  mesh.** Measured on Abaqus 2021, `PartFromInputFile` on a deck holding one
  meshed bar returns 189 nodes, 80 elements and **0 cells, 0 faces, 0 edges,
  0 vertices**, and drops every set and surface the file carried (3 `*Nset`,
  4 `*Elset`, 1 `*Surface` in; `sets: []`, `surfaces: []` out). So every
  selector this dialect had resolved against an empty sequence, and
  `Set(faces=<empty>)` is accepted in silence. An imported bar now takes its
  load through `nodes@z=max` and solves to **−0.18946819 against
  P L³/3EI = −0.19047619, 0.53% out**.

  **`element@` takes only `@all`, and that is measured rather than
  conservative.** `getByBoundingBox` on elements means wholly inside: the
  tolerance band this dialect emits (span × 1e-6) matched **0 of 80** elements
  at z=min, while a band one element thick matched the 4 of that layer. A
  plane is a surface and an element is a volume; the thickness that would make
  them meet is a number the author would have to work back from the seed,
  which is the coordinate arithmetic selectors exist to remove. The refusal
  carries all three numbers.

  Two silent zeros decided the rest. `getVolume()` on such a part returns
  **0.0 without raising** — the same answer the IGES shell gives — so an
  import must state what came back, and *which* pair it states (volume/cells
  versus mesh.nodes/mesh.elements) is also what tells this layer which kind of
  part it is; no method-name list is involved, and a wrong declaration meets a
  run-time check either way. And the section path every other part takes,
  `p.Set(name='ALL', cells=p.cells)`, was measured to build a set holding 0
  cells and then assign a section to 0 cells, neither raising — so the orphan
  route builds that set from elements instead. Only that branch changed; every
  other part emits the bytes it emitted before, which the frozen-deck guard
  compares.

  `PartFromInputFile` takes no `name` and the deck's name arrives upper-cased
  (`Bar` → `BAR`; a two-part deck arrives as `ALPHA` and `BETA`), so the part
  is picked up by diffing the model's parts across the call, renamed with
  `parts.changeKey`, and a file producing anything other than exactly one part
  is refused with the names it did produce. `expect.mesh` gained `nodes`,
  because 80 elements is 189 nodes as C3D8 and far more as C3D20.

### Added — a crack's truth layer

- **`contour_integral_j` reads J off a `*Contour Integral` history output, and
  refuses two runs Abaqus reports as COMPLETED without a word.** Seams close by
  counting nodes; a crack has no equivalent tell, which is the question #70
  left open. J is also the one quantity in this dialect that cannot be checked
  while the model is built — it does not exist until the job is done, and a
  contour integral returns a number for any "crack" it is handed. So the layer
  lives in the extractor.

  Measured on Abaqus 2021 against a single-edge-notched plate, a/W = 0.2, plane
  strain (`K_I = 768.3 MPa·√mm`, `J = K_I²(1−ν²)/E = 2.5576 N/mm`). The correct
  model returns **2.5033, −2.12% from the handbook**. A model whose seam was
  never assigned returns −1.4e−16 … −1.3e−14. A model whose crack-extension
  direction is reversed returns **−2.5033: the right magnitude, the wrong
  sign**. Both broken jobs COMPLETED with no warning.

  Three checks, and the order was corrected by the solver. The first draft
  tested `all(v == 0.0)` for the unseparated crack, because "no seam means
  zero" is obvious; the real values are round-off on both sides of nothing and
  **every one of them is negative**, so they fell through to the sign check and
  a missing seam was diagnosed as a reversed q vector — sending the user to fix
  a vector that was already right. A `zero_tolerance` (default 1e−12, and the
  measured round-off is three orders below it) now runs first. A genuinely
  small J still comes back.

  The third check is the one that matters most and would have been the only one
  a textbook suggested. Path-independence across contours 2..N cannot see the
  reversed run: **its contours are as converged as the correct model's,
  7.74e−04 either way**. Only the sign separates them, and the gate asserts
  that premise rather than assuming it. Contour 1 hugs the singularity and is
  neither returned nor averaged in.

  **Authoring a `ContourIntegral` through this dialect** was explicitly not
  claimed when this shipped: the gate built its models with its own CAE script
  and said so as one of its ten items rather than leaving it to be assumed.
  That item was a trip-wire, not a sentence — it scanned `cases/*/spec.yaml`
  and would fail the moment a spec authored one. It is now measured, and the
  entry below replaced it.

- **A crack can now be built from a spec, and the answer is bit-identical to a
  hand-written CAE script.** The single-edge-notched plate that #75's gate
  built with its own script is now also built from the v2 dialect, in the same
  gate, and both return **J = 2.503265619277954 — every digit.** The comparison
  is against the scripted rig rather than the handbook, because a −2.1%
  handbook gap cannot tell a correct model from an approximately correct one.
  The same spec with its seam removed still solves, still reports COMPLETED,
  and is still refused by the extractor — reaching J through the dialect is not
  a way around the truth layer.

  Two things were in the way, and neither was an Abaqus limitation:

  - **Parts were hard-coded `THREE_D`**, and every downstream line operated on
    `p.cells`. `parts[].dimensionality` now takes `THREE_D`,
    `TWO_D_PLANAR` or `AXISYMMETRIC`; a 2D part meshes with `faces`, pairs with
    QUAD/TRI instead of HEX/TET (a mismatched pair is refused by name), and
    takes `section.thickness` — which is refused on a `THREE_D` part, where it
    would be silently ignored. `expect.area` came with it, since `volume` is
    `0.0` on a planar part and that is the silent-zero family this engine
    already knows about.
  - **No selector could name one of two.** Partitioning at the crack tip splits
    the y=0 line into two edges; the plane form matched both, `@all` matched
    both, and there was nothing in between — the gap #22 recorded when it
    refused `cell@<plane>`. `kind@box=x0,y0,z0,x1,y1,z1` closes it: a
    scale-relative padded bounding box, refused if the six numbers are not six
    numbers or if a box is inverted. It is `getByBoundingBox`, so on volumes it
    means WHOLLY INSIDE.

  A third change rode along and is deliberately not counted as a blocker:
  **assembly operations can now build sets**, which is what a *named* crack
  front wants. It was checked rather than assumed — writing crackFront and
  crackTip as `{select:}`, which compiles to a tuple, returns
  **the same J to every digit** — so the set form buys a name, not the
  capability. What did change with it is a refusal: `assignSeam` on the
  assembly used to be declined because "an assembly operation cannot build
  one", true of this generator and false of Abaqus. The reason is now the real
  one, **timing** — measured, a seam assigned after `generateMesh` leaves the
  node count exactly as it was and raises nothing (27 against 36), and assembly
  operations run after `generateMesh` while part features run before it.
  Whether Abaqus would accept an assembly set for that argument is not claimed
  either way; both answers make the route wrong.

  Both planner prompts carry the whole recipe, and the recipe in the prompt is
  extracted by a test, run through the schema and through `generate_script` —
  an example is the part that gets copied.

- **The Copilot prompt's KPI list was two types stale, with nothing to catch
  it.** `eigenvalue` and `derived_stress_concentration` were in the schema and
  absent from `workbench/planner.py`, so buckling and SCF were unreachable from
  the chat while every test passed; the drift guard added in #29 covered only
  the other prompt. Both prompts now read against the schema's enum in both
  directions, and `odb_lens.recipe.SUPPORTED_TYPES` — the third copy of that
  list, and the one checked after the solve is paid for — is held with them.

### Documented — the KPI whose name promises what the code does not do

- **`derived_stress_concentration` returns a stress, not a concentration
  factor**, and the comment above it said otherwise. The line read
  `Kt = max_mises_at_hole / nominal_stress`, describing a division the branch
  does not perform — so `cases/plate_hole` ships a KPI named `SCF` whose note
  promises "analytical ~3.0" beside a value of about 300 MPa.

  It is not `field_max` in different units either. `field_max` routes a stress
  field through `_at_element_nodal`; this branch does not, so one is the
  unaveraged extrapolation to the element nodes and the other is the
  integration point — measured 8.2% apart on this very plate. Dividing `SCF` by
  the nominal stress by hand does not recover the promised Kt, and the
  shortfall is a position, not a rounding.

  **Left as it is, on purpose.** `run_id = sha256(spec)`; the name and the note
  both live in the spec, so correcting either — even the note — changes the
  hash and invalidates a frozen Abaqus baseline that was measured once and
  cannot be recomputed. The honest rename costs a piece of unreproducible
  evidence. What it costs to leave is a misleading name, so the name now has
  `tests/test_scf_returns_a_stress.py` attached to it: five tests that fail if
  someone turns the extractor into a ratio (silently changing what every
  existing baseline means) AND if the misleading note is quietly edited out
  (changing the run_id without anyone weighing it). The schema's type
  description says the same thing where a spec author reads first.

  It has cost nothing so far for a reason worth recording: `expected.json`
  grades `MISES_HOLE_EDGE` and `U_X_MAX` and never pinned `SCF`, so the wrong
  name has never made a run pass or fail.

### Fixed — a selector form that could never match

- **`cell@<plane>` matched nothing, every time, and was still on offer.** #71
  refused `element@<plane>` because `getByBoundingBox` on an element means
  wholly inside, so a plane never cuts one. A cell is a volume for the same
  reason. Measured on Abaqus 2021 on a plate partitioned into two cells at
  x=10: `cell@x=min` matched **0 of 2** at the band this dialect emits and 0 of
  2 at a band a hundred times tighter, while a box containing the whole first
  cell matched 1 and `face@x=min` **at the same band as the first row** matched
  1. The last two are why this is a refusal rather than a wider tolerance — the
  band is not too thin, and the box that does catch a cell is one that contains
  all of it. No plane can ever match.

  It failed loudly rather than silently, because the count assertion caught it,
  so this cost people time rather than correctness. Nothing in the tree used
  the form. Both planner prompts now teach it, held by the drift guard that
  reads `selectors.PLANE_REFUSED`.

  What this does NOT fix: naming *one of several* cells is still unsayable.
  That is what a 3D crack model needs — partition only the cell on one side of
  the tip — and it would take a compound-condition selector grammar, which is a
  direction rather than a detail.

### Fixed — a material erased by its own spec

- **Re-declaring a material in `model_setup` deleted everything the spec said
  about it, silently.** Measured on Abaqus 2021: a material carrying Elastic,
  Plastic and Density, handed a second `m.Material(name=...)` under the same
  name, comes back with all three absent and nothing raised. Not just the
  Elastic — the `yield` and the `density` are gone too, which is the 917 MPa
  failure `_materials` was written to prevent, arriving through a different
  door. The block order guarantees the rebuild wins.

  **Why anyone wrote that spec, and why a refusal alone would have been the
  wrong fix.** `material:` is a closed key set: Hyperelastic, an anisotropic
  LAMINA elastic, a multi-point hardening curve and a temperature-dependent
  property cannot be spelled there, and re-declaring was the only route. So the
  refusal ships with the route out, and the route was measured too —
  `Hyperelastic` on an existing material succeeded and left its Elastic intact,
  as did LAMINA, a four-point hardening curve and a temperature-dependent
  expansion.

  A declared material is now reachable as `target: {ref: <name>}` without any
  earlier call having bound it, and **nothing extra is emitted for it**: it
  compiles straight to `m.materials['<name>']`, so a spec that does not use the
  form produces the deck it produced before, byte for byte.

  **Two layers, split by how many method names they know.** The
  generation-time refusal knows one, `Material`, because that is the one
  measured to do this. The runtime check knows none: after `model_setup` runs,
  every declared material is asked whether it still carries what it was given,
  so a call that clears one by a route nobody has measured is caught too. A
  list of dangerous method names would have been a guess about Abaqus's API;
  this is a statement about our own spec. The property list is per-material and
  read off the spec — a material that never declared a density is not checked
  for one.

  The refusal covers **all four blocks that dispatch onto the model**, not just
  `model_setup`: `interactions`, `steps` and `conditions` reach `m` the same
  way, so the same line erases a material from any of them. What differs is the
  way out — `target: {ref: <material>}` is offered in `model_setup` only,
  because a constitutive model has to be on the material before a section
  assignment uses it, so from the other three the instruction is to move the
  line rather than to rewrite it where pointing at that form would not work.
  An `as:` alias colliding with a declared material name is refused too:
  aliases win the lookup, so the collision would silently redirect every later
  `ref:`.

  The check is emitted inline in the `model_setup` block rather than added to
  the shared preamble, because `build_model.py` fingerprints the whole script
  for its run cache and a preamble change would rebuild every shipped case's
  frozen baseline in place. No shipped case has a `model_setup`.

### Fixed — a KPI location naming a surface

- **A `location` that named a surface resolved, then died inside Abaqus, and
  the KPI disappeared from a run that reported COMPLETED.** `_resolve_region`
  searched `surfaces` alongside the node and element sets and returned whatever
  it found first; `getSubset` then answered *"Surface based region for
  getSubset is not supported"*, the KPI vanished from `result["kpis"]`, the
  error stayed in `stages.extract_kpis.errors`, and the top level still said
  the run succeeded. A surface was never a usable region here, so returning one
  only moved the failure somewhere it could not be explained.

  Surfaces are still searched, and that is the fix rather than an aside:
  "not found" would send the author hunting for a typo in a name that is
  correct. What is wrong is the kind of object, so the refusal says so, names
  the sets that would have worked, and says to build a set over the same
  region. The "available sets" list is now actually sets — surfaces used to be
  mixed into it.

  This is half of what was found. The other half is the entry below.

### Fixed — a run that delivered fewer KPIs than it was asked for and said so nowhere

- **A dropped KPI left a grid one tile shorter, a cover reading `KPIs: 2`, and
  a run reporting COMPLETED.** `_stage_extract` assigned `result["kpis"]` from
  whatever came back and left the failures in `stages.extract_kpis.errors`.
  Nothing compared the two collections, so a spec asking for three KPIs and
  receiving two produced three true statements, none of which mentioned that a
  third had been requested. This is the blind spot the surface refusal above
  landed in.

  `odb_lens.missing_kpis()` DIFFS the requested names against the delivered
  ones rather than reading the error list, because those are different
  questions: the error list only knows about failures somebody wrote a message
  for, and a KPI that vanishes for an unanticipated reason still shows up in a
  diff. The shortfall now travels as `result["kpis_missing"]` — always written,
  empty list included, so "nothing was dropped" is an answer this pipeline gave
  rather than a key an older run happened not to have — and rides the
  `limitations` channel the UI already polls. The workbench draws a tile for
  each one, headed with the denominator (`2/3`); the report cover reads
  `2 of 3` with a warn class, and both the HTML and the Markdown KPI tables
  carry a `NOT EXTRACTED` row with the extractor's own words in it.

  **The verdict is deliberately unchanged.** Marking the run FAILED would
  re-grade every shipped case and every frozen baseline, which is a separate
  decision from making the shortfall visible; the browser gate asserts both
  directions, so a build that starts failing these runs fails the gate too.

  Measured end to end on a real Abaqus 2021 solve: a cantilever with a third
  KPI pointing at a set that does not exist finished COMPLETED, delivered two
  values, and reported `kpis_missing: [MISES_AT_ROOT]` with the ODB's list of
  sets that would have worked.

- **Every `.dat` integrity finding had been rendering as an empty card.**
  Found while wiring the above. `runner/dat_warnings.limitation_lines()` writes
  plain strings into `result["limitations"]`; the page read `l.reason`, which
  on a string is `undefined`, so `limitationLine` returned `" = ："` and the
  card came out blank. The channel chosen because "the UI cannot render a
  degraded run as a clean one" was displaying nothing at all — including *85
  tie nodes were silently left unconstrained*, the bearing_block finding that
  channel exists for.

- **`scripts/run_diagnosis_ui_check.py` was in no registry.** Written in
  2026-08, never run by the harness. It is the gate proving a failed run still
  shows its error text after you click away and back. Registered; passes.

### Added — a warning for the element that is silently 92x wrong

- **`mesh.element: C3D8R` produced an answer two orders of magnitude out, from
  a job reporting COMPLETED, with nothing on screen.** A first-order
  reduced-integration element has one integration point, and an element's
  bending modes produce no strain at that point — so they cost no energy and
  the element folds into them freely.

  Reproduced while building this, on a model unlike the one that found it (a
  bar built from this dialect under a distributed side pressure, rather than an
  imported orphan mesh under a tip force), which is what turned one observation
  into a rule:

  | elements through the 10 mm thickness | C3D8I | C3D8R | ratio |
  |---|---|---|---|
  | 1 (seed 10) | -0.7126152 | -65.66674 | 92.1x |
  | 2 (seed 5) | -0.7104333 | -0.9517219 | 1.34x |

  Read the C3D8I column first: it moves 0.3% between the two meshes, so it is
  already converged and the C3D8R number is not a coarse mesh. The number of
  element layers through the thinnest direction is the only knob that changes
  anything.

  `core/element_risk.py` is a RULE, not a list of bad element names: it reads
  Abaqus's naming grammar (`<family><nodes><modifiers>`, `R` = reduced, node
  count against the family's first-order ceiling), so an element nobody has
  typed into this repository classifies correctly if its family is known. It
  has three verdicts, and the third is the point — `B31R` carries an `R` but
  its digits are not a node count (`B31` = beam, 3D, order 1), so it comes back
  `unreadable` rather than `clear`. Silence from this module means "no reduced
  integration", never "we could not tell".

  **It warns; it does not refuse** (user's call, 2026-08-07: 警告并写进报告).
  Reduced integration is the correct element under explicit dynamics with
  enhanced hourglass control, and a model with no bending is unaffected. No
  shipped case names a first-order reduced element, so no verdict and no
  `run_id` moved; a test asserts that, so adding one becomes a deliberate
  choice rather than a surprise in a frozen baseline.

  Both planner prompts were teaching the opposite. `workbench/planner.py`
  listed `C3D8R` at the head of "the usual four" and used it in its import
  example — which is the very model the 90x was measured on. Both now lead with
  `C3D8I`, and a guard runs every `element:` in either prompt through the
  classifier, because an example is what gets copied and prose is not.

- **The report gained a Known Limitations section.** It had none: an archived
  report is what gets sent to somebody who was not in the room, and it carried
  no caveats at all — not the hourglass warning, not a tie that silently
  dropped 85 nodes, not a KPI that never came back. Both limitation shapes are
  rendered, the `{feature, value, reason}` records and the bare sentences
  `runner/dat_warnings` writes.

- **`scripts/run_hourglass_warning_check.py`** solves both element codes on
  every harness run (5/5, 59.8s, ratio 92.15). It asserts both directions: the
  warning fires and names the spec key, AND the run still reports COMPLETED. A
  gate that only checked for the warning would pass a build that had started
  refusing C3D8R outright.

### Fixed — documentation that had gone quietly out of date

- **The schema described eleven argument forms and the generator resolved
  fifteen.** `one`, `new`, `instance`, `vertex` and `wire_at` were implemented,
  tested, shipped and used by real cases while the only prose a spec author can
  read enumerated the other ten and stopped. There is no enum to fall back on —
  generic dispatch leaves the METHOD names open, so the closed part lives in a
  description, and a description does not fail a test when it goes stale. A
  form nobody can find is a form nobody uses, and the next move is a
  hand-written wrapper for something the dialect already does.

  `tests/test_schema_arg_forms_documented.py` now compares the two lists in
  both directions — a form the generator resolves and the prose omits, and a
  form the prose quotes and the generator does not resolve — plus a stated
  count, so adding a sixteenth cannot be silent. Both directions were verified
  by mutation rather than assumed: deleting `wire_at` from the prose and adding
  a fictional `edge_at` each fail the check. The allow-list of quoted words
  that are not forms is exactly the five the pattern reaches today, because a
  generous one would make the whole test fail open.

  Same rot in `docs/MASTER_PLAN.md`, which stated the count of eleven twice —
  in the section whose own rule 3 is "don't write numbers that rot, write the
  command that prints them". Replaced with the command.

- **Both planner prompts had fallen behind the builder by five capability
  layers.** Between the dispatch work and here, the generator learned part-scope
  sets and seams, geometry and orphan-mesh import, `node@`/`element@` selectors,
  reference points, and four more argument forms. Neither prompt learned any of
  them, and nothing failed: every existing test asked "is what the prompt
  teaches true?" and none asked "is what the builder does taught?". A capability
  the planner cannot name is one the user cannot reach, and from inside the
  prompt it is invisible.

  `workbench/planner.py` (the Copilot chat) gained the import route with the
  measurement that makes its `expect` mandatory — the same bar exported and read
  back returns 1 cell and volume 10000.0 through STEP and SAT, and 0 cells and
  volume 0.0 through IGES without raising — the seam rules, the mesh-selector
  kinds with the reason `element@` takes only `@all`, and all fifteen argument
  forms with the four that are assembly-only called out.

  `prompts/spec_generator.txt` (behind `server.py` and `mcp_server.py`) was
  worse: entirely v1, so those two endpoints could not emit an assembly spec at
  all, and its one example hard-coded `abaqus_release: "2024"` on a machine
  running 2021. Rewritten to teach both dialects and say which to use when.

  The guards are drift tests in both directions, read from `_ARG_FORMS`,
  `selectors.KINDS` and the schema's KPI enum rather than typed out again, plus
  a stated count so a sixteenth form cannot be silent. Every prompt example is
  now extracted and pushed through the real schema AND
  `build_v2.generate_script` — which immediately earned its keep: the seam
  example was written `{name:, positions:}` and the generator refused it, the
  keys are `{set:, duplicated:}`. Verified by mutation, and verified to fail
  against the pre-change prompts.

### Fixed — answers that were wrong and quiet

Each of these produced a confident number, or a completed job, with nothing
anywhere saying otherwise. Each was measured on Abaqus 2021 before and after.

- **The preview knew which faces a tie joined and never said so.** The named
  surfaces, their triangles, and which interaction joined which of them are
  computed by `post/parse_inp.py:_overlay_region` on every preview build — and
  `workbench/routes.py` dropped the whole structure before the `meta` event
  went out. So clicking a contact pair in the model tree could only dim the two
  bodies, which on a bonded pair is close to no information: the joined faces
  are interior, they are exactly where the bodies meet, and "both plates" is
  the picture the user already had.

  Which facets Abaqus actually put in the surface is the one thing a spec
  author cannot check by reading the spec. `Housing:face@r=12` catching the
  bore and catching the outer flange are the same eleven characters of YAML and
  look nothing alike in the viewport. The overlay now ships (measured on
  `bearing_block`: 119 KB against a 477 KB mesh, every list capped upstream),
  and a selected interaction draws its two sides in two colours over the bodies
  that carry them.

  A highlight that covers part of its region says so rather than reading as all
  of it — the preview mesh is an exterior corner-node triangulation, so a
  quadratic element's midside nodes are not in it and cannot be lit. The
  overlay carries `drawn_nodes` against `node_count` for exactly this, and the
  tree now reports the shortfall instead of discarding it.

  `scripts/run_contact_preview_ui_check.py` (16 items, ~21 s, registered in the
  harness under a new `browser` kind) asserts on the three.js scene graph in
  real Chromium rather than on pixels. Item 7 pins the trap that made the cheap
  implementation wrong: reusing a part's own position buffer for the highlight
  would let `clearRegions` free the body's GPU buffer along with it, blanking
  the model on the *second* click. Verified to report FAIL (3/5) against the
  frontend from before this change.

  The browser surface had no entry in the harness at all, which is how a
  backend computing an overlay that never reached the wire stayed green for
  months.

- **A spec the model wrote and validation rejected was replaced by a default
  cantilever and reported as valid.** `generate_spec_async` wrapped the whole
  LLM path in `except Exception: pass`, so a user of `server.py` or
  `mcp_server.py` who asked for two plates tied together got a 100 mm cantilever
  back with `valid: true` and nothing anywhere saying their request had been
  discarded. `LLMPlanner` now splits `call` from `parse`: failures before the
  model answers — no key, no package, no network — still fall back to the
  template, because a template is a fair answer to that; failures after it
  answers propagate, because substituting one answers a different question than
  the one asked. `parse` also dry-builds v2 output through
  `build_v2.generate_script`, so the refusal is in the builder's own words
  naming the spec key, rather than a kernel traceback after a licence has been
  taken. A relative `{file:}` is declared undecidable — it resolves against a
  spec file that does not exist yet — instead of being refused or waved through.
- **A KPI component name that was not recognised fell back to a default
  index.** `S12` returned `S11`; `UR3` returned `U2`; and the default differed
  per KPI type, so the same misspelling returned a different wrong number
  depending on which KPI asked. Now refused by name.
- **`invariant:` recognised only `MISES`**; the other six silently became
  `.magnitude`. A KPI's `name` was also a hidden dispatch key that could
  override an explicit `field_variable`.
- **`history_output_max` ignored `location:` entirely**, reducing across every
  region in the file.
- **An `expected.json` baseline of 0 was judged INFO, and INFO counted as a
  pass** — so any measured value at all passed. Now a zero baseline requires an
  explicit `atol`.
- **A part with no `mesh:` block and no `expect.mesh` reached the input file as
  an empty `*Part` with a live `*Instance`** and the job completed, that part
  contributing no mass and no stiffness. Refused; the trigger was leaving out
  one optional key.
- **An assembly boolean created a part nothing meshed.** `InstanceFromBooleanCut`
  left an instance with zero elements; `PartFromBooleanMerge` created a part
  nothing instances and suppressed nothing, so what solved was the model from
  before the merge. Both refused by name, and the route out —
  `makeIndependent` then mesh the result — is now a gate item rather than a
  claim.
- **A whole-part section assignment overrode the spec's own.** A bar
  partitioned and given aluminium on one half solved entirely as steel.
- **A CalculiX run reported a mode shape as a displacement.** A
  `geometry.type: custom_inp` spec carries its physics in the deck, but the
  capability matrix reads `analysis.step_type` off the *spec*, so a deck whose
  step is `*FREQUENCY` was graded as a static run. ccx solved it, exited 0 and
  dropped nothing; the extractor's "the last block is the final state" is false
  for an eigenvalue `.dat`, where the repeated blocks are modes, so the last
  mode's tip component came back as `U_TIP_MM = -110.9003` on a 200 mm beam
  from a deck with no load card at all — tagged Abaqus-equivalent and graded
  PASS/FAIL against a real baseline. The procedure cards now sit with the
  unverified contact cards and are refused before the solve, and the extractor
  refuses an eigenvalue `.dat` outright.
- **A positioning constraint left the part exactly where it was.**
  `FaceToFace`, `ParallelFace`, `EdgeToEdge` and `CoincidentPoint` were
  reachable in the dialect and could not work: `{select:}` always compiles to a
  GeomSequence — `core/selectors.py` returns what `getByBoundingBox` produced,
  never an entity out of it — and measured on Abaqus 2021, all four handed that
  sequence return `None`, add nothing to `a.features`, grow no repository and
  move nothing, before and after `a.regenerate()`, without raising. Handed the
  entity itself they return a named `Feature` and move the instance 40.0 /
  10.0 / 30.0 / 30.0 mm. So a bolt written the obvious way stayed 40 mm from
  where the spec put it, in a deck that meshed, solved and reported COMPLETED.
  New `{one: "<instance>:face@x=min"}` argument form passes the entity, forcing
  the count assertion to exactly one — one form rather than a
  `face_at`/`edge_at`/`cell_at` family, so it serves any method wanting a
  single entity of any kind. And the old spelling is now refused at run time by
  its return value, not by whether anything changed: `makeIndependent` and
  `seedPartInstance` also change nothing and are the documented way to mesh a
  boolean result.
- **`expect:` on a part feature was accepted and dropped.** It is honoured on
  an interaction and a condition and refused on `model_setup` and a step;
  here it passed schema validation, generated a full deck, and the number it
  stated appeared nowhere in it. Refused, pointing at the part's own `expect:`.
- **`expect:` on an assembly operation was accepted and dropped too** — same
  shape, but here the right answer is to honour it, because an operation
  returns a modelling result and one of its failures is silent. Measured: a cut
  that removes nothing *raises*, but a merge across a gap does not — it returns
  a part carrying every cubic millimetre of both bodies and **two** cells
  instead of one, so what solves is two loose pieces where the spec asked for
  one solid. `volume` and `cells`, measured on what the call returned, matched
  by shape rather than by method name: an `InstanceFromBooleanCut` result
  carries `partName` and no `getVolume`, a `PartFromBooleanMerge` result the
  other way round, and a pattern returns a tuple, which is refused as
  unmeasurable with a pointer to `assembly.expect`.
- **A misspelt parametric path created the key it could not find.**
  `geometry.HH` instead of `geometry.H` gave five variants of one identical
  model, five `COMPLETED` rows, five full solves paid for (the invented key
  made each resume fingerprint unique), and a sensitivity report reading
  `0.0000` with a direction. Every v2 sweepable number sits behind a list index
  (`parts.0.mesh.seed`), and those crashed inside a private function with
  `AttributeError: 'list' object has no attribute 'setdefault'`. A path now
  addresses a value the spec already carries, lists are walked by index, and a
  path that names nothing is refused before a single licence is taken — naming
  the keys that *are* there, and the entries' own names so nobody has to count.

- **A bore in exactly the right place was refused for being too big.** The
  default tolerance on `expect.cylinders[].at` was a flat 0.05 mm, sized once
  against a 30 mm flange. `getCentroid()` is a tessellation estimate whose own
  error grows with the feature, so past a certain size the check was tighter
  than the instrument reading it: measured on Abaqus 2021, a through bore of
  r = 300 in a 900 mm plate reports its centroid 0.070931 off an analytically
  exact position, and the old default refused it. The default now follows the
  radius, `max(1e-3, r * 2e-3)`; `assembly.expect.at[].tol` follows the
  instance's own span, computed in the kernel because that is the first moment
  the span exists. A gate item runs the counterexample three ways — correct
  position accepted, the old 0.05 stated by hand still refusing it, and the
  same bore moved 5 mm still refused — so the loosening cannot quietly turn the
  check off. Every passing position check now logs its margin
  (`off by X of Y allowed`), and false refusals have a reporting channel
  (`CONTRIBUTING.md`, `.github/ISSUE_TEMPLATE/false_refusal.yml`), because a
  truth layer that refuses correct geometry gets switched off, and a switched-off
  truth layer is not one.

- **A keyword insert put the card in the deck and made the deck unreadable.**
  `keywordBlock.insert(position, text)` places the text *after* block
  `position` of `sieBlocks`, so the integer decides everything. Same spec, same
  `*Damping, alpha=0.5`, one integer apart, both measured on Abaqus 2021: after
  block 21 (the end of `*Elastic`) the deck datachecks with 0 errors; after
  block 3, inside the generated `*Element` table, CAE wraps the edit in a
  `*Conflicts` block, which is not an analysis keyword — the input file
  processor reports **4 FATAL ERRORS** and terminates before the first
  increment. Both builds reported success and both logged `KEYWORD_OK`, because
  the read-back only asked whether the text was present. It now also refuses a
  deck carrying `*Conflicts` and removes the input file, naming both positions
  so the message says what to do. Three claims written into that layer from the
  shape of the API turned out to be false and are corrected in place: an
  out-of-range position raises `IndexError` rather than landing nowhere
  quietly, `synchVersions` was not required first, and a later `synchVersions`
  did not discard the edit. What no build-stage check can see is a card that is
  conflict-free and illegal where it landed (`insert(1)`: no wrapper, 1 fatal
  error) — the input file processor is the only thing that knows, and it says
  so loudly, so it is left to the job rather than guessed at.
- **The evidence collector answered "nothing here" when it did not understand
  its input.** `scripts/collect_gate_evidence.py` only knew the
  `{"items": [...]}` shape a single gate prints. Handed the harness roll-up,
  `{"gates": [...]}`, it wrote a summary reading `0 pass, 0 fail, 0 skipped`
  over a real seventeen-gate evidence file and exited 0. It now handles both
  shapes explicitly, refuses anything else, and leaves the target file
  untouched when it refuses — the same failure mode this release fixes in the
  model layer, found in the tool that publishes the proof.

### Added — the gate for the case that carries everything

- **`scripts/run_bearing_block_check.py`**, seven items on the case where every
  layer of the dialect is present at once. Three arithmetic identities — the
  summed vertical reaction is the sum of three weights, plus a 240 N pressure
  term in step 2, and a Coulomb `mu*N` in step 3 — and then the failure those
  identities cannot see. Measured: with the bore's local seeds stripped and the
  tie tolerance at 0.05, Abaqus leaves eleven blocks of secondary nodes untied
  and raises 85 constraint findings, and all three identities still land within
  0.004%, 0.0003% and 0.00008% of theory. Equilibrium does not care which nodes
  carry the load, so only the `.dat` can tell the two models apart.
- **A correction to what keeps that tie bound.** The case credits the local
  seeds; it also, in the same change, widened the tie tolerance from 0.05 to
  0.1. All four combinations, measured: the seeds bind it at either tolerance,
  and widening alone silences the warning on a mesh that gained no elements.
  Two fixes where one was needed, and the spare one is the anti-fix the design
  doc warns about. The gate therefore pins the tolerance at 0.05 wherever the
  mesh is the variable, and `--tie-tolerance 1.0` is the mutation that must
  make the whole script fail — verified, exit 1, on the coarse-mesh item and on
  a bushing sitting 0.5 mm out of its bore.
- Also measured, and worth twenty minutes to anyone extending this: a tie is
  resolved when the model is assembled, not when it converges. `WILL NOT BE
  TIED` appears in `<job>_syntaxcheck.dat` exactly as in the analysis `.dat` —
  eleven blocks in both — so the constraint items run a datacheck and skip the
  solve, which took them from 704 s to 19 s.

### Changed

- `scripts/run_all_real_checks.py` reads both output contracts in the tree and
  runs seventeen gates rather than five. It used to `json.loads` the whole of
  stdout, which judged FAIL every gate that prints its item list first — nine
  of them — and a timeout raised out of the run instead of failing one gate.
- `SECURITY.md` no longer claims an AST guard on generated scripts. The tool it
  named was never on the data path, is not in the published tree, and rejects
  this project's own decks. Replaced with what is true: no model-written code
  is executed.
- `docs/COPILOT_MVP.md` no longer hands you `--host 0.0.0.0` with no warning,
  which contradicted `SECURITY.md` in the same published tree.
- `requirements.txt` pins `mcp>=1.0,<2` to match `pyproject.toml`;
  `mcp_server.py` imports `mcp.server.fastmcp`, which moved in 2.0.0.

## [Unreleased] - 2026-08-03

### Added — Chinese and English

- **The interface switches between Chinese and English.** Chinese stays the
  source language and the fallback: it is what the users this is built for
  read, and a missing English string shows the Chinese one rather than a raw
  key. The choice follows the browser on a first visit, is remembered after
  that, and is shared by both pages.
- `README.zh-CN.md`, written for a Chinese reader rather than translated
  sentence-by-sentence from the English. Both READMEs link to each other.
- One message catalogue (`core/messages.py`) for backend text that reaches a
  human — CalculiX refusals, backend labels, offline planner replies. The
  browser fetches it from `GET /api/i18n/messages` instead of keeping a second
  copy, so the two can never describe the same refusal differently.
  A refusal travels as a key plus parameters, because it is written into
  `result.json` and read back later, possibly by someone reading in the other
  language; it is rendered at display time, not at solve time.
- Two gates, because "we support English" is easy to claim and quiet to break.
  `scripts/run_i18n_static_check.py` holds the catalogues to the markup and
  ratchets the count of untranslated lines down to zero.
  `scripts/run_i18n_ui_check.py` drives both pages in a real browser and
  checks what counting strings cannot: that switching language does not
  destroy a solve report, that a refusal reads in English, that the choice
  survives a reload, and that a missing `/static/i18n.js` cannot take the page
  down with it.

### Changed

- **Licence: AGPL-3.0-or-later**, with a commercial licence available for use
  that copyleft does not suit (`LICENSING.md`). Every claim about the licence —
  `pyproject.toml`, the README badge, the footer — now says the same thing.
- **The licence gate is gone, not stubbed.** `premium/` became `features/` and
  `premium/licensing.py` was deleted; there is no always-true placeholder left
  behind. Every feature in the repository is in every copy of it. One
  side effect worth knowing: `analysis.max_retries` used to be silently inert
  because the gate defaulted closed, and now actually retries.
- Release bundles no longer carry the GPLv3 ffmpeg build that `imageio_ffmpeg`
  vendors (it was 73% of the bundle). `THIRD_PARTY_NOTICES.md` records what
  ships and under what terms.

### Added

- **CalculiX fallback backend**, so the project is usable without an Abaqus
  licence. Deliberately narrow — `cantilever_block` / `custom_inp` geometry,
  `Static` steps, concentrated forces — and everything outside that is
  **refused before the solve starts**, naming the spec field in plain language.
  The refusal is the feature: CalculiX silently drops load cards it does not
  recognise, exits 0, and returns a model where every displacement is
  `0.000000E+00`. On the shipped cantilever it agrees with the Abaqus baseline
  to seven significant figures. Its Mises does not and cannot — nodal-averaged
  `.frd` stress versus unaveraged Abaqus `ELEMENT_NODAL`, ~6% apart on the same
  mesh — so that KPI carries its provenance and is excluded from pass/fail
  rather than graded against a baseline it does not mean the same thing as.
- `ABAQUS_AGENT_SOLVER_BACKEND` (`auto` / `abaqus` / `calculix` / `demo`).
  Naming a solver the machine does not have is an error, never a silent
  downgrade to demo output.
- The workbench and the landing page share one design system, link to each
  other, and open on an actionable empty state instead of a blank pane.
- `docs/ROADMAP.md`, including the rule that decides when a capability may be
  called "supported": a passing real-solver check, not an existing code path.
- The publish gate reads markdown. It immediately found four broken links in
  the README, two of which were the headline demo's own screenshot and
  recording.

### Fixed

- **Pressure loads lost their sign**, so `plate_hole` — a tension case — had
  been solved in compression since 2026-06-06. Mises is magnitude-only, so the
  stress baseline still matched and nothing looked wrong; only the displacement
  KPI, sitting at exactly 0.0 because every U1 was negative, gave it away.
- **A failed solve could be reported as complete.** The Abaqus launcher exits 0
  even when the analysis aborts, and the pipeline trusted the exit code. The
  `.sta` verdict now decides, and a failure is reported by quoting the solver's
  own last lines verbatim.
- **Deck reuse required only that a file existed.** A cached `.inp` is now
  reused only against a fingerprint of the spec, the probed solver release and
  the source deck; anything missing, corrupt, mismatched or hand-edited
  rebuilds, and the reason is printed.
- **A KPI location is honoured or refused, never quietly widened** to the whole
  model.
- Failed and refused runs have somewhere to explain themselves in the UI
  instead of rendering as an empty result.
- The targeted Abaqus release is probed from the installed solver rather than
  asserted by the spec, and the UI no longer offers versions the machine does
  not have.
- The container published a port it never listened on; `docker compose up` now
  reaches the workbench, bound to loopback.
- Feature registration no longer depends on import order, and import failures
  are reported instead of leaving a capability silently absent.
- Subprocess reads no longer die on the first non-UTF-8 byte a solver emits
  under a GBK code page.
- The frozen `MISES_MAX` baseline was annotated as an integration-point value
  when the extractor has requested `ELEMENT_NODAL` since 2026-05-02. The number
  was right; its description was the opposite of the truth.

### Security

- The local API is no longer drivable by any web page a user happens to visit.
  It launches solver jobs and reads and writes the filesystem with no
  authentication, and was configured with `allow_origins=["*"]` while binding
  `0.0.0.0` outside frozen builds. CORS is now opt-in and never wildcarded
  (`ABAQUS_AGENT_CORS_ORIGINS`); the bind address is loopback everywhere, with
  `ABAQUS_AGENT_HOST` as the deliberate escape hatch.

## [Unreleased] - 2026-07-19

### Added (workbench P2-α: interactive 3D viewport)

- `post/export_odb_mesh.py`: exports the ODB exterior surface (hex/tet/wedge/
  shell/2D families) + nodal Mises / displacement fields as compact JSON;
  pure-python topology core is unit-tested without Abaqus; wired into the
  orchestrator as a best-effort stage after contour export.
- Workbench results view embeds a three.js viewport (vendored r128 UMD,
  offline): drag-rotate/zoom, Abaqus-style rainbow vertex contours with
  legend, field switcher (Mises / |U|), deformation overlay, and — for modal
  runs — a live sine mode-shape animation labeled with the real frequency.
  Falls back to the PNG contours when mesh.json or WebGL is unavailable.
- Showcase asserts `viewport_3d` per scene; all four real-solve scenes PASS
  with the viewport rendering in headless chromium.

### Added (Cursor-style workbench P0)

- `/workbench`: three-pane Cursor-style IDE for FEA — chat pane drives spec
  proposals, center shows spec.yaml / red-green diff / results, bottom console
  streams the real solve live (SSE with polling fallback), left rail is the
  run timeline. Accepting a proposal is the only path to a real solve.
- Chat-driven spec proposals with diff-accept loop
  (`workbench/` module: sessions persisted to disk, `POST .../chat`,
  `POST .../accept`, `POST .../reject`); accept reuses the existing
  `RUNS`/`run_pipeline`/SSE/artifact machinery unchanged.
- `claude_cli` planner backend: headless `claude -p` via stdin pipe (the npm
  `claude.CMD` shim truncates multi-line argv on Windows), schema-constrained
  prompt with one validation-error retry, template fallback when the CLI is
  missing or fails. Replies include a theory estimate (e.g. FL³/3EI) for the
  requested case.
- Results view: KPI cards, ODB contour images served per-run, and a
  KPI diff table against the previous completed run (simdiff).
- Real-solve E2E gates: `scripts/run_workbench_real_check.py` (API-level) and
  `scripts/run_workbench_browser_check.py` (Playwright chromium drives the
  actual UI: type → proposal → accept → live console → KPI cards + contour
  pixels loaded). Both PASS on real Abaqus; evidence under
  `artifacts/workbench/`.

### Fixed (Cursor-style workbench P0)

- `cantilever_block` TIP_NODES: nearest-node-to-face-center selection instead
  of a bounding box that silently produced an empty set (and a fatal *CLOAD
  error) whenever the seed didn't place a node exactly at the face center —
  e.g. seed 2 on a 10×10 section. Any "refine the mesh" request used to kill
  the solve.

## [Unreleased] - 2026-07-05

### Added (evening iteration)

- Session history picker: browse recent Copilot sessions (⚠ marks failures),
  restore any of them with plan/chips/model tree/viewport, and repoint the CAE
  plugin (`GET /api/copilot/sessions`, `GET /api/copilot/sessions/{id}/full`)
- Two more theory-checked scenarios: plate-with-hole tension (`Kt = 2.73` vs
  Howland ≈ 3.1 on the demo mesh, full-integration C3D8 after C3D8R was caught
  under-reading the surface peak at 2.32) and cantilever modal analysis (first
  bending 360.6 Hz vs Euler-Bernoulli 417.8 Hz, physically-correct paired modes)
- Replay scenario picker with four recordings (cantilever fail→fix, simple beam,
  plate hole with Kt, modal with 5 frequencies); `/api/copilot/replays` +
  whitelisted `?name=`
- Live sessions now show solver KPIs in the workspace status card (the plugin
  ships the extract script's result dict with the completed submit action)
- CAE failure pattern library grown 6 → 15 (name collisions, generated-code
  SyntaxError, API parameter mismatch, disk full, permissions, MemoryError,
  missing sections…), matched against the real `exec` traceback shape
- Doctor panel: CAE pattern gallery + self-service "paste your traceback"
  diagnosis box (`GET /api/doctor/cae-patterns`, `POST /api/doctor/cae-diagnose`)
- Cantilever tip-deflection theory gate (dial-gauge node vs PL^3/3EI, 1.31x on
  the demo mesh — consistent with the simple beam's 1.30x) and a cantilever
  modal scenario; consolidated real-machine gate `scripts/run_all_real_checks.py`
  (5 gates, ~3 min, all PASS)
- CAE traceback diagnosis exposed as an MCP tool (`diagnose_cae_error_tool`)
- All four replay recordings refreshed so the green 求解结果 KPI card shows
  during playback

### Added

- Replay mode: `▶ 播放真实录像` plays back a recorded real-Abaqus session in the
  workspace (chat → plan typewriter → action chips → model tree → viewport PNGs →
  real stale-lock failure → one-click fix → solver KPIs) with no Abaqus installed;
  recording ships in `evidence/copilot_replay/replay.json` and
  `scripts/record_copilot_replay.py` re-records it live
- Plain-language CAE failure diagnosis (`doctor/cae_errors.py`): stale lock, license,
  missing model/part, geometry selection, missing ODB, aborted job — shown as a card
  above the raw traceback; `让 Copilot 修复` is now one click and diagnosis-aware
- Solver Doctor auto-pass on failed solves: the plugin ships `.msg/.sta/.dat/.log`
  tails with the failure and the error card shows category/summary/recommendations
- Second scenario: simply-supported (three-point bend) beams via 简支/三点弯 keywords,
  with a dial-gauge `midspan_deflection` KPI (real-solve verified within 30% of
  PL^3/48EI on the coarse demo mesh)
- Copilot sessions persist across server restarts and the workspace auto-resumes the
  last session on page load (`/api/copilot/sessions/active`)
- First-visit replay hint, post-replay next-steps guidance, Enter-to-send input,
  rotating example prompts, README "See It In 60 Seconds" section with screenshot
- Browser-level verification of the replay UI in headless Edge; real-solve gates
  `scripts/run_simple_beam_real_check.py` and `scripts/run_solver_doctor_real_check.py`

### Fixed

- Aborted solves no longer masquerade as COMPLETED with 0.0 KPIs: the submit script
  verifies job status (falling back to the solver's `.sta` verdict, since
  `job.status` can be None in noGUI kernels) and raises into the diagnosis loop
- A failed action no longer counts toward `completed_count` (no more "3/3 完成"
  next to a failure); error pane resets its empty state when errors clear
- Codex app-server bridge works on Windows again (npm `.cmd` shim: spawn PATHEXT
  ENOENT + Node ≥18.20 EINVAL both bypassed by running `codex.js` directly)
- Alpha Gate reads a tracked evidence snapshot (`evidence/copilot_alpha/`) when
  gitignored `artifacts/` copies are missing, so fresh clones report
  ALPHA_READY_WITH_GUI_BLOCKER instead of FAIL
- Dimension inference prefers mm-suffixed numbers so a force like `50N` can't become
  a beam width; force parsed from the N-suffixed number

## [0.1.0] - 2026-03-07

### Added

- 7-stage Abaqus FEA pipeline: validate, build, syntaxcheck, submit, monitor, extract, compare
- MCP (Model Context Protocol) server for AI agent integration
- HTTP-to-MCP bridge for web clients
- FastAPI REST API with SSE streaming for real-time progress
- Web frontend with transport mode toggle (Direct API / MCP)
- NL-to-Spec generation via LLM (Anthropic, OpenAI, or template fallback)
- 5 premium features: multi-physics coupling, mesh adaptivity, parametric sweeps, extended geometry, auto-repair
- Static AST security guard blocking dangerous code in LLM-generated scripts
- Schema validation for problem specifications
- 4 benchmark cases: cantilever, plate_hole, modal, explicit_impact
- Benchmark runner with Markdown report generation
- 197 unit tests (no Abaqus required)
- Structured error codes with recovery suggestions
