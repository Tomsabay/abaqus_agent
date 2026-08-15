"""
scripts/run_kpi_missing_ui_check.py
-----------------------------------
Browser-level proof that a KPI the spec asked for and never got back is
VISIBLE, and that the run's verdict is left alone. (#73(b))

THE DEFECT. `_stage_extract` assigned `result["kpis"]` from whatever the
extractor returned and put the failures in `stages.extract_kpis.errors`.
Nothing compared the two, so a spec asking for three KPIs and receiving two
produced: a COMPLETED run, a report cover reading `KPIs: 2`, and a workbench
grid with two tiles. All three are true and none of them says a third was
requested. A grid that is quietly one tile short reads as a complete result.

WHAT IS AND IS NOT BEING CHECKED. The user's decision on 2026-08-07 was
"显著标注但不改判定" — mark it prominently, do not change the verdict. So this
gate asserts the shortfall is on screen AND that the banner still says
COMPLETED. Both directions matter: a gate that only checked for the warning
would pass a build that started failing every run with a dropped KPI, which
would silently re-grade every shipped case.

IT ALSO COVERS A SECOND, OLDER BUG. `limitationText` read `l.reason`, but
`runner/dat_warnings.limitation_lines()` has always written PLAIN STRINGS into
`result["limitations"]`. On a string that lookup is undefined, so every .dat
integrity finding -- "85 tie nodes were silently left unconstrained" -- rendered
as an EMPTY card. The channel chosen because "the UI cannot render it as a
clean run" was displaying nothing at all.

Usage (needs playwright chromium):
  .venv\\Scripts\\python.exe scripts\\run_kpi_missing_ui_check.py
Exit 0 = every item passed, or Chromium is absent and the gate skipped itself.
Nothing is written inside cases/.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 8137
BASE = "http://127.0.0.1:%d" % PORT
OUT_DIR = ROOT / "artifacts" / "kpi_missing_ui_check"

MISSING_NAME = "MISES_AT_ROOT"
MISSING_REASON = ("MISES_AT_ROOT: location u'NO_SUCH_SET_EXISTS' not found in "
                  "ODB (available sets: ALL, FIXED_END, LOAD_END, TIP_NODES)")
# The exact shape runner/dat_warnings.limitation_lines() emits: a bare string.
DAT_LIMITATION = "Tie 约束有 85 个节点没绑上（85 处） 处理办法：放宽 position_tolerance"

BOOTSTRAP = r'''
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, r"{root}")
out = Path(r"{out}")
sess_dir = out / "sessions"
sess_dir.mkdir(parents=True, exist_ok=True)
os.environ["ABAQUS_AGENT_WORKBENCH_SESSION_DIR"] = str(sess_dir)
os.environ["ABAQUS_AGENT_EVIDENCE_VAULT"] = str(out / "vault")

import server

now = time.time()
# A run that SUCCEEDED and still dropped a KPI. That combination is the whole
# point: if the run had failed, the failure banner would carry the news.
server.RUNS["short"] = {{
    "run_id": "short", "status": "COMPLETED", "started_at": now,
    "finished_at": now, "spec": {{"meta": {{"model_name": "Cantilever"}}}},
    "stages": {{}},
    "kpis": {{"U_tip": -0.0019039579201489687, "MISES_MAX": 0.6528551578521729}},
    "kpis_missing": [{{"name": {missing_name!r}, "type": "field_max",
                      "reason": {missing_reason!r}}}],
    "limitations": [{{"feature": "KPI", "value": {missing_name!r},
                     "kind": "kpi_not_extracted", "reason": {missing_reason!r}}}],
}}
# The control. Same shape, nothing dropped -- proves the denominator and the
# warning tile appear because of the shortfall and not on every run.
server.RUNS["whole"] = {{
    "run_id": "whole", "status": "COMPLETED", "started_at": now,
    "finished_at": now, "spec": {{"meta": {{"model_name": "Cantilever"}}}},
    "stages": {{}},
    "kpis": {{"U_tip": -0.0019039579201489687, "MISES_MAX": 0.6528551578521729}},
    "kpis_missing": [],
}}
# The string-limitation regression, in the shape dat_warnings actually writes.
server.RUNS["datstring"] = {{
    "run_id": "datstring", "status": "COMPLETED", "started_at": now,
    "finished_at": now, "spec": {{"meta": {{"model_name": "Bearing"}}}},
    "stages": {{}}, "kpis": {{"U_tip": 1.0}}, "kpis_missing": [],
    "limitations": [{dat_limitation!r}],
}}

session = {{
    "session_id": "wb-kpimissing", "title": "kpi missing check",
    "created_at": now, "updated_at": now,
    "messages": [], "current_spec_yaml": "", "pending": None,
    "runs": [
        {{"run_id": rid, "status": "COMPLETED", "accepted_at": now,
          "proposal_id": "p", "model_name": "Cantilever", "kpis": {{}},
          "visuals": []}}
        for rid in ("short", "whole", "datstring")
    ],
}}
(sess_dir / "wb-kpimissing.json").write_text(
    json.dumps(session, ensure_ascii=False), encoding="utf-8")

import uvicorn
uvicorn.run(server.app, host="127.0.0.1", port={port}, log_level="warning")
'''


def wait_health(deadline_s: int = 60) -> None:
    t0 = time.time()
    while time.time() - t0 < deadline_s:
        try:
            with urllib.request.urlopen(BASE + "/health", timeout=5):
                return
        except OSError:
            time.sleep(1)
    raise RuntimeError("server did not become healthy")


def _read_run(page, run_id: str) -> dict:
    """Render one run and read back what the grid and the panel contain."""
    page.evaluate("id => showRun(id)", run_id)
    page.wait_for_timeout(900)
    return page.evaluate(
        """() => {
            const grid = document.getElementById('kpi-grid');
            const labels = [...document.querySelectorAll('#results-inner .sec-label')]
                .map(e => e.innerText);
            const slot = document.getElementById('diag-slot');
            const banner = document.querySelector('#results-inner .status-banner');
            return {
                cards: grid ? grid.querySelectorAll('.kpi-card').length : 0,
                missing: grid ? grid.querySelectorAll('.kpi-card.kpi-missing').length : 0,
                missingText: grid
                    ? [...grid.querySelectorAll('.kpi-card.kpi-missing')].map(e => e.innerText)
                    : [],
                labels: labels,
                slotText: slot ? slot.innerText : '',
                bannerText: banner ? banner.innerText : '',
            };
        }"""
    )


def main() -> int:
    try:
        from playwright.sync_api import Error as PWError
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(json.dumps({"overall": "skipped",
                          "reason": "playwright is not installed"}))
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    boot = BOOTSTRAP.format(
        root=str(ROOT), out=str(OUT_DIR), port=PORT,
        missing_name=MISSING_NAME, missing_reason=MISSING_REASON,
        dat_limitation=DAT_LIMITATION,
    )
    boot_path = OUT_DIR / "_bootstrap.py"
    boot_path.write_text(boot, encoding="utf-8")

    log = open(OUT_DIR / "server.log", "w", encoding="utf-8")  # noqa: SIM115
    proc = subprocess.Popen(
        [sys.executable, str(boot_path)], cwd=str(ROOT),
        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
    )
    items: list[dict] = []
    try:
        wait_health()

        # The API layer first: a DOM assertion on a field the server never sent
        # would be measuring the stub, not the wire.
        with urllib.request.urlopen("%s/api/run/short" % BASE, timeout=15) as r:
            api_short = json.loads(r.read())
        items.append({
            "id": "1_api_carries_the_field",
            "status": "pass" if [m["name"] for m in api_short.get("kpis_missing", [])]
                      == [MISSING_NAME] else "fail",
            "note": "GET /api/run/short returns kpis_missing=%s"
                    % [m["name"] for m in api_short.get("kpis_missing", [])],
        })

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except PWError as exc:
                print(json.dumps({"overall": "skipped",
                                  "reason": "chromium unavailable: %s" % exc}))
                return 0
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("%s/workbench?session=wb-kpimissing" % BASE,
                      wait_until="domcontentloaded")
            page.wait_for_function("typeof showRun === 'function'", timeout=20000)
            page.wait_for_timeout(1200)

            short = _read_run(page, "short")
            page.screenshot(path=str(OUT_DIR / "grid_short.png"))
            whole = _read_run(page, "whole")
            page.screenshot(path=str(OUT_DIR / "grid_whole.png"))
            datstring = _read_run(page, "datstring")
            page.screenshot(path=str(OUT_DIR / "diag_datstring.png"))

            page.evaluate("() => I18N.setLang('en')")
            page.wait_for_timeout(400)
            short_en = _read_run(page, "short")
            page.screenshot(path=str(OUT_DIR / "grid_short_en.png"))
            browser.close()

        missing_text = " ".join(short["missingText"])
        kpi_label = " ".join(
            ln for ln in short["labels"] if "KPI" in ln or "指标" in ln)
        whole_label = " ".join(
            ln for ln in whole["labels"] if "KPI" in ln or "指标" in ln)

        items.append({
            "id": "2_the_grid_has_a_tile_for_it",
            "status": "pass" if (short["cards"] == 3 and short["missing"] == 1)
                      else "fail",
            "note": "2 delivered + 1 missing -> %d tiles, %d of them flagged "
                    "(want 3 and 1)" % (short["cards"], short["missing"]),
        })
        items.append({
            "id": "3_the_tile_names_the_kpi_and_the_reason",
            "status": "pass" if (MISSING_NAME in missing_text
                                 and "NO_SUCH_SET_EXISTS" in missing_text)
                      else "fail",
            "note": missing_text[:300],
        })
        items.append({
            "id": "4_the_heading_carries_the_denominator",
            "status": "pass" if "2/3" in kpi_label.replace(" ", "") else "fail",
            "note": kpi_label[:200],
        })
        items.append({
            # The direction that is easy to forget. A denominator on every run
            # is a denominator nobody reads.
            "id": "5_a_complete_run_is_left_alone",
            "status": "pass" if (whole["cards"] == 2 and whole["missing"] == 0
                                 and "/" not in whole_label) else "fail",
            "note": "%d tiles, %d flagged, label %r"
                    % (whole["cards"], whole["missing"], whole_label[:120]),
        })
        items.append({
            # #73(b) as decided: mark it, do not re-grade it.
            "id": "6_the_verdict_is_unchanged",
            "status": "pass" if "COMPLETED" in short["bannerText"] else "fail",
            "note": short["bannerText"].replace("\n", " ")[:200],
        })
        items.append({
            "id": "7_string_limitation_is_not_a_blank_card",
            "status": "pass" if "position_tolerance" in datstring["slotText"]
                      else "fail",
            "note": datstring["slotText"].replace("\n", " ")[:300],
        })
        items.append({
            "id": "8_english_says_it_too",
            "status": "pass" if (short_en["missing"] == 1
                                 and "not extracted" in " ".join(
                                     short_en["missingText"]).lower()) else "fail",
            "note": " ".join(short_en["missingText"])[:250],
        })
        items.append({
            "id": "9_no_page_errors",
            "status": "pass" if not errors else "fail",
            "note": "; ".join(errors[:3]) or "none",
        })
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()

    failed = [i for i in items if i["status"] != "pass"]
    result = {"overall": "fail" if failed else "pass", "items": items,
              "artifacts": str(OUT_DIR)}
    (OUT_DIR / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    for item in items:
        print("[%-4s] %s — %s" % (item["status"], item["id"], item["note"][:160]))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
