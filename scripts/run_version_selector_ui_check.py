"""Browser check: the release selector must reflect the installed solver.

Screenshot-trust is not evidence here, so every claim below is a DOM assertion
against the live page served by server.py.

Pinned defects:
  * the selector offered 2023/2024/2025 only, so a user on 2021 (this build's
    own machine) could not pick their own release, and the generated spec
    carried a year the machine did not have;
  * validateSpecText() rejected anything outside 2023/2024/2025, telling that
    same user their valid spec was invalid.

Run:  .venv\\Scripts\\python.exe scripts\\run_version_selector_ui_check.py
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCHEMA_YEARS = ["2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(url: str, timeout: float = 60.0) -> dict:
    import urllib.request
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/health", timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:                      # server still booting
            last = exc
            time.sleep(1.0)
    raise RuntimeError("server never became healthy: %s" % last)


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP: playwright not installed")
        return 0

    port = _free_port()
    url = "http://127.0.0.1:%d" % port
    proc = subprocess.Popen(
        [sys.executable, "server.py"],
        cwd=str(ROOT),
        env={**__import__("os").environ, "ABAQUS_AGENT_PORT": str(port)},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, text=True, errors="replace",
    )
    failures: list[str] = []
    try:
        health = _wait_for_health(url)
        detected = health.get("abaqus_release")
        print("server /health abaqus_release = %r" % detected)

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            # SSE keeps the network busy; networkidle never fires.
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_function(
                "typeof applyDetectedRelease === 'function'", timeout=30000)

            offered = page.eval_on_selector(
                "#abaqus-version",
                "el => [...el.options].map(o => o.value)")
            print("selector offers: %s" % offered)
            missing = [y for y in SCHEMA_YEARS if y not in offered]
            if missing:
                failures.append("selector is missing schema years: %s" % missing)

            if detected:
                page.wait_for_function(
                    "v => document.getElementById('abaqus-version').value === v",
                    arg=str(detected), timeout=30000)
                selected = page.eval_on_selector(
                    "#abaqus-version", "el => el.value")
                print("selector settled on: %s" % selected)
                if selected != str(detected):
                    failures.append(
                        "selector shows %s but the solver reports %s"
                        % (selected, detected))
            else:
                print("no solver detected; skipping auto-selection assertion")

            # The client-side validator must accept every schema year.
            verdicts = page.evaluate(
                """years => Object.fromEntries(years.map(y => {
                    const spec = [
                      'meta:', '  abaqus_release: "' + y + '"',
                      'geometry:', 'material:',
                      'analysis:', '  solver: standard',
                      'bc_load:', 'outputs:', '  kpis:',
                    ].join('\\n');
                    const r = validateSpecText(spec);
                    return [y, r.errors.filter(e => e.includes('abaqus_release'))];
                }))""",
                SCHEMA_YEARS)
            rejected = {y: e for y, e in verdicts.items() if e}
            print("validator rejects: %s" % (rejected or "none"))
            if rejected:
                failures.append(
                    "client validator rejects valid schema years: %s" % rejected)

            # A hand pick must survive a later /health refresh. Driven through
            # JS because the control lives in a panel that is not the active
            # tab on load — Playwright refuses to click an invisible element,
            # but a real user reaches it by opening that panel.
            page.evaluate(
                """() => {
                    const el = document.getElementById('abaqus-version');
                    el.value = '2026';
                    el.dispatchEvent(new Event('change'));
                }""")
            page.evaluate("checkServer()")
            page.wait_for_timeout(1500)
            after = page.eval_on_selector("#abaqus-version", "el => el.value")
            print("after manual pick + health refresh: %s" % after)
            if after != "2026":
                failures.append(
                    "auto-selection overwrote the user's manual pick (%s)" % after)

            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()

    if failures:
        print("\nRESULT: FAIL")
        for f in failures:
            print("  - %s" % f)
    else:
        print("\nRESULT: PASS")
    # The verdict scripts/run_all_real_checks.py reads. It has to be the last
    # parseable JSON object on stdout.
    print(json.dumps({"schema": "version_selector_ui_check/1",
                      "result": "FAIL" if failures else "PASS",
                      "failures": failures}, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
