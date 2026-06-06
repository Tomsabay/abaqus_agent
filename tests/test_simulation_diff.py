from simdiff.kpi_diff import diff_kpis, render_markdown
from simdiff.service import collect_kpi_diff


def test_diff_kpis_passes_values_within_tolerance():
    report = diff_kpis(
        {"U_tip": -2.0, "mode": "linear"},
        {"U_tip": -2.04, "mode": "linear"},
        {"U_tip": {"rtol": 0.05}},
    )

    assert report["status"] == "PASS"
    assert report["passed"]
    assert report["unchanged_count"] == 2
    u_tip = next(row for row in report["kpis"] if row["name"] == "U_tip")
    assert u_tip["rel_delta"] == -0.020000000000000018


def test_diff_kpis_flags_changed_added_and_removed_values():
    report = diff_kpis(
        {"U_tip": -2.0, "max_mises": 100.0, "old_only": 1.0},
        {"U_tip": -2.4, "new_only": 7.0, "max_mises": 100.0},
        {"U_tip": {"rtol": 0.05}},
    )
    statuses = {row["name"]: row["status"] for row in report["kpis"]}

    assert report["status"] == "FAIL"
    assert statuses == {
        "U_tip": "FAIL",
        "max_mises": "PASS",
        "new_only": "ADDED",
        "old_only": "REMOVED",
    }
    assert report["changed_count"] == 1
    assert report["added_count"] == 1
    assert report["removed_count"] == 1


def test_diff_kpis_uses_absolute_tolerance_for_zero_baseline():
    passing = diff_kpis({"reaction_sum": 0.0}, {"reaction_sum": 0.001}, {"reaction_sum": {"atol": 0.01}})
    failing = diff_kpis({"reaction_sum": 0.0}, {"reaction_sum": 0.02}, {"reaction_sum": {"atol": 0.01}})

    assert passing["status"] == "PASS"
    assert passing["kpis"][0]["rel_delta"] is None
    assert failing["status"] == "FAIL"


def test_diff_markdown_renders_summary_table():
    report = diff_kpis({"U_tip": -2.0}, {"U_tip": -2.4}, {"U_tip": {"rtol": 0.05}})
    markdown = render_markdown(report)

    assert "# Simulation Diff: KPI" in markdown
    assert "| KPI | Status | Baseline | Candidate | Delta | Rel Delta | Tolerance |" in markdown
    assert "| U_tip | FAIL | -2 | -2.4 | -0.4 | -0.2 | rtol=0.05, atol=0 |" in markdown


def test_diff_empty_kpis_is_info():
    report = diff_kpis({}, {})

    assert report["status"] == "INFO"
    assert report["passed"]
    assert "No KPI values supplied" in render_markdown(report)


def test_collect_kpi_diff_writes_portable_report(tmp_path):
    result = collect_kpi_diff(
        baseline_kpis={"U_tip": -2.0},
        candidate_kpis={"U_tip": -2.4},
        tolerances={"U_tip": {"rtol": 0.05}},
        out_dir=tmp_path,
        diff_id="unit-simdiff",
        input_metadata={"source": "unit-test"},
    )

    assert result["workflow"] == "simulation-diff-kpi"
    assert result["overall_status"] == "FAIL"
    assert result["real_env_verified"] is False
    assert result["inputs"]["metadata"]["source"] == "unit-test"
    assert (tmp_path / "diff.json").exists()
    markdown = (tmp_path / "diff.md").read_text(encoding="utf-8")
    assert "Abaqus Agent Simulation Diff Report" in markdown
    assert "Verification Boundary" in markdown
    assert "supplied KPI JSON values" in markdown
