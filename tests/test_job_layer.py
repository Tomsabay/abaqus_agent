"""The `job:` block: launcher options a deck cannot carry.

Double precision, a user subroutine, what to restart from, GPUs -- none of
these are keywords, they are arguments to the `abaqus` command, and a spec had
nowhere to put them.

It is a PASSTHROUGH rather than a list of supported flags, and everything that
makes a passthrough safe here was measured on Abaqus 2021 rather than assumed
(artifacts/probe_job):

    bogusoption=1    "Abaqus Error: ..." plus the launcher's own list of the 36
                     options it accepts, then no .dat and no .odb
    double=banana    "The specified value ... is not supported by Abaqus"
    user=nosuch.f    "The following file(s) could not be located"
    oldjob=neverran  the same, about neverran.odb, when the deck really does
                     carry *RESTART, READ

ALL FOUR EXIT 0. So the option name is never judged on this side -- Abaqus
judges it -- and what this side must not do is trust the exit code.

The launcher's printed list is deliberately not used as a validator either: it
omits `gpus`, and `gpus=1` runs (6 licence tokens instead of 5 and 3m45s
instead of 11s, same one-element deck). A validator built from that list would
refuse an option that works.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runner.submit_job import (  # noqa: E402
    _RESERVED_JOB_OPTIONS,
    _build_cmd,
    _job_option_args,
    _launcher_refused,
)
from tools.errors import AbaqusAgentError  # noqa: E402


def _refuse(options, workdir) -> str:
    with pytest.raises(AbaqusAgentError) as excinfo:
        _job_option_args(options, workdir)
    return str(excinfo.value)


# --- the passthrough ------------------------------------------------------

def test_options_become_launcher_arguments(tmp_path):
    assert _job_option_args({"double": "both", "gpus": 1}, tmp_path) == [
        "double=both", "gpus=1"]


def test_nothing_is_passed_when_there_is_no_block(tmp_path):
    assert _job_option_args(None, tmp_path) == []
    assert _job_option_args({}, tmp_path) == []


def test_an_option_this_file_has_never_heard_of_still_goes_through(tmp_path):
    """The point of a passthrough. `scratch` and `parallel` are real launcher
    options nobody here wrote a branch for, and a spec needing one should not
    have to wait for this file to learn about it."""
    assert _job_option_args({"scratch": "D:/tmp"}, tmp_path) == [
        "scratch=D:/tmp"]


def test_the_arguments_land_between_the_deck_and_the_wait(tmp_path):
    cmd = _build_cmd(job_name="J", inp_path=tmp_path / "J.inp", cpus=1,
                     mp_mode="threads", memory="90%", background=False,
                     interactive=True, job_option_args=["double=both"])
    assert "double=both" in cmd
    assert cmd.index("double=both") < cmd.index("interactive")
    assert cmd[-1] == "interactive"


# --- what it refuses ------------------------------------------------------

@pytest.mark.parametrize("name", sorted(_RESERVED_JOB_OPTIONS))
def test_an_option_the_pipeline_already_sets_is_refused(name, tmp_path):
    """Not a capability limit -- a collision. The pipeline already writes each
    of these onto the command line, so setting one here passes it twice and
    the launcher takes one of them without saying which."""
    message = _refuse({name: "x"}, tmp_path)
    assert name in message
    assert "twice" in message


def test_the_refusal_says_where_the_setting_really_lives(tmp_path):
    assert "runner.json" in _refuse({"cpus": 8}, tmp_path)


def test_a_block_that_is_not_a_mapping_is_refused(tmp_path):
    assert "must be a mapping" in _refuse("double=both", tmp_path)


@pytest.mark.parametrize("value", [None, True, False, ""])
def test_a_value_that_cannot_be_a_launcher_argument_is_refused(value,
                                                               tmp_path):
    """`job: {double: }` is None and `job: {double: yes}` is True after YAML
    gets hold of it; neither can become `name=value`."""
    assert _refuse({"double": value}, tmp_path)


# --- the files, checked before the licence --------------------------------

def test_a_missing_subroutine_is_refused_here_not_by_abaqus(tmp_path):
    message = _refuse({"user": "nosuch.f"}, tmp_path)
    assert "nosuch.f" in message
    assert "after checking out a licence" in message


def test_a_subroutine_that_exists_passes(tmp_path):
    (tmp_path / "umat.f").write_text("      subroutine umat\n      end\n")
    assert _job_option_args({"user": "umat.f"}, tmp_path) == ["user=umat.f"]


def test_a_restart_source_is_checked_as_an_odb(tmp_path):
    """`oldjob=` names a JOB, and what has to be on disk is its .odb.

    Measured: with a deck carrying *RESTART, READ, `oldjob=neverran` answers
    "The following file(s) could not be located: neverran.odb" -- so the
    suffix is added here rather than making the user write it.
    """
    assert "neverran.odb" in _refuse({"oldjob": "neverran"}, tmp_path)
    (tmp_path / "prev.odb").write_bytes(b"not really an odb")
    assert _job_option_args({"oldjob": "prev"}, tmp_path) == ["oldjob=prev"]


def test_an_absolute_path_is_not_re_rooted(tmp_path):
    source = tmp_path / "sub" / "umat.f"
    source.parent.mkdir()
    source.write_text("      end\n")
    assert _job_option_args({"user": str(source)}, tmp_path) == [
        "user=%s" % source]


# --- reading the refusal the exit code cannot carry ------------------------

def test_the_launcher_refusal_is_recognised():
    stdout = ('Abaqus Error: The specified value for the following command '
              'line option is not supported by Abaqus: double=banana\n'
              'Abaqus/Analysis exited with error(s).')
    found = _launcher_refused(stdout, "")
    assert "double=banana" in found


def test_a_normal_run_is_not_mistaken_for_a_refusal():
    assert _launcher_refused("Abaqus JOB d COMPLETED", "") == ""


def test_the_refusal_is_not_classified_by_keyword_scan():
    """The launcher prints its own option list when it rejects one, and that
    list contains the word "memory" -- so running it through _classify_error
    came back MEMORY_ERROR for a mistyped option name, sending the reader to
    look at RAM. Measured, then fixed to a fixed code."""
    source = (ROOT / "runner" / "submit_job.py").read_text(encoding="utf-8")
    after = source.split("refusal = _launcher_refused(", 1)[1]
    block = after.split("meta[\"status\"]", 1)[0]
    assert "ErrorCode.SPEC_INVALID" in block
    assert "_classify_error" not in block.split("raise", 1)[0].replace(
        "NOT _classify_error", "")
