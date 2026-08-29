"""No source file in this repo grows past the size a person can hold.

The rule is 800 lines. It was not enforced, and runner/build_v2.py reached
6021 -- one file holding the spec compiler, the element tables, the argument
grammar, the preview payload and 1777 lines of Python 2.7 for the Abaqus
kernel. Nobody decided that; it accreted one honest commit at a time, which is
exactly why a decision is not enough and a test is needed.

The exemption list is the interesting part. Every entry is a file that is over
and is not being split today, with the reason and the intended end state
written down. A file that stays on this list without its number coming down is
a file nobody is working on -- which is information, not an excuse.
"""

from __future__ import annotations

from pathlib import Path

from tests.repo_sources import is_captured_artefact

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 800

# path -> (ceiling, why it is not 800 today)
#
# Ceilings are the CURRENT size rounded up a little, not aspirations: the test
# fails if a listed file GROWS, so the list cannot be used to park a file and
# keep adding to it.
EXEMPT = {
    "runner/kernel_runtime.py": (
        1900,
        "Not code -- the Python 2.7 the Abaqus kernel executes, as text. Split "
        "into seven named chunks (54-420 lines) that "
        "tests/test_kernel_runtime.py pins byte-identical. Splitting it across "
        "FILES would put a `+` between two halves of one program for no "
        "reader's benefit."),
    "frontend/index.html": (
        4450,
        "Was 7029. The stylesheet is now frontend/index.css and the "
        "translation catalogue frontend/index_i18n.js; what is left is markup "
        "plus behaviour, and the behaviour splits next by panel (copilot, "
        "evidence, doctor, bench) the way the workbench viewport already did."),
    "frontend/index.css": (
        2000,
        "One stylesheet for the tools page, on top of the shared tokens in "
        "design-system.css. Long because the page carries four panels; it "
        "splits when the behaviour does."),
    "frontend/workbench.html": (
        2350,
        "Was 3616. The stylesheet is now frontend/workbench.css and the "
        "translation catalogue frontend/workbench_i18n.js; what is left is "
        "markup plus behaviour, and the behaviour splits next by panel."),
    "frontend/workbench.css": (
        1000,
        "One stylesheet for the workbench, on top of the shared tokens in "
        "design-system.css. Long because the app is dense, not because two "
        "things are mixed; it splits by panel when the markup does."),
    "server.py": (
        1550,
        "Was 2249. The 21 /api/copilot routes and the session store they own "
        "are in copilot/routes.py, and the evidence artifact registry is in "
        "evidence/artifact_registry.py. The 14 /api/evidence routes are the "
        "next group out; they are now thin enough to move as a router."),
    "runner/build_v2.py": (
        2740,
        "Was 6021. Out so far: the kernel runtime, the argument grammar, the "
        "element tables, the preview payload, the named profiles "
        "(runner/v2_profiles.py) and the tie/contact emitters "
        "(runner/v2_pairs.py). What is left is the rest of the deck emitters, "
        "which split next along the block list in generate_script."),
    "mcp_bridge.py": (
        1100,
        "Was 1281. It documents itself as a proxy and is not one -- roughly 16 "
        "handlers run in-process, and 203 of its lines were a second copy of "
        "the evidence artifact registry, now shared. Deleting the in-process "
        "handlers is the rest of the split."),
    "core/material_library.py": (
        900,
        "Does four jobs -- load the cards, resolve a spec's `library:` keys, "
        "search, and render provenance -- and only resolve_spec_materials is "
        "on the run path."),
    "agent/orchestrator.py": (
        950,
        "Stage driving and grading policy in one class: the nine _stage_* "
        "methods are a pipeline, _stage_compare and _stage_contracts are the "
        "verdict, and they change for unrelated reasons."),
    "frontend/workbench_viewport.js": (
        900,
        "One WebGL viewport, but four concerns in it: scene setup, the contour "
        "ramp, face/part picking, and deformation scaling."),
    "runner/build_model.py": (
        1200,
        "The v1 generator, which build_v2 was written to replace. It stays "
        "whole until the last v1 case is migrated -- splitting a module that "
        "is on its way out spends effort twice."),
    "post/parse_inp.py": (
        1000,
        "A parser for a keyword format with about forty card types. The size "
        "is the format's, not the code's; each handler is small."),
    "post/extract_kpis.py": (
        1000,
        "Runs inside the Abaqus kernel under Python 2.7, so it cannot import "
        "helper modules from this tree -- abaqus python resolves imports "
        "against its own interpreter. Self-contained on purpose."),
    "mcp_server.py": (
        1100,
        "One handler per MCP tool plus the schema literal each one advertises. "
        "The schemas are roughly half of it and belong in a data module."),
    "reporting/templates.py": (
        950,
        "Three report templates (standard, client summary, engineering "
        "delivery) plus the shared status/verdict helpers, in one file."),
    "features/parametric/sweep_engine.py": (
        850,
        "Sweep expansion, run fan-out and result collation. Barely over; the "
        "seam is between expanding the grid and running it."),
}

# Two categories where the limit means something different, with the reason
# stated once rather than copied per file.
#
#   scripts/run_*_check.py  -- a gate must be runnable on its own, on a machine
#       that has Abaqus and may not have this repo installed. Its fixtures,
#       its spec and its assertions travel together on purpose; a gate that
#       imports half of the tree is a gate that can fail for reasons that have
#       nothing to do with what it gates.
#   tests/test_*.py -- a test file is a list of independent cases, not one
#       program. Reading case 40 does not require having read cases 1-39, so
#       the argument the limit rests on does not apply.
EXEMPT_PATTERNS = ("scripts/run_", "tests/test_")

# Directories whose size says nothing about maintainability.
#
# `evidence` is NOT here, and that is a correction: it was, and it hid eight
# source modules from this gate -- including evidence/real_smoke_contract_diff.py
# at 465 lines and evidence/artifact_registry.py, which was added *by* a split
# done to satisfy this gate. The reason it was skipped is the 297 captured
# solver artefacts under evidence/real_abaqus_smoke_*/; those are still
# skipped, by tests/repo_sources.is_captured_artefact.
SKIP_DIRS = {".git", ".venv", "node_modules", "artifacts", "dist", "build",
             "vendor", "__pycache__", "cases", "course", "docs",
             ".pytest_cache", "htmlcov", "runs", "runs_archive"}
SUFFIXES = {".py", ".js", ".html", ".css"}


def _sources() -> list[tuple[str, int]]:
    out = []
    for path in ROOT.rglob("*"):
        if path.suffix not in SUFFIXES or not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if set(rel.parts) & SKIP_DIRS or is_captured_artefact(rel):
            continue
        out.append((rel.as_posix(),
                    path.read_text(encoding="utf-8", errors="replace")
                        .count("\n") + 1))
    return sorted(out)


def _pattern_exempt(name: str) -> bool:
    return name.startswith(EXEMPT_PATTERNS)


def test_no_unlisted_file_is_over_the_limit():
    over = [(name, n) for name, n in _sources()
            if n > LIMIT and name not in EXEMPT and not _pattern_exempt(name)]
    assert not over, (
        "over %d lines and not on the exemption list: %s. Split it, or add it "
        "with a ceiling and the reason." % (LIMIT, over))


def test_no_exempt_file_has_grown():
    grown = [(name, n, EXEMPT[name][0]) for name, n in _sources()
             if name in EXEMPT and n > EXEMPT[name][0]]
    assert not grown, (
        "an exempt file grew past its ceiling: %s. The list records what is "
        "already too big; it is not a budget to spend." % grown)


def test_a_pattern_exemption_does_not_cover_production_code():
    """The two patterns are narrow on purpose. If a module ever lands under
    scripts/run_*.py that is not a gate, or a helper is added to tests/, the
    limit should apply to it again."""
    for name, _n in _sources():
        if _pattern_exempt(name):
            assert name.endswith(".py"), name
            assert name.startswith(("scripts/run_", "tests/test_")), name


def test_the_exemption_list_has_no_ghosts():
    """A file that has been split, renamed or deleted must leave the list, or
    the list stops describing the repo and starts describing its history."""
    names = {name for name, _n in _sources()}
    ghosts = sorted(set(EXEMPT) - names)
    assert not ghosts, "listed but no longer present: %s" % ghosts


def test_every_exemption_says_why():
    for name, (ceiling, why) in EXEMPT.items():
        assert ceiling > LIMIT, name
        assert len(why) > 60, "%s: the reason is too short to be one" % name
