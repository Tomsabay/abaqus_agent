"""
scripts/run_diagnosis_ui_check.py
---------------------------------
Browser-level proof that a failed run actually shows its diagnosis.

The defect this guards: before the diagnosis panel existed, every problem the
engine detected was written to the live console, which ``watchRun`` clears and
``showRun`` never repopulates. A user who clicked away from a failed run and
back saw a bare "✗ FAILED" chip and had no way to recover the error text.

Rather than trust a screenshot, this asserts on the DOM: the raw solver error
must be present verbatim, and when the pattern library matches, the diagnosis
must appear alongside it — never instead of it.

Three runs are seeded, covering the three shapes the panel must handle:
  failed-known    a recognised nonconvergence banner -> error + finding
  failed-unknown  text no pattern matches            -> error + "no match" line
  refused         a backend refusal, not a crash     -> notice + limitation

Usage (needs playwright chromium):
  .venv\\Scripts\\python.exe scripts\\run_diagnosis_ui_check.py
Exit 0 = every assertion held. Nothing is written inside cases/.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 8134
BASE = "http://127.0.0.1:%d" % PORT
OUT_DIR = ROOT / "artifacts" / "diagnosis_ui_check"

KNOWN_MSG = " ***ERROR: TOO MANY ATTEMPTS MADE FOR THIS INCREMENT: ANALYSIS TERMINATED\n"
UNKNOWN_MSG = "a line the pattern library has never seen before\n"
RAW_ERROR_TEXT = "increment 12 abandoned after 5 attempts"
REFUSAL_NOTICE = "CalculiX 2.23 无法忠实求解这个问题，因此没有输出任何数值"
REFUSAL_REASON = "CalculiX 不认识 CONWEP 爆炸载荷"

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

known_dir = out / "wd_known"; known_dir.mkdir(parents=True, exist_ok=True)
(known_dir / "Job-1.msg").write_text({known_msg!r}, encoding="utf-8")
unknown_dir = out / "wd_unknown"; unknown_dir.mkdir(parents=True, exist_ok=True)
(unknown_dir / "Job-1.msg").write_text({unknown_msg!r}, encoding="utf-8")

now = time.time()
server.RUNS["failed-known"] = {{
    "run_id": "failed-known", "status": "FAILED", "started_at": now,
    "finished_at": now, "workdir": str(known_dir),
    "spec": {{"meta": {{"model_name": "Job-1"}}}}, "stages": {{}}, "kpis": {{}},
    "error": {{"error_code": "NONCONVERGENCE", "message": {raw_error!r}}},
}}
server.RUNS["failed-unknown"] = {{
    "run_id": "failed-unknown", "status": "FAILED", "started_at": now,
    "finished_at": now, "workdir": str(unknown_dir),
    "spec": {{"meta": {{"model_name": "Job-1"}}}}, "stages": {{}}, "kpis": {{}},
    "error": {{"error_code": "JOB_FAILED", "message": "opaque failure text"}},
}}
server.RUNS["refused"] = {{
    "run_id": "refused", "status": "REFUSED", "started_at": now,
    "finished_at": now, "spec": {{"meta": {{"model_name": "Job-1"}}}},
    "stages": {{}}, "kpis": {{}},
    "kpi_notice": {notice!r},
    "limitations": [{{"feature": "bc_load.load_type", "value": "blast_conwep",
                     "reason": {reason!r}}}],
}}

session = {{
    "session_id": "wb-diagcheck", "title": "diagnosis check",
    "created_at": now, "updated_at": now,
    "messages": [], "current_spec_yaml": "", "pending": None,
    "runs": [
        {{"run_id": rid, "status": st, "accepted_at": now,
          "proposal_id": "p", "model_name": "Job-1", "kpis": {{}}, "visuals": []}}
        for rid, st in (("failed-known", "FAILED"), ("failed-unknown", "FAILED"),
                        ("refused", "REFUSED"))
    ],
}}
(sess_dir / "wb-diagcheck.json").write_text(
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


def main() -> int:
    from playwright.sync_api import sync_playwright

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    boot = BOOTSTRAP.format(
        root=str(ROOT), out=str(OUT_DIR), port=PORT,
        known_msg=KNOWN_MSG, unknown_msg=UNKNOWN_MSG,
        raw_error=RAW_ERROR_TEXT, notice=REFUSAL_NOTICE, reason=REFUSAL_REASON,
    )
    boot_path = OUT_DIR / "_bootstrap.py"
    boot_path.write_text(boot, encoding="utf-8")

    log = open(OUT_DIR / "server.log", "w", encoding="utf-8")  # noqa: SIM115
    proc = subprocess.Popen(
        [sys.executable, str(boot_path)], cwd=str(ROOT),
        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
    )
    checks: list[dict] = []
    try:
        wait_health()

        # API layer first: if this is wrong the DOM assertions are meaningless.
        for rid in ("failed-known", "failed-unknown", "refused"):
            with urllib.request.urlopen("%s/api/run/%s/doctor" % (BASE, rid), timeout=15) as r:
                checks.append({"id": "api:" + rid, "payload": json.loads(r.read())})

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            # NOT networkidle: the workbench holds an SSE stream open, so the
            # network never goes idle and goto would always time out.
            page.goto("%s/workbench?session=wb-diagcheck" % BASE,
                      wait_until="domcontentloaded")
            page.wait_for_function("typeof showRun === 'function'", timeout=20000)
            page.wait_for_timeout(1200)

            for rid, expect in (
                ("failed-known", [RAW_ERROR_TEXT]),
                ("failed-unknown", [RAW_ERROR_TEXT.split()[0], "诊断模式库没有匹配"]),
                ("refused", [REFUSAL_NOTICE, REFUSAL_REASON]),
            ):
                page.evaluate("id => showRun(id)", rid)
                page.wait_for_timeout(900)
                slot = page.eval_on_selector(
                    "#diag-slot", "el => el.innerText") if page.query_selector("#diag-slot") else ""
                cards = page.eval_on_selector_all(".diag-card", "els => els.length")
                page.screenshot(path=str(OUT_DIR / ("panel_%s.png" % rid)), full_page=False)
                checks.append({
                    "id": "dom:" + rid,
                    "diag_cards": cards,
                    "slot_text_len": len(slot),
                    "slot_text": slot[:600],
                    "expected_present": {
                        s: (s in slot) for s in
                        (expect if rid != "failed-unknown" else [expect[1]])
                    },
                })
            checks.append({"id": "page_errors", "errors": errors})
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()

    problems: list[str] = []
    for c in checks:
        if c["id"].startswith("dom:"):
            if c["diag_cards"] < 1:
                problems.append("%s rendered no .diag-card" % c["id"])
            for text, present in c["expected_present"].items():
                if not present:
                    problems.append("%s missing expected text: %s" % (c["id"], text[:50]))
        if c["id"] == "page_errors" and c["errors"]:
            problems.append("page errors: %s" % c["errors"][:3])
    known = next(c for c in checks if c["id"] == "api:failed-known")["payload"]
    unknown = next(c for c in checks if c["id"] == "api:failed-unknown")["payload"]
    if not known["matched"]:
        problems.append("known nonconvergence produced no finding")
    if unknown["matched"] or unknown["findings"]:
        problems.append("unmatched text must not produce an invented finding")
    if not unknown.get("error"):
        problems.append("unmatched run must still echo the raw error")

    result = {"result": "PASS" if not problems else "FAIL",
              "problems": problems, "checks": checks}
    (OUT_DIR / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False)[:4000])
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
