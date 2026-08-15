"""The five shipped v2 decks, pinned from `# --- Materials` onward.

WHY THIS EXISTS. `run_id = sha256(spec)`. The deck text is not part of it, so a
generator change that alters what a shipped case builds reuses the same run
directory and silently replaces a frozen Abaqus baseline with a different
model. The baselines under `cases/*/runs/` are unreproducible evidence: they
were measured on one machine, on one release, and the spec hash that names them
cannot be recomputed for a spec that has since changed.

WHY ONLY THE MODEL SECTION. Every deck opens with the same `_HELPERS`
preamble -- selector resolution, the truth-layer checks, the dispatch shim.
That block grows whenever a new check is added, and it is inert: it defines
functions and runs nothing. Hashing the whole deck would fail on every commit
that adds a helper, and a guard that always fails is a guard nobody reads. The
marker `# --- Materials` is where `_materials` starts emitting, downstream of
`_header` and `selectors.RUNTIME` in the block list, so everything from it on
is the model this spec actually builds.

ONE CONVENTION, ON PURPOSE. There are two defensible spellings --
`text[text.index("# --- Materials"):]` and splitting on `"\\n# --- Material"` --
and they differ by a leading newline, so their hashes never match. Mixing them
across commits produces a "moved" report that is really a convention change.
This file is the convention.

WHEN ONE OF THESE MOVES. It is not automatically wrong. It means the generator
now builds those cases differently, which is a decision, not an accident:
update the constant here, say in the commit message what changed and why the
new deck is the right one, and archive the affected run directories first
(docs/BUILD_SPEC.md, evidence preservation) because they will rebuild in place
on next use -- runner/build_model.py fingerprints the whole emitted script, so
any preamble change already invalidates their cache.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner import build_v2  # noqa: E402

MARKER = "# --- Materials"

# Measured 2026-08-08. Moved by #79 (geometric-face export in the preview
# dump). The MODEL is untouched: [# --- Materials, # --- Preview dump) and
# the job section were compared byte-for-byte between the old and new
# generator for all five cases and are identical (artifacts/_frozen_pin_probe
# .py) — only the preview instrumentation inside the pinned range grew. Runs
# archived to artifacts/runs_archive/20260808_frozen_pin_79/ (8 dirs, file
# counts verified) because build_model fingerprints the whole script and will
# rebuild them in place on next use.
FROZEN = {
    "bearing_block": "30e3d6fee2e4f3e8",
    "block_friction_slide": "b14269ae5a0516e9",
    "plate_hole_v2": "bc6b8f85a77b7afa",
    "two_plate_contact": "d69e35bb79222724",
    "two_plate_tie": "0f16a4a37be3515d",
}


def _model_section_sha(case: str) -> str:
    spec = yaml.safe_load(
        (ROOT / "cases" / case / "spec.yaml").read_text(encoding="utf-8"))
    text = build_v2.generate_script(spec)
    section = text[text.index(MARKER):]
    return hashlib.sha256(section.encode()).hexdigest()[:16]


@pytest.mark.parametrize("case", sorted(FROZEN))
def test_the_model_section_is_unchanged(case):
    assert _model_section_sha(case) == FROZEN[case], (
        "%s now builds a different model. If that is deliberate, update FROZEN "
        "in this file, say in the commit message what changed and why the new "
        "deck is the right one, and archive cases/%s/runs/* first -- the "
        "baselines there were measured against the old deck and cannot be "
        "reproduced from a spec that has since changed." % (case, case))


def test_every_shipped_v2_case_is_pinned():
    """A new case must not be able to join the tree unwatched."""
    shipped = set()
    for spec_path in sorted((ROOT / "cases").glob("*/spec.yaml")):
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        if isinstance(spec, dict) and spec.get("parts"):
            shipped.add(spec_path.parent.name)
    assert shipped == set(FROZEN), (
        "cases with a `parts:` block are built by runner/build_v2 and must be "
        "pinned here. Unpinned: %s. Pinned but gone: %s."
        % (sorted(shipped - set(FROZEN)), sorted(set(FROZEN) - shipped)))


def test_the_marker_is_where_the_model_starts():
    """The guard is worth nothing if the marker drifts into the preamble."""
    spec = yaml.safe_load(
        (ROOT / "cases" / "two_plate_tie" / "spec.yaml").read_text(encoding="utf-8"))
    text = build_v2.generate_script(spec)
    assert text.count(MARKER) == 1
    section = text[text.index(MARKER):]
    assert "def _sel_resolve(" not in section, "the preamble leaked into the pin"
    assert "mdb.Model(" not in section, "the model is created before the marker"
    assert "m.Material(" in section, "materials are the first thing pinned"
