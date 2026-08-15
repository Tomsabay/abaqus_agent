"""The one command that reads every gate's verdict.

Hermetic — nothing here starts a solver. What it pins is the contract reader,
because the bug it replaces was entirely a reading bug: `json.loads(stdout)` on
a gate that prints its item list before its JSON judged that gate FAIL, and
nine of the seventeen gates print their item list first.

Two output contracts exist in the tree and both have to be read:

    {"result": "PASS"}                the five 2026-07 scenario gates
    {"overall": "pass", "items": []}  everything written since
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _module():
    spec = importlib.util.spec_from_file_location(
        "run_all_real_checks", ROOT / "scripts" / "run_all_real_checks.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def rarc():
    return _module()


# --- reading a verdict -----------------------------------------------------

def test_the_2026_07_contract_is_still_read(rarc):
    assert rarc._verdict({"result": "PASS"}) == "PASS"
    assert rarc._verdict({"result": "FAIL"}) == "FAIL"


def test_the_newer_contract_is_read_and_upper_cased(rarc):
    assert rarc._verdict({"overall": "pass"}) == "PASS"
    assert rarc._verdict({"overall": "skipped"}) == "SKIPPED"


def test_a_payload_with_neither_key_is_not_silently_a_pass(rarc):
    assert rarc._verdict({"items": []}) == "UNREADABLE"


def test_json_is_found_after_the_human_summary(rarc):
    """The bug this file exists for. Nine gates print their items first, and
    feeding the whole of stdout to json.loads judged every one of them FAIL."""
    stdout = ("  generic_mesh_tets_a_part_with_no_hex_route       pass\n"
              "  generic_mesh_refuses_a_silent_zero               pass\n"
              '{"overall": "pass", "items": [{"status": "pass"}]}\n')
    payload = rarc._payload(stdout)
    assert payload is not None
    assert rarc._verdict(payload) == "PASS"


def test_a_brace_in_the_human_summary_does_not_stop_the_search(rarc):
    """`{` appears in refusal messages the gates quote back."""
    stdout = ('  refused: {select: "..."} carries a stray key\n'
              '{"overall": "pass"}\n')
    assert rarc._verdict(rarc._payload(stdout)) == "PASS"


def test_no_json_at_all_reads_as_nothing(rarc):
    assert rarc._payload("Traceback (most recent call last):") is None


# --- what gets summarised --------------------------------------------------

def test_item_counts_are_rolled_up(rarc):
    got = rarc._interesting({"items": [{"status": "pass"}, {"status": "pass"},
                                       {"status": "fail"},
                                       {"status": "skipped"}]})
    assert got["items"] == {"total": 4, "pass": 2, "fail": 1, "skipped": 1}


def test_a_scenario_gates_number_survives(rarc):
    got = rarc._interesting({"result": "PASS", "kt_measured": 3.02})
    assert got["kt_measured"] == 3.02


# --- the gate list ---------------------------------------------------------

def test_every_listed_gate_exists(rarc):
    missing = [script for _n, script, _s in rarc.GATES
               if not (ROOT / script).is_file()
               and Path(script).name not in rarc.PRIVATE_ONLY]
    assert not missing, missing


def test_the_generic_layer_gates_are_in_the_list(rarc):
    """They were not, which is the other half of the bug: the summary ran five
    2026-07 scripts and reported PASS while the engine work of 2026-08 went
    unchecked by the one command that claims to check everything."""
    names = {name for name, _s, _solver in rarc.GATES}
    for name in ("generic_part", "generic_mesh", "generic_load",
                 "generic_interaction", "generic_connector", "mesh_quality",
                 "dropped_input", "part_grammar", "assembly"):
        assert name in names, name


def test_gate_names_are_unique(rarc):
    names = [name for name, _s, _solver in rarc.GATES]
    assert len(names) == len(set(names))


# --- the overall verdict ---------------------------------------------------

def _summary(rarc, verdicts, monkeypatch, tmp_path):
    calls = iter(verdicts)

    def fake_run(name, script, solver, timeout):
        return {"name": name, "script": script, "solver": solver,
                "seconds": 0.0, "result": next(calls)}

    monkeypatch.setattr(rarc, "_run", fake_run)
    monkeypatch.setattr(rarc, "ROOT", tmp_path)
    only = [name for name, _s, _solver in rarc.GATES][:len(verdicts)]
    argv = []
    for name in only:                    # append action: one flag per value
        argv += ["--only", name]
    code = rarc.main(argv)
    written = json.loads((tmp_path / "artifacts"
                          / "real_check_gate_summary.json").read_text(
                              encoding="utf-8"))
    return code, written


def test_all_passing_exits_zero(rarc, monkeypatch, tmp_path):
    code, summary = _summary(rarc, ["PASS", "PASS"], monkeypatch, tmp_path)
    assert code == 0 and summary["overall"] == "PASS"


def test_a_machine_with_no_solver_is_skipped_not_failed(rarc, monkeypatch,
                                                        tmp_path):
    """Every gate says "skipped" and exits 0 when it cannot find Abaqus. The
    honest overall verdict is SKIPPED, and it must not be exit 1 -- a fresh
    checkout would look broken."""
    code, summary = _summary(rarc, ["SKIPPED", "SKIPPED"], monkeypatch,
                             tmp_path)
    assert code == 0 and summary["overall"] == "SKIPPED"


def test_one_failure_fails_the_run(rarc, monkeypatch, tmp_path):
    code, summary = _summary(rarc, ["PASS", "FAIL"], monkeypatch, tmp_path)
    assert code == 1 and summary["overall"] == "FAIL"
    assert summary["counts"] == {"total": 2, "pass": 1, "partial": 0,
                                 "skipped": 0, "not_distributed": 0, "fail": 1}


def test_a_withheld_gate_does_not_fail_a_public_run(rarc, monkeypatch,
                                                    tmp_path):
    """The public tree runs a registry that names three course-line gates it
    does not ship. Their NOT_DISTRIBUTED must not turn the whole run red --
    and it must be counted under its own name, never folded into pass."""
    code, summary = _summary(rarc, ["PASS", "NOT_DISTRIBUTED"], monkeypatch,
                             tmp_path)
    assert code == 0 and summary["overall"] == "PASS"
    assert summary["counts"]["not_distributed"] == 1
    assert summary["counts"]["pass"] == 1


def test_an_unreadable_gate_fails_the_run(rarc, monkeypatch, tmp_path):
    code, summary = _summary(rarc, ["PASS", "UNREADABLE"], monkeypatch,
                             tmp_path)
    assert code == 1 and summary["overall"] == "FAIL"


def test_an_unknown_gate_name_is_refused(rarc):
    assert rarc.main(["--only", "no_such_gate"]) == 2


# --- PARTIAL was on neither list -------------------------------------------
#
# Eight gates build their overall as `elif "skipped" in statuses: "partial"`
# -- no item failed, some were skipped. PARTIAL was not in PASSING, so the
# harness counted the gate a failure and exited 1 while the gate itself exited
# 0 saying it was fine. Two sources of truth, no way to tell which one meant it.

def test_a_partial_gate_does_not_fail_the_run(rarc):
    assert "PARTIAL" in rarc.PASSING


def test_a_partial_gate_is_not_reported_as_a_full_pass(rarc, monkeypatch,
                                                       tmp_path):
    """The other half of the fix. Folding PARTIAL into PASS would trade a
    false red for a false green, which is the worse of the two."""
    code, summary = _summary(rarc, ["PASS", "PARTIAL"], monkeypatch, tmp_path)
    assert code == 0
    assert summary["overall"] == "PARTIAL"
    assert summary["counts"] == {"total": 2, "pass": 1, "partial": 1,
                                 "skipped": 0, "not_distributed": 0, "fail": 0}


def test_a_real_failure_still_outranks_a_partial(rarc, monkeypatch, tmp_path):
    code, summary = _summary(rarc, ["PARTIAL", "FAIL"], monkeypatch, tmp_path)
    assert code == 1 and summary["overall"] == "FAIL"


def test_the_partial_gates_really_do_emit_that_word(rarc):
    """The verdict is only worth handling if something produces it: if no gate
    can say `partial`, the branch above is dead code and should go, not linger.

    Non-empty, not a count: the original `>= 8` was a census snapshot, and it
    rotted the day the public tree shipped one fewer emitter than the private
    one -- the eighth lives in a withheld course-line gate."""
    import re
    emitters = [
        p.name for p in (ROOT / "scripts").glob("run_*check*.py")
        if re.search(r'overall\s*=\s*"partial"', p.read_text(encoding="utf-8"))
    ]
    assert emitters, "no gate can produce a `partial` overall any more"
