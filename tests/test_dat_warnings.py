"""The .dat scanner: the layer that answers "is this the model the spec asked for".

`monitor_job` answers "did it finish" and the .sta answers "did it converge".
Neither answers this one, and Abaqus does not raise when the answer is no. The
fixtures below are trimmed from a real Abaqus 2021 .dat, wrapping and all,
because the wrapping is where two of the bugs were.
"""
from __future__ import annotations

import pytest

from runner.dat_warnings import classify, limitation_lines, parse_dat_warnings

# Copied from cases/bearing_block's own .dat, including the line breaks: Abaqus
# wraps a warning across as many indented lines as it needs, and the half that
# says what happened is usually not on the first one.
UNTIED = """\
  *tie, name=ASSEMBLY_BORETIE, positiontolerance=0.05, adjust=NO

 ***WARNING: SLAVE NODE 830 INSTANCE BUSHING WILL NOT BE TIED TO THE MASTER
             SURFACE ASSEMBLY_BORETIE_MAIN. THE DISTANCE FROM THE MASTER
             SURFACE IS GREATER THAN THE POSITION TOLERANCE VALUE.

 ***WARNING: SLAVE NODE 911 INSTANCE BUSHING WILL NOT BE TIED TO THE MASTER
             SURFACE ASSEMBLY_BORETIE_MAIN. THE DISTANCE FROM THE MASTER
             SURFACE IS GREATER THAN THE POSITION TOLERANCE VALUE.

 ***NOTE: THE ABOVE WARNING MESSAGE IS BEING SUPPRESSED DUE TO EXCESSIVE
          REPORTING.
  *surfaceinteraction, name=CAPSEAT_PROP
"""

MISS_MASTER = """\
 ***WARNING: 74 nodes are either missing intersection with their respective
             master surface or are outside the adjust zone. The nodes have been
             identified in node set WarnNodeMissMasterIntersect.
  *output, field
"""

CLEAN = """\
  *step, name=SelfWeight, nlgeom=NO
  *static

 THE ANALYSIS HAS COMPLETED SUCCESSFULLY
"""


def write(tmp_path, text, name="Job.dat"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# --- the two bugs the wrapping caused --------------------------------------

def test_a_wrapped_warning_is_read_whole(tmp_path):
    """Reading only the first line matches "SLAVE NODE 830 INSTANCE BUSHING"
    and misses "WILL NOT BE TIED", which is the entire content."""
    report = parse_dat_warnings(write(tmp_path, UNTIED))
    assert [f["id"] for f in report["findings"]] == ["tie_node_outside_tolerance"]
    assert report["findings"][0]["count"] == 2


def test_the_suppression_note_is_found_although_it_wraps_too(tmp_path):
    """"SUPPRESSED DUE TO EXCESSIVE" ends one line and "REPORTING" starts the
    next, so a search of the raw text finds nothing -- and the run then reports
    an exact count for something Abaqus stopped counting."""
    report = parse_dat_warnings(write(tmp_path, UNTIED))
    assert report["suppressed"] is True
    assert report["findings"][0]["count_is_lower_bound"] is True


# --- counting ---------------------------------------------------------------

def test_a_warning_that_states_its_own_total_is_counted_by_that_total(tmp_path):
    """One block, 74 nodes. Counting blocks understates it by 73."""
    report = parse_dat_warnings(write(tmp_path, MISS_MASTER))
    finding = report["findings"][0]
    assert finding["id"] == "nodes_miss_master_intersection"
    assert finding["count"] == 1
    assert finding["items"] == 74
    assert report["integrity_count"] == 74


def test_a_stated_total_is_not_downgraded_to_a_lower_bound(tmp_path):
    """Suppression stops the per-node listing. A warning that states its count
    states it once, in full, so it is not affected."""
    report = parse_dat_warnings(write(tmp_path, UNTIED + MISS_MASTER))
    by_id = {f["id"]: f for f in report["findings"]}
    assert by_id["tie_node_outside_tolerance"]["count_is_lower_bound"] is True
    assert by_id["nodes_miss_master_intersection"]["count_is_lower_bound"] is False


def test_repeats_of_one_problem_group_into_one_finding(tmp_path):
    report = parse_dat_warnings(write(tmp_path, UNTIED))
    assert len(report["findings"]) == 1


# --- classification ---------------------------------------------------------

def test_integrity_findings_sort_ahead_of_the_rest(tmp_path):
    text = MISS_MASTER + """
 ***WARNING: 11 elements are distorted. Either the isoparametric angles are out
             of the suggested limits or the triangular or tetrahedral quality
             measure is bad. The elements have been identified in element set
             WarnElemDistorted.
"""
    report = parse_dat_warnings(write(tmp_path, text))
    assert [f["integrity"] for f in report["findings"]] == [True, False]
    # A mesh-quality warning is real but it does not mean the model differs
    # from the spec, so it must not block the run.
    assert report["integrity_count"] == 74


def test_an_unrecognised_warning_is_reported_not_dropped(tmp_path):
    """"We did not recognise this" and "there was no warning" must never look
    the same."""
    text = " ***WARNING: SOMETHING NOBODY HAS SEEN BEFORE HAPPENED HERE.\n"
    report = parse_dat_warnings(write(tmp_path, text))
    assert report["findings"] == []
    assert len(report["unrecognised"]) == 1
    assert "NOBODY HAS SEEN" in report["unrecognised"][0]["example"]


def test_every_signature_carries_what_why_and_fix():
    from runner.dat_warnings import SIGNATURES
    for signature in SIGNATURES:
        for key in ("id", "match", "integrity", "what", "why", "fix"):
            assert signature.get(key) not in (None, ""), (signature["id"], key)
        assert signature["match"] == signature["match"].upper(), signature["id"]


@pytest.mark.parametrize("message,expected", [
    ("SLAVE NODE 1 INSTANCE B WILL NOT BE TIED TO THE MASTER SURFACE X",
     "tie_node_outside_tolerance"),
    ("74 nodes are either missing intersection with their respective master",
     "nodes_miss_master_intersection"),
    ("ZERO PIVOT WHEN PROCESSING D.O.F. 1 OF NODE 5", "zero_pivot"),
    ("nothing in particular", None),
])
def test_classify(message, expected):
    signature = classify(message)
    assert (signature["id"] if signature else None) == expected


# --- absence ----------------------------------------------------------------

def test_a_clean_dat_reports_nothing(tmp_path):
    report = parse_dat_warnings(write(tmp_path, CLEAN))
    assert report["read"] is True
    assert report["findings"] == []
    assert report["integrity_count"] == 0
    assert limitation_lines(report) == []


def test_a_missing_dat_is_not_an_absence_of_warnings(tmp_path):
    """The caller decides whether that is expected (a build that never reached
    the solver) or a problem (a solve that claims to have finished). It must
    not be able to mistake it for a clean file."""
    report = parse_dat_warnings(tmp_path / "nope.dat")
    assert report["read"] is False
    assert report["findings"] == []


# --- what reaches the user --------------------------------------------------

def test_the_limitation_line_says_it_is_a_lower_bound(tmp_path):
    report = parse_dat_warnings(write(tmp_path, UNTIED))
    line = limitation_lines(report)[0]
    assert "至少" in line
    assert "下限" in line
    assert "position tolerance" in line


def test_only_integrity_findings_become_limitations(tmp_path):
    text = """
 ***WARNING: 11 elements are distorted. Either the isoparametric angles are out
             of the suggested limits.
"""
    report = parse_dat_warnings(write(tmp_path, text))
    assert report["findings"][0]["id"] == "distorted_elements"
    assert limitation_lines(report) == []
