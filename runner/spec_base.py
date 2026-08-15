"""The three things every part of the v2 compiler needs.

Extracted so runner/arg_forms.py, runner/mesh_policy.py and runner/preview.py
can raise the project's own error and parse a selector without importing
build_v2 and creating a cycle. Nothing else belongs here: this file exists to
be depended on, so anything that grows in it is a dependency everyone acquires.
"""

from __future__ import annotations

from core import selectors
from tools.errors import AbaqusAgentError, ErrorCode


class SpecError(AbaqusAgentError):
    def __init__(self, message: str):
        super().__init__(ErrorCode.SPEC_INVALID, message)

def _parse(raw: str, expect, where: str) -> selectors.Selector:
    try:
        return selectors.parse(raw, expect)
    except selectors.SelectorError as exc:
        raise SpecError("%s: %s" % (where, exc))

def _is_generic(entry: dict) -> bool:
    return isinstance(entry, dict) and "call" in entry
