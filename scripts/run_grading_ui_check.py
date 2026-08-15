"""Browser check: the workbench shows whether a run was graded, and how.

Before this, the workbench read `regression.passed === false` to decide whether
to open the diagnosis panel and rendered no verdict anywhere else. Combined
with core.pipeline never passing `expected_path` to the orchestrator, that made
three different runs look identical on screen:

    a run whose every KPI matched its baseline
    a run with no baseline at all
    a run whose contracts were never loaded

All three showed KPI cards and a green COMPLETED banner and nothing else. This
gate drives the real `gradingSection` in real Chromium and pins the three
apart, plus the two states that must NOT be swallowed by the new amber one:
a genuine PASS and a genuine FAIL.

Hermetic -- no Abaqus, no solver, no session. The page is loaded and the
shipped function is called with the payload shapes core.pipeline now produces.

Run:  .venv\\Scripts\\python.exe scripts\\run_grading_ui_check.py
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "artifacts" / "grading_ui"


@contextlib.contextmanager
def _server(port: int):
    env = {**os.environ, "ABAQUS_AGENT_PORT": str(port),
           "ABAQUS_AGENT_HOST": "127.0.0.1"}
    log_path = Path(tempfile.gettempdir()) / ("grading_ui_%d.log" % port)
    log = open(log_path, "w", encoding="utf-8", errors="replace")
    print("server log: %s" % log_path)
    proc = subprocess.Popen(
        [sys.executable, "server.py"], cwd=str(ROOT), env=env,
        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
    try:
        import urllib.request
        deadline = time.time() + 40
        while time.time() < deadline:
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/" % port, timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        yield
    finally:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            proc.terminate()
        log.close()


class Items:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.rows.append({"name": name, "status": "pass" if ok else "fail",
                          "detail": detail})
        print("  %-4s  %-46s %s" % ("PASS" if ok else "FAIL", name, detail))

    def failed(self) -> int:
        return sum(1 for r in self.rows if r["status"] != "pass")


# The payloads below are the exact shapes the fixed pipeline writes.
GRADED_PASS = {
    "status": "COMPLETED",
    "regression": {"passed": True, "comparisons": {"U_tip": {"status": "PASS"}}},
    "contracts": {"passed": True, "results": [{"name": "tip_down", "status": "PASS"}]},
}
GRADED_FAIL = {
    "status": "COMPLETED",
    "regression": {"passed": False, "comparisons": {"U_tip": {"status": "PASS"}},
                   "blocked_by_integrity": {"count": 85, "findings": ["x"],
                                            "note": "85 个节点上的约束没有生效"}},
    "contracts": {"passed": False, "results": [{"name": "tip_down", "status": "FAIL"}]},
}
NOT_GRADED = {
    "status": "COMPLETED",
    "regression": {"passed": None, "comparisons": {},
                   "not_compared_reason": "本次运行没有提供 expected.json 基准，未做任何数值比对"},
    "contracts": {"passed": None, "results": [],
                  "not_checked_reason": "没有加载到任何 physics contract，本次运行未做契约检查"},
}
LEGACY = {"status": "COMPLETED", "regression": {}, "contracts": {}}
UNSOLVED = dict(NOT_GRADED, unsolved=True)


def _items(browser, base: str, items: Items) -> None:
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base + "/workbench")
    page.wait_for_function("typeof gradingSection === 'function'", timeout=20000)

    def html(src):
        return page.evaluate("(s) => gradingSection(s)", src)

    graded = html(GRADED_PASS)
    items.add(
        "a_graded_run_says_pass_in_green",
        "g-pass" in graded and "g-none" not in graded and "g-fail" not in graded,
        "classes: %s" % _classes(graded))

    failed = html(GRADED_FAIL)
    items.add(
        "a_failed_run_says_fail_in_red",
        failed.count("g-fail") == 2 and "g-pass" not in failed,
        "classes: %s" % _classes(failed))

    items.add(
        "an_integrity_block_shows_the_reason_not_just_the_verdict",
        "85 个节点上的约束没有生效" in failed,
        "withdrawn-verdict note reaches the card: %s"
        % ("yes" if "85 个节点" in failed else "no"))

    ungraded = html(NOT_GRADED)
    items.add(
        "a_run_with_no_baseline_says_not_graded",
        ungraded.count("g-none") == 2
        and "g-pass" not in ungraded and "g-fail" not in ungraded,
        "classes: %s" % _classes(ungraded))

    items.add(
        "not_graded_says_which_input_was_missing",
        "expected.json" in ungraded and "physics contract" in ungraded,
        "both reasons present: %s"
        % ("yes" if "expected.json" in ungraded and "physics contract" in ungraded
           else "no"))

    items.add(
        "the_three_states_are_distinguishable_on_screen",
        len({graded, failed, ungraded}) == 3,
        "3 distinct renders from 3 payloads")

    items.add(
        "a_pre_fix_run_record_asserts_nothing",
        html(LEGACY) == "",
        "empty regression/contracts -> no section (cannot claim NOT GRADED "
        "about a record that predates the field)")

    items.add(
        "an_unsolved_run_does_not_compete_with_its_own_refusal",
        html(UNSOLVED) == "",
        "unsolved -> no verdict section")

    # The reason text is user-facing; a payload carrying markup must not
    # become markup. `esc` is applied per field, so this proves the wiring.
    injected = json.loads(json.dumps(NOT_GRADED))
    injected["regression"]["not_compared_reason"] = "<img src=x onerror=alert(1)>"
    hostile = html(injected)
    items.add(
        "a_reason_string_is_escaped_not_rendered",
        "<img" not in hostile and "&lt;img" in hostile,
        "payload markup arrives escaped")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    page.evaluate(
        "(h) => { const d = document.createElement('div');"
        " d.id='grade-shot'; d.style.cssText='padding:24px;background:#0E1116';"
        " d.innerHTML = h; document.body.prepend(d); }",
        graded + failed + ungraded)
    page.locator("#grade-shot").screenshot(path=str(OUT_DIR / "verdicts.png"))

    items.add("no_page_errors", not errors, "page errors: %s" % (errors or "none"))
    page.close()


def _classes(html: str) -> str:
    return ",".join(c for c in ("g-pass", "g-fail", "g-none") if c in html) or "none"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8043)
    args = parser.parse_args()

    started = time.time()
    items = Items()
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        items.add("playwright_available", False, "%s" % exc)
        sync_playwright = None

    if sync_playwright is not None:
        base = "http://127.0.0.1:%d" % args.port
        with _server(args.port), sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                _items(browser, base, items)
            finally:
                browser.close()

    report = {
        "schema": "grading_ui_check/1",
        "seconds": round(time.time() - started, 1),
        "overall": "pass" if items.failed() == 0 else "fail",
        "items": items.rows,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if items.failed() == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
