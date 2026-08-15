"""A gate nobody runs is a gate that does not exist.

scripts/run_all_real_checks.py is the one command that produces a verdict for
the whole engine, and its GATES list is hand-maintained. Nothing ever noticed
a gate script that was written and never added, so gates accumulated outside
it silently -- three separate comments in that file record the same discovery,
each made by accident while adding an unrelated gate, and on 2026-08-09 there
were still nine unlisted.

Hermetic: reads the registry and the directory, runs no gate.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_all_real_checks as harness  # noqa: E402

SCRIPTS = ROOT / "scripts"

# A gate script that is deliberately not in the harness, and why. Kept short
# on purpose: every check written so far belongs in the one command that says
# whether the engine works. Add an entry only with a reason that would still
# read as a reason to someone who did not write it.
EXEMPT: dict[str, str] = {
    "run_from_scratch_planner_check.py": (
        "Drives the real claude CLI: needs the local subscription login, "
        "burns quota, and grades nondeterministic LLM output — a red run can "
        "mean the model changed, not the engine. The harness verdict must "
        "stay deterministic, so this one is run by hand after any planner "
        "prompt change."),
}


def _gate_scripts() -> set[str]:
    return {p.name for p in SCRIPTS.glob("run_*_check.py")}


def _registered() -> dict[str, str]:
    return {Path(script).name: name for name, script, _ in harness.GATES}


def test_every_gate_script_is_registered_or_says_why_not():
    unlisted = sorted(_gate_scripts() - set(_registered()) - set(EXEMPT))

    assert unlisted == [], (
        "%d gate script(s) exist and no one runs them: %s. Add them to GATES "
        "in scripts/run_all_real_checks.py, or to EXEMPT here with a reason."
        % (len(unlisted), unlisted))


def test_the_registry_points_at_files_that_exist():
    """The other direction: a renamed or deleted script leaves an entry that
    fails at run time, in the middle of a harness run that takes ~55 minutes.

    PRIVATE_ONLY names may legitimately be absent: the public distribution
    withholds them, and the harness reports each as NOT_DISTRIBUTED with its
    reason rather than crashing on the missing file."""
    missing = sorted(script for _name, script, _solver in harness.GATES
                     if not (ROOT / script).is_file()
                     and Path(script).name not in harness.PRIVATE_ONLY)

    assert missing == [], "GATES names %d file(s) that are not there: %s" % (
        len(missing), missing)


def test_private_only_names_are_registered_or_exempt():
    """A typo in PRIVATE_ONLY would quietly turn a real registry rot back into
    a mid-run crash: the misspelt entry guards nothing, and the gate it meant
    to guard fails as an ordinary missing file."""
    known = set(_registered()) | set(EXEMPT)
    ghosts = sorted(set(harness.PRIVATE_ONLY) - known)

    assert ghosts == [], (
        "PRIVATE_ONLY lists %s, which is neither a GATES script nor EXEMPT"
        % ghosts)


def test_a_missing_private_gate_reports_not_distributed_with_its_reason(tmp_path, monkeypatch):
    """Both directions, because the else branch is the trap: an absent file
    that is NOT private-only has to fail, not skip."""
    monkeypatch.setattr(harness, "ROOT", tmp_path)

    private = harness._run("hallucination_pack",
                           "scripts/run_hallucination_pack_check.py",
                           "abaqus", timeout=1)
    assert private["result"] == "NOT_DISTRIBUTED"
    assert "course/" in private["reason"]
    assert private["result"] in harness.PASSING

    rotted = harness._run("crack", "scripts/run_crack_check.py", "abaqus",
                          timeout=1)
    assert rotted["result"] == "FAIL"


def test_gate_names_are_unique():
    """`--only <name>` picks by name; two gates sharing one would make the
    second unreachable, and the summary would show one line for two runs."""
    names = [name for name, _script, _solver in harness.GATES]

    duplicates = sorted({n for n in names if names.count(n) > 1})
    assert duplicates == [], duplicates


def test_no_exemption_is_a_ghost():
    """An exemption for a script that no longer exists reads as coverage.

    A PRIVATE_ONLY exemption is allowed to be absent -- that is the public
    tree, where the script is withheld, not deleted."""
    ghosts = sorted(set(EXEMPT) - _gate_scripts() - set(harness.PRIVATE_ONLY))

    assert ghosts == [], "EXEMPT lists %s, which is not in scripts/" % ghosts


def test_a_verdict_is_read_even_with_text_printed_after_it():
    """run_workbench_browser_check.py prints `evidence -> <path>` after its
    JSON. The reader used to require the payload to run to the last byte, so
    that gate was reported as "printed no JSON object" -- a FAIL -- on a run
    whose payload said `"overall": "PASS"`."""
    stdout = ('  ok  something\n'
              '{"overall": "PASS", "items": []}\n'
              '\nevidence -> D:\\artifacts\\browser_check.json\n')

    assert harness._verdict(harness._payload(stdout)) == "PASS"


def test_the_verdict_is_the_last_payload_not_the_first():
    """Several gates print an interim payload mid-run (the coherence gate
    dumps its token census) and the verdict at the end."""
    stdout = ('{"shared_tokens_checked": 12}\n'
              'RESULT: FAIL\n'
              '{"result": "FAIL", "failures": ["a"]}\n')

    assert harness._verdict(harness._payload(stdout)) == "FAIL"


def test_a_gate_that_prints_no_json_is_not_silently_passed():
    assert harness._payload("RESULT: PASS\n") is None


def test_every_gate_prints_a_verdict_the_harness_can_read():
    """The harness reads one JSON object with `result` or `overall`. A gate
    that prints only "RESULT: PASS" is read as UNREADABLE -- which is how
    three of the nine gates registered on 2026-08-09 would have arrived, all
    of them green, all of them counted as broken.

    Checked by parsing rather than by running: these gates start servers and
    browsers, and this suite stays hermetic.
    """
    silent = []
    for _name, script, _solver in harness.GATES:
        if (not (ROOT / script).is_file()
                and Path(script).name in harness.PRIVATE_ONLY):
            continue
        tree = ast.parse((ROOT / script).read_text(encoding="utf-8"))
        keys = {node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        if not ({"result", "overall"} & keys):
            silent.append(script)

    assert silent == [], (
        "%d gate(s) never name `result` or `overall`, so run_all_real_checks "
        "reads them as UNREADABLE: %s" % (len(silent), silent))
