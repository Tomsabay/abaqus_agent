"""What counts as this repo's own source, for the gates that scan all of it.

There is one place in the tree where the answer is not obvious. `evidence/`
holds both: eight modules that this repo wrote, and 297 files captured from
real Abaqus solves and frozen as proof — including three
`build_model_script.py` that the kernel generated and nobody maintains.

Both gates that walk the tree need the same answer, and they used to disagree
by omission: the size gate skipped `evidence/` wholesale (so eight modules,
one of them 465 lines, were never sized) and the subprocess-decoding gate
never listed it at all. Stating the rule once, here, is the point --
`tests/frontend_sources.py` exists for the same reason.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def is_captured_artefact(rel: Path) -> bool:
    """True for a file recorded from a solve rather than written by a person.

    `evidence/vault.py` is ours. `evidence/real_abaqus_smoke_20260605/.../
    build_model_script.py` is a frozen copy of what the run produced; its
    shape is the solver's business, and rewriting it would destroy the
    evidence it exists to be.
    """
    parts = rel.parts
    return bool(parts) and parts[0] == "evidence" and len(parts) > 2
