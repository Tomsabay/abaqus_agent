"""A KPI the spec asked for and never got back has to be visible. (#73(b))

THE FAILURE THIS CLOSES. `_stage_extract` wrote `result["kpis"] = result.get(
"kpis", {})` and put extraction errors in `stages.extract_kpis.errors`. Nothing
compared the two collections, so a spec asking for three KPIs and receiving two
produced a run that reported COMPLETED, a report whose cover printed `KPIs: 2`,
and a workbench grid with two tiles. Every one of those is true and none of them
says a third KPI was requested. #73(a) made a surface location refuse instead of
returning a wrong number -- and the refusal landed in exactly this blind spot.

WHAT WAS DECIDED, AND WHAT WAS NOT. The user's call on 2026-08-07 was
"显著标注但不改判定": mark it prominently, leave the verdict alone. So these
tests assert the SHORTFALL IS SHOWN and deliberately do NOT assert that the run
fails. Turning a dropped KPI into a FAILED run would re-grade every shipped case
and every frozen baseline under `cases/*/runs/`, which is a separate decision
from making the shortfall visible.

WHY THE DIFF AND NOT THE ERROR LIST. `missing_kpis` compares requested names
against delivered ones instead of reading `errors`. The two questions differ:
the error list only knows about failures somebody wrote a message for. A KPI
that vanishes for a reason nobody anticipated still shows up in a diff.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.orchestrator import AbaqusOrchestrator  # noqa: E402
from odb_lens import missing_kpis  # noqa: E402
from reporting import templates  # noqa: E402
from tests.frontend_sources import workbench_text  # noqa: E402

# --- the diff itself -------------------------------------------------------

def test_a_delivered_kpi_is_not_missing():
    requested = [{"name": "U_TIP", "type": "nodal_displacement"}]
    assert missing_kpis(requested, {"U_TIP": 1.23}) == []


def test_a_dropped_kpi_is_reported_with_its_type():
    requested = [{"name": "U_TIP", "type": "nodal_displacement"},
                 {"name": "SCF", "type": "derived_stress_concentration"}]
    rows = missing_kpis(requested, {"U_TIP": 1.23})
    assert [r["name"] for r in rows] == ["SCF"]
    assert rows[0]["type"] == "derived_stress_concentration"


def test_a_zero_valued_kpi_counts_as_delivered():
    """0.0 is a result. Membership, not truthiness -- a displacement of exactly
    zero at a fixed node is the most ordinary number in this project."""
    assert missing_kpis([{"name": "U", "type": "field_max"}], {"U": 0.0}) == []


def test_the_matching_error_is_attached_to_the_row():
    requested = [{"name": "SCF", "type": "derived_stress_concentration"}]
    errors = ["KPI SCF: location 'TOP' is a SURFACE, and a KPI location has to "
              "be a set."]
    rows = missing_kpis(requested, {}, errors)
    assert "SURFACE" in rows[0]["reason"]


def test_an_error_naming_no_kpi_is_not_guessed_onto_a_row():
    """A precise-looking sentence about the wrong KPI is worse than none.

    The unattributed error is not lost -- it is still in
    `stages.extract_kpis.errors`, which the report and the diagnosis panel both
    read.
    """
    rows = missing_kpis([{"name": "SCF", "type": "x"}], {},
                        ["odb could not be opened"])
    assert rows[0]["reason"] == ""


def test_a_kpi_missing_for_an_unanticipated_reason_is_still_caught():
    """The whole reason this is a diff. No error mentions it at all."""
    rows = missing_kpis([{"name": "J_TIP", "type": "contour_integral_j"}], {}, [])
    assert [r["name"] for r in rows] == ["J_TIP"]


# --- the orchestrator wiring ----------------------------------------------

def _bare_orchestrator(result: dict) -> AbaqusOrchestrator:
    """An orchestrator with no Abaqus behind it.

    `__init__` builds a workdir and reads a spec; none of that is needed to
    test what `_record_missing_kpis` does to `self.result`.
    """
    orch = AbaqusOrchestrator.__new__(AbaqusOrchestrator)
    orch.result = result
    return orch


def test_the_shortfall_reaches_the_top_level_of_the_result():
    orch = _bare_orchestrator({"kpis": {"U_TIP": 1.0}})
    orch._record_missing_kpis(
        [{"name": "U_TIP", "type": "nodal_displacement"},
         {"name": "SCF", "type": "derived_stress_concentration"}],
        {"kpis": {"U_TIP": 1.0}, "errors": []})

    assert [m["name"] for m in orch.result["kpis_missing"]] == ["SCF"]


def test_the_shortfall_also_rides_the_limitations_channel():
    """The channel the UI already polls and cannot render as a clean run."""
    orch = _bare_orchestrator({"kpis": {}})
    orch._record_missing_kpis([{"name": "SCF", "type": "t"}],
                              {"kpis": {}, "errors": []})

    entry = orch.result["limitations"][0]
    assert entry["feature"] == "KPI"
    assert entry["value"] == "SCF"
    assert entry["kind"] == "kpi_not_extracted"
    assert entry["reason"]


def test_recording_does_not_erase_limitations_already_there():
    """CalculiX puts its capability caveats in this list before extraction runs.

    `_record_caveats` ASSIGNS to `result["limitations"]`; if this method did the
    same, every caveat about what the fallback solver could not do would be
    replaced by a KPI note.
    """
    orch = _bare_orchestrator({
        "kpis": {},
        "limitations": [{"feature": "element", "value": "C3D8I",
                         "reason": "CalculiX 没有这个单元"}],
    })
    orch._record_missing_kpis([{"name": "SCF", "type": "t"}],
                              {"kpis": {}, "errors": []})

    features = [ln["feature"] for ln in orch.result["limitations"]]
    assert features == ["element", "KPI"]


def test_a_complete_run_records_an_empty_list_not_a_missing_key():
    """Absent and empty must not be the same thing downstream.

    A reader that does `result.get("kpis_missing", [])` cannot tell a run that
    dropped nothing from one produced before this existed. Writing the empty
    list makes "nothing was dropped" an answer this pipeline gave.
    """
    orch = _bare_orchestrator({"kpis": {"U_TIP": 1.0}})
    orch._record_missing_kpis([{"name": "U_TIP", "type": "nodal_displacement"}],
                              {"kpis": {"U_TIP": 1.0}, "errors": []})

    assert "kpis_missing" in orch.result
    assert orch.result["kpis_missing"] == []
    assert orch.result.get("limitations", []) == []


def test_the_calculix_orchestrator_inherits_the_same_recording():
    """Both backends drop KPIs the same way, so both must report it the same."""
    from agent.ccx_orchestrator import CalculiXOrchestrator

    assert CalculiXOrchestrator._record_missing_kpis is \
        AbaqusOrchestrator._record_missing_kpis
    source = (ROOT / "agent" / "ccx_orchestrator.py").read_text(encoding="utf-8")
    assert "self._record_missing_kpis(kpi_spec, result)" in source


def test_both_stage_extract_methods_call_it():
    """The guard against the wiring being removed while the helper survives."""
    for rel in ("agent/orchestrator.py", "agent/ccx_orchestrator.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        body = text.split("def _stage_extract", 1)[1].split("\n    def ", 1)[0]
        assert "_record_missing_kpis" in body, rel


# --- the report ------------------------------------------------------------

def _report(kpis: dict, missing: list) -> dict:
    return {
        "summary": {"run_id": "r1", "status": "COMPLETED", "model_name": "M"},
        "kpis": kpis,
        "kpis_missing": missing,
        "regression": {},
        "contracts": {},
        "artifacts": {},
    }


def test_the_cover_metric_shows_the_denominator():
    value, css = templates._kpi_metric_value(
        _report({"A": 1.0, "B": 2.0}, [{"name": "C", "type": "t"}]))
    assert value == "2 of 3"
    assert css == "warn"


def test_the_cover_metric_is_a_bare_count_when_nothing_is_missing():
    """The unchanged reading. A denominator on every run would train it away."""
    assert templates._kpi_metric_value(_report({"A": 1.0}, [])) == ("1", "")


def test_the_html_kpi_table_carries_a_not_extracted_row():
    html = templates.render_run_report_html(
        _report({"A": 1.0}, [{"name": "SCF", "type": "t",
                              "reason": "location 'TOP' is a SURFACE"}]))
    assert "NOT EXTRACTED" in html
    assert "SCF" in html
    assert "SURFACE" in html
    assert "2 of 3" not in html          # 1 delivered + 1 missing
    assert "1 of 2" in html


def test_every_markdown_template_carries_the_row():
    """All three go through `_append_kpi_rows`; prove it rather than assume it."""
    report = _report({"A": 1.0}, [{"name": "SCF", "type": "t", "reason": ""}])
    for template in ("standard", "client_summary", "engineering_delivery"):
        text = templates.render_run_report_markdown(report, template=template)
        assert "NOT EXTRACTED" in text, template
        assert "| SCF |" in text, template


def test_the_client_summary_count_line_shows_the_shortfall():
    text = templates.render_run_report_markdown(
        _report({"A": 1.0}, [{"name": "SCF", "type": "t"}]),
        template="client_summary")
    assert "KPI count: `1 of 2`" in text


def test_a_reason_containing_a_pipe_cannot_break_the_markdown_table():
    text = templates.render_run_report_markdown(
        _report({}, [{"name": "SCF", "type": "t",
                      "reason": "sets are A|B|C, pick one"}]))
    row = [ln for ln in text.splitlines() if ln.startswith("| SCF |")][0]
    assert row.count("|") == 4          # the three cell separators plus the end


def test_a_bare_string_entry_from_an_older_run_still_renders():
    """Report code reads archived result.json files, and those outlive a shape."""
    html = templates.render_run_report_html(_report({"A": 1.0}, ["SCF"]))
    assert "SCF" in html and "NOT EXTRACTED" in html


# --- the plumbing between them --------------------------------------------

def test_the_key_survives_every_hop_to_the_report():
    """result.json -> load_offline_run -> build_offline_run_report -> template.

    Each hop copies an explicit list of keys. A field added at one end and not
    at the other is invisible in exactly the way this whole task is about.
    """
    for rel, marker in (
        ("reporting/export.py", '"kpis_missing": run.get("kpis_missing", [])'),
        ("reporting/export.py", '"kpis_missing": result.get("kpis_missing", [])'),
        ("core/pipeline.py", '"kpis_missing": run.get("kpis_missing", [])'),
        ("core/pipeline.py", 'run["kpis_missing"] = result.get("kpis_missing", [])'),
        ("workbench/routes.py", '"kpis_missing"'),
    ):
        assert marker in (ROOT / rel).read_text(encoding="utf-8"), (rel, marker)


def test_the_pipeline_snapshot_is_json_serializable_with_the_new_key():
    import time

    from core import pipeline

    run = {"run_id": "r1", "started_at": time.time(),
           "kpis_missing": [{"name": "SCF", "type": "t", "reason": "x"}]}
    snapshot = pipeline._run_snapshot(run) if hasattr(pipeline, "_run_snapshot") \
        else None
    if snapshot is None:                       # renamed helper: find it by shape
        import inspect
        for _name, fn in inspect.getmembers(pipeline, inspect.isfunction):
            src = inspect.getsource(fn)
            if '"progress_pct": run.get("progress_pct", 0),' in src:
                snapshot = fn(run)
                break
    assert snapshot is not None, "the run snapshot builder moved"
    assert snapshot["kpis_missing"][0]["name"] == "SCF"
    json.dumps(snapshot)


# --- the workbench page ----------------------------------------------------

def test_the_grid_renders_a_tile_for_a_missing_kpi():
    source = workbench_text()
    for marker in (
        "const kpisMissing = (run && run.kpis_missing) || rec.kpis_missing || [];",
        "if (kpiNames.length || kpisMissing.length) {",
        "kpisMissing.forEach((m, i) => {",
        'class="kpi-card kpi-missing"',
        ".kpi-card.kpi-missing::before",
        "t('kpi.missing.count'",
    ):
        assert marker in source, marker


def test_limitation_line_renders_strings():
    """`runner.dat_warnings.limitation_lines` has always written plain strings.

    `limitationText` read `l.reason`, which on a string is undefined, so every
    one of those lines rendered as an EMPTY card and `limitationLine` returned
    " = ：". Measured in node before the fix. The .dat integrity findings --
    "85 tie nodes were silently left unconstrained" -- were going into a
    channel that displayed nothing.
    """
    source = workbench_text()
    text_fn = source.split("function limitationText(l) {", 1)[1].split("\n}", 1)[0]
    line_fn = source.split("function limitationLine(l) {", 1)[1].split("\n}", 1)[0]
    assert "typeof l === 'string'" in text_fn
    assert "typeof l === 'string'" in line_fn


def test_the_new_catalogue_keys_exist_in_both_languages():
    """test_frontend_i18n_catalogue covers this generally; named here so a
    failure points at this feature instead of at "some key is missing"."""
    source = workbench_text()
    for key in ("kpi.missing.value", "kpi.missing.why", "kpi.missing.count"):
        assert source.count('"%s":' % key) == 2, key
