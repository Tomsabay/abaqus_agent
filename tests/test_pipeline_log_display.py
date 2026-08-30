"""The run console is narration, not a debug dump.

What it used to print on a perfectly normal run:

  * ``INP_WRITTEN: <drive>:\\...\\cases\\...\\Cantilever.inp`` -- the
    operator's disk layout and user name in every screenshot;
  * ``errors: []`` / ``odb_exists: True`` / ``progress_pct: -1`` on every
    monitor poll -- raw verdict internals rendered as if they were news;
  * ``autorepair: {'attempt': 1, 'max': 2}`` -- a Python dict repr on screen,
    because every key of that payload was suppressed and the fallback dumped
    the whole dict.

These tests pin the rewrite: paths shortened to ``<dir>/<file>``, monitor
noise suppressed, every remaining line human-readable. Hermetic -- the
orchestrator is a mock driven by hand.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.pipeline import _display_path, _display_val, _run_pipeline_real  # noqa: E402


def test_display_path_shortens_windows_absolute_path():
    src = r"C:\sim\proj\cases\cantilever\runs\6ad82dcf\Cantilever.inp"
    assert _display_path(src) == "6ad82dcf/Cantilever.inp"


def test_display_path_shortens_posix_absolute_path():
    assert _display_path("/tmp/model.inp") == "tmp/model.inp"


def test_display_path_keeps_non_path_text():
    assert _display_path("Cantilever.inp") == "Cantilever.inp"
    assert _display_path("85 tie nodes were left unconstrained") == \
        "85 tie nodes were left unconstrained"
    assert _display_path(3) == "3"


def test_display_path_drive_root_file_keeps_name_only():
    assert _display_path(r"D:\model.inp") == "model.inp"


def test_display_val_joins_lists():
    vals = [r"D:\x\runs\abc\S_mises.png", r"D:\x\runs\abc\U_mag.png"]
    assert _display_val(vals) == "abc/S_mises.png、abc/U_mag.png"


def _make_run(run_id):
    return {
        "run_id": run_id,
        "status": "PENDING",
        "spec": {"meta": {"model_name": "t"}},
        "runner_cfg": {"cpus": 2, "mp_mode": "threads"},
        "stages": {},
        "kpis": {},
        "started_at": time.time(),
        "finished_at": None,
        "progress_pct": 0,
    }


def _drive_pipeline(progress_calls):
    """Run _run_pipeline_real with a mock orchestrator that replays
    `progress_calls` through on_progress, and return the run dict."""
    runs = {"r1": _make_run("r1")}
    captured = {}

    def fake_orch_init(**kwargs):
        captured["fn"] = kwargs.get("on_progress")
        mock = MagicMock()

        def run():
            for stage, data in progress_calls:
                captured["fn"](stage, data)
            return {"status": "COMPLETED", "kpis": {}, "regression": {}}

        mock.run = run
        return mock

    with patch("agent.orchestrator.AbaqusOrchestrator", side_effect=fake_orch_init):
        # Same pattern as test_real_pipeline.py, deliberately: asyncio.run()
        # closes its loop AND unsets the thread's loop on exit, which fails
        # every later get_event_loop() test in the suite (measured: 10).
        asyncio.get_event_loop().run_until_complete(_run_pipeline_real("r1", runs))
    return runs["r1"]


def _texts(run, stage):
    return [log["text"] for log in run["stages"][stage]["logs"]]


def test_inp_written_line_has_no_absolute_path():
    run = _drive_pipeline([
        ("build_model", {"inp": r"C:\sim\proj\cases\c\runs\abc\Model.inp"}),
    ])
    texts = _texts(run, "build_model")
    assert "INP_WRITTEN: abc/Model.inp" in texts
    assert not any("C:\\" in t for t in texts)


def test_monitor_poll_noise_is_suppressed():
    run = _drive_pipeline([
        ("monitor_job", {"status": "running", "progress_pct": 43.0,
                         "last_increment": 12, "last_time": 0.5,
                         "errors": [], "warnings": [], "odb_exists": False}),
    ])
    texts = _texts(run, "monitor_job")
    assert texts == ["status: running"]


def test_monitor_errors_render_one_line_each():
    run = _drive_pipeline([
        ("monitor_job", {"status": "aborted",
                         "errors": ["TIME INCREMENT REQUIRED IS LESS THAN MINIMUM"]}),
    ])
    logs = run["stages"]["monitor_job"]["logs"]
    err = [log for log in logs if log["level"] == "error"]
    assert len(err) == 1
    assert "TIME INCREMENT" in err[0]["text"]


def test_dat_integrity_clean_and_dirty():
    clean = _drive_pipeline([("dat_integrity", {"integrity_count": 0, "findings": []})])
    assert _texts(clean, "dat_integrity") == ["✓ .dat 完整性检查：无告警"]

    dirty = _drive_pipeline([
        ("dat_integrity", {"integrity_count": 1,
                           "findings": ["TIE_ADJUST_UNCONSTRAINED"]}),
    ])
    texts = _texts(dirty, "dat_integrity")
    assert any("完整性告警 1 条" in t for t in texts)
    assert any("TIE_ADJUST_UNCONSTRAINED" in t for t in texts)


def test_exported_images_render_short_names():
    run = _drive_pipeline([
        ("export_odb_images", {"images": [r"D:\x\runs\abc\S_mises.png"]}),
    ])
    texts = _texts(run, "export_odb_images")
    assert "✓ 云图导出：abc/S_mises.png" in texts
    assert not any("D:\\" in t for t in texts)


def test_exported_image_records_render_path_not_dict_repr():
    """The exporter sends records, not paths — the real shape from a real run."""
    record = {"name": "u_magnitude", "bytes": 24208, "component": None,
              "invariant": "MAGNITUDE", "path": "u_magnitude.png",
              "field_variable": "U"}
    run = _drive_pipeline([("export_odb_images", {"images": [record]})])
    texts = _texts(run, "export_odb_images")
    assert "✓ 云图导出：u_magnitude.png" in texts
    assert not any("{'" in t for t in texts)


def test_contract_check_count_zero_is_not_a_log_line():
    run = _drive_pipeline([
        ("physics_contracts", {"passed": None, "checks": 0, "caveat": "没有加载到任何 physics contract"}),
    ])
    texts = _texts(run, "physics_contracts")
    assert not any("checks" in t for t in texts)
    assert any("NOT GRADED" in t for t in texts)

    graded = _drive_pipeline([("physics_contracts", {"passed": True, "checks": 3})])
    assert "契约检查 3 项" in _texts(graded, "physics_contracts")


def test_autorepair_is_a_sentence_not_a_dict_repr():
    run = _drive_pipeline([("autorepair", {"attempt": 1, "max": 2})])
    assert _texts(run, "autorepair") == ["自动修复：第 1/2 次重试"]


def test_parametric_sweep_progress_lines():
    run = _drive_pipeline([
        ("parametric_sweep", {"index": 0, "total": 4, "status": "starting"}),
        ("parametric_sweep", {"index": 2, "total": 4, "status": "completed"}),
        ("parametric_sweep", {"index": 4, "total": 4, "status": "completed"}),
    ])
    assert _texts(run, "parametric_sweep") == [
        "参数扫掠：共 4 个样本",
        "样本 2/4：completed",
        "✓ 参数扫掠完成：4 个样本",
    ]


def test_no_log_line_ever_contains_a_dict_repr():
    run = _drive_pipeline([
        ("build_model", {"inp": r"D:\x\runs\abc\Model.inp"}),
        ("monitor_job", {"status": "running", "errors": [], "odb_exists": True}),
        ("dat_integrity", {"integrity_count": 0, "findings": []}),
        ("compare_kpis", {"passed": None, "details": {},
                          "caveat": "本次运行没有提供 expected.json 基准"}),
        ("autorepair", {"attempt": 1, "max": 2}),
    ])
    for stage in run["stages"].values():
        for log in stage["logs"]:
            assert "{'" not in log["text"], log["text"]
            assert not log["text"].endswith(": {}"), log["text"]
