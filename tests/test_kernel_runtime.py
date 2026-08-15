"""The kernel runtime is a payload, and a split payload must still be the same bytes.

runner/kernel_runtime.py holds the Python 2.7 that the Abaqus kernel executes,
as text. It is split into seven named chunks so a reader can find the mesh
checks without paging through the selector resolvers -- navigation only. The
moment that split is allowed to change what the chunks concatenate to, it stops
being a split and becomes an edit to every deck this generator emits.

`tests/test_frozen_model_sections.py` cannot catch that: it deliberately hashes
each deck only from `# --- Materials` onward, because the preamble grows
whenever a check is added and a guard that always fails is a guard nobody
reads. Everything above that marker -- which is exactly this file's subject --
is unguarded by it.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner import build_v2, kernel_runtime  # noqa: E402

SRC = ROOT / "runner" / "kernel_runtime.py"


def _chunk_names() -> list[str]:
    """The _H_* constants, in source order -- which is the concatenation order."""
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    out = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.startswith("_H_"):
                    out.append(target.id)
    return out


def test_the_chunks_concatenate_to_exactly_what_the_kernel_gets():
    chunks = [getattr(kernel_runtime, name) for name in _chunk_names()]
    assert "".join(chunks) == kernel_runtime.HELPERS
    # Reordering them would still concatenate to the same LENGTH, so the join
    # above is checked against content, and the order is checked separately.
    assert kernel_runtime.HELPERS.index("def _tie(") < \
        kernel_runtime.HELPERS.index("def _gcall(") < \
        kernel_runtime.HELPERS.index("def _mesh_check(")


def test_build_v2_still_serves_the_same_two_constants():
    """The generator imports them; the rest of the tree reads them off
    build_v2. Both names have to keep resolving to the same objects."""
    assert build_v2._HELPERS is kernel_runtime.HELPERS
    assert build_v2._PREAMBLE is kernel_runtime.PREAMBLE


def test_the_runtime_is_python_2_7_and_says_so():
    """The kernel on this machine reports 2.7.15. Abaqus only moved to 3.10.5
    at the 2024 release, so an f-string here is a SyntaxError inside a solver
    run -- the most expensive place to find one."""
    tree = ast.parse(kernel_runtime.HELPERS)
    # Parsed, not grepped. The first draft of this test looked for the two
    # characters "f'" and matched `'%.6f_%.6f' % (...)` in _expect_placed --
    # a substring search cannot tell an f-string from a float format.
    kinds = {type(n).__name__ for n in ast.walk(tree)}
    assert "JoinedStr" not in kinds, "an f-string reaches the 2.7 kernel"
    assert "AnnAssign" not in kinds, "an annotated assignment reaches 2.7"
    assert not [n for n in ast.walk(tree)
                if isinstance(n, ast.arg) and n.annotation], "annotated arg"
    assert not [n for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.returns], "a return annotation reaches 2.7"
    assert "pathlib" not in kernel_runtime.HELPERS


def test_every_chunk_is_small_enough_to_read():
    """The point of the split. A chunk that grows past a few hundred lines has
    become the thing this file was made to stop."""
    for name in _chunk_names():
        lines = getattr(kernel_runtime, name).count("\n")
        assert lines < 500, "%s is %d lines; split it" % (name, lines)


def test_the_chunk_list_is_not_stale():
    """If someone adds an _H_* constant and forgets the concatenation, the
    first test still passes -- it joins whatever it finds. This one fails."""
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    joined = None
    for node in tree.body:
        if (isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "_HELPERS"
                        for t in node.targets)):
            joined = {n.id for n in ast.walk(node.value)
                      if isinstance(n, ast.Name)}
    assert joined == set(_chunk_names()), (
        "chunks defined but not concatenated: %s"
        % sorted(set(_chunk_names()) - (joined or set())))
