"""Every place the project states its licence must state the same one.

Measured defect: LICENSE was AGPL-3.0 while README's badge, README's footer and
pyproject's `license` field all still said Apache-2.0. `pip show` confirmed the
installed metadata read `License-Expression: Apache-2.0`.

pyproject is the one that actually bites: it is machine-readable, and PyPI,
SBOM scanners and the GitHub dependency graph read it rather than LICENSE. A
dual-licence business model rests entirely on the AGPL being the stated
default, so a stray Apache-2.0 there gives away the thing being sold.

The two carve-outs are deliberate and documented in NOTICE:
  * schema/, cases/, examples/ stay Apache-2.0 (integration surface)
  * the 2026-03-06..2026-06-16 releases were Apache-2.0, irrevocably
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANONICAL = "AGPL-3.0-or-later"


def test_license_file_is_the_agpl():
    head = (ROOT / "LICENSE").read_text(encoding="utf-8")[:400].upper()

    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in head
    assert "VERSION 3" in head


def test_pyproject_declares_the_same_licence():
    """The only declaration a machine reads."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    match = re.search(r'^license\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "pyproject has no license field"
    assert match.group(1) == CANONICAL, (
        "pyproject says %r; PyPI / SBOM / dependency graph read this one"
        % match.group(1))


def test_pyproject_carries_no_stale_apache_classifier():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    classifiers = re.findall(r'"License :: [^"]+"', text)

    for entry in classifiers:
        assert "Apache" not in entry, entry


def test_readme_badge_and_footer_say_agpl_not_apache():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    badge = [ln for ln in readme.splitlines() if "img.shields.io/badge/license" in ln]
    assert badge, "licence badge disappeared"
    assert "Apache" not in badge[0], badge[0]
    assert "AGPL" in badge[0], badge[0]

    footer = readme.split("## License", 1)
    assert len(footer) == 2, "README lost its License section"
    body = footer[1]
    assert CANONICAL in body
    # Apache may only appear as the documented carve-out, never as the project
    # licence.
    for line in body.splitlines():
        if "Apache" in line:
            assert ("schema/" in line or "2026-03-06" in line
                    or "LICENSES/Apache-2.0.txt" in line
                    or "inbound" in line.lower()), (
                "unqualified Apache claim in the License section: %s" % line)


def test_the_chinese_readme_states_the_same_licence():
    """A translation is a second licence statement, not a copy of one.

    README.zh-CN.md ships in the public tree with its own AGPL badge, its own
    License section and its own rendering of both Apache carve-outs. Nothing
    pinned it, so it could have drifted — and a dual-licence business rests on
    every statement of the default agreeing.
    """
    readme = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")

    badge = [ln for ln in readme.splitlines() if "img.shields.io/badge/license" in ln]
    assert badge, "the Chinese README lost its licence badge"
    assert "AGPL" in badge[0] and "Apache" not in badge[0], badge[0]

    heading = [ln for ln in readme.splitlines()
               if ln.startswith("## ") and "许可" in ln]
    assert heading, "the Chinese README lost its License section"
    body = readme.split(heading[0], 1)[1]
    assert CANONICAL in body

    for line in body.splitlines():
        if "Apache" in line:
            assert ("schema/" in line or "2026-03-06" in line
                    or "LICENSES/Apache-2.0.txt" in line
                    or "入站" in line or "inbound" in line.lower()), (
                "unqualified Apache claim in the Chinese License section: %s" % line)


def test_the_carve_outs_stay_documented():
    """If these vanish, contributors and integrators lose the only written
    statement that schema/cases/examples are safe to build against."""
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")

    for marker in ("schema/", "cases/", "examples/",
                   "LICENSES/Apache-2.0.txt", "AGPL"):
        assert marker in notice, marker
    assert (ROOT / "LICENSES" / "Apache-2.0.txt").is_file()
    assert (ROOT / "LICENSING.md").is_file()
