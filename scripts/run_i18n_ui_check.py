"""Drive the real UI in a real browser and check the language switch holds up.

scripts/run_i18n_static_check.py counts strings. Counting strings cannot see
any of the ways a translated UI actually breaks, and an adversarial review of
the first i18n pass found six of them behind a passing static gate:

  * switching language re-stamped the empty-state placeholder over a finished
    Evidence report and over a Solver Doctor report — real output, destroyed by
    pressing a language button;
  * a configured API key's badge flipped back to "Not configured" while keeping
    its green class, so the UI contradicted itself about the user's own state;
  * a running replay's stop button relabelled itself "▶ Play", so it said the
    opposite of what pressing it would do;
  * thirteen async buttons dropped their "⟳ Running…" label while still
    disabled, leaving a button that looks idle and cannot be pressed;
  * the spec-validation verdict and the open Solver Doctor pattern never
    re-rendered, so they sat in the previous language permanently;
  * and the pages had grown a hard dependency on /static/i18n.js whose absence
    killed every event handler on the page.

Each of those is a case here. Run:

    .venv\\Scripts\\python.exe scripts\\run_i18n_ui_check.py

It starts its own server on a free port and stops it again. To drive one you
already have running: --no-serve --port 8000.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_i18n_static_check as static  # noqa: E402

PAGES = ("/", "/workbench")

# URL -> the markup this gate should read the catalogue from.
PAGE_SOURCE = {"/": "frontend/index.html", "/workbench": "frontend/workbench.html"}

# A raw key that leaked to screen looks like this. `t()` returning its own
# argument is the engine's last-resort fallback; seeing one means a catalogue
# entry is missing in BOTH languages.
RAW_KEY = re.compile(r"(?<![\w./-])[a-z][a-z0-9]*(?:\.[a-z0-9_]+){2,}(?![\w/-])")

CJK = re.compile(r"[一-鿿]")

# Nodes that carry runtime state rather than translatable copy. Each one is a
# defect that shipped and was caught by review, not a hypothetical.
PROBES = {
    "/": [
        {"selector": "#evidence-report", "stamp": "# Evidence report\nU_tip = -1.9e-3",
         "disable": False,
         "why": "a finished Evidence report was overwritten by the empty-state text"},
        {"selector": "#doctor-report", "stamp": "# Solver Doctor\nERROR: too many attempts",
         "disable": False,
         "why": "a finished Solver Doctor report was overwritten by the empty-state text"},
        {"selector": "#btn-evidence-run", "stamp": "PROBE running…", "disable": True,
         "why": "a disabled, in-flight button lost its progress label and looks idle"},
        {"selector": "#btn-copilot-replay", "stamp": "PROBE stop 3/9", "disable": False,
         "why": "the replay button reverted to 'Play' while the replay was still running"},
    ],
    # The workbench keeps its empty state in a separate element from its
    # content (#results-empty beside #results-inner, #diff-empty beside
    # #diff-body) and toggles display, which is the pattern that made the tools
    # page's shared <pre> break. These probes pin that separation: if someone
    # later collapses the two into one node, the runtime content starts getting
    # re-stamped on every switch and this goes red.
    "/workbench": [
        {"selector": "#results-inner", "stamp": "U_tip = -1.903958e-3 mm",
         "disable": False,
         "why": "solve results were overwritten on a language switch"},
        {"selector": "#console-body", "stamp": "[solve] frame 12 · 34%",
         "disable": False,
         "why": "live console output was overwritten on a language switch"},
    ],
}


class Failures(list):
    def add(self, page: str, what: str) -> None:
        self.append("%s: %s" % (page, what))
        print("  FAIL  %s: %s" % (page, what))

    def ok(self, page: str, what: str) -> None:
        print("  ok    %s: %s" % (page, what))


@contextmanager
def _server(port: int):
    env = {**os.environ, "ABAQUS_AGENT_PORT": str(port),
           "ABAQUS_AGENT_HOST": "127.0.0.1"}
    # To a file, never to a PIPE nobody drains: uvicorn logs a line per
    # request, and once the pipe buffer fills the server blocks on write and
    # stops answering. That looked exactly like a page that would not load.
    log_path = Path(tempfile.gettempdir()) / ("i18n_ui_check_%d.log" % port)
    log = open(log_path, "w", encoding="utf-8", errors="replace")
    print("server log: %s" % log_path)
    proc = subprocess.Popen(
        [sys.executable, "server.py"], cwd=str(ROOT), env=env,
        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.time() + 40
        import urllib.request
        while time.time() < deadline:
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/" % port, timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        yield
    finally:
        # uvicorn's reloader leaves the worker holding the socket if only the
        # parent is killed, so kill the tree.
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True)
        else:
            proc.terminate()
        proc.wait(timeout=20)
        log.close()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _visible_text(page) -> str:
    return page.inner_text("body")


def _key_namespaces(path: str) -> set[str]:
    """First segments of every key this page registers or asks for.

    Dotted tokens on screen are not all leaked keys: the pages show filenames,
    and they show Abaqus API snippets like `mdb.models.keys` in seeded example
    prompts. Asking "does this token start with a namespace this page's
    catalogue actually uses" separates the two without a hand-kept list of
    exceptions, and unlike matching whole keys it still catches a key built at
    runtime as t('grade.' + verdict).
    """
    rel = PAGE_SOURCE[path]
    text = "\n".join((ROOT / src).read_text(encoding="utf-8")
                     for src in static.PAGES[rel])
    keys = set(static._extract_catalogue(text, rel, []).get("zh", {}))
    keys |= static._referenced_keys(text)
    return {k.split(".")[0] for k in keys if "." in k}


def _leaked_keys(text: str, namespaces: set[str]) -> list[str]:
    """Raw catalogue keys sitting on screen."""
    return [k for k in sorted(set(RAW_KEY.findall(text)))
            if k.split(".")[0] in namespaces
            # A file can be named after a namespace too (results.json).
            and not k.endswith((".py", ".inp", ".odb", ".json", ".yaml", ".yml",
                                ".md", ".sta", ".msg", ".dat", ".cae", ".log",
                                ".frd", ".lck", ".html", ".css", ".js"))]


def _check_page(browser, base: str, path: str, fails: Failures) -> None:
    url = base + path
    label = path
    namespaces = _key_namespaces(path)

    # -- 1. the browser's own language decides the default ------------------
    for locale, expected in (("zh-CN", "zh"), ("en-US", "en")):
        ctx = browser.new_context(locale=locale)
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_function("() => window.I18N && I18N.lang", timeout=15000)
        got = page.evaluate("() => I18N.lang")
        if got != expected:
            fails.add(label, "browser locale %s gave I18N.lang=%r, expected %r"
                             % (locale, got, expected))
        else:
            fails.ok(label, "locale %s -> %s" % (locale, expected))
        ctx.close()

    ctx = browser.new_context(locale="zh-CN")
    page = ctx.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_function("() => window.I18N && I18N.lang === 'zh'", timeout=15000)

    # -- 2. runtime content survives a language switch ----------------------
    # Targeted rather than a blanket sweep: for an ordinary label, being
    # re-stamped on a language switch is exactly right. The nodes below are the
    # ones where it is wrong, because what they hold is not translatable copy —
    # a solve report, or a button's live in-flight state.
    probes = PROBES.get(path, [])
    planted = page.evaluate(
        """(probes) => {
             const out = [];
             for (const p of probes) {
               const el = document.querySelector(p.selector);
               if (!el) { out.push({...p, missing: true}); continue; }
               el.textContent = p.stamp;
               if (p.disable) el.disabled = true;
               out.push({...p, missing: false});
             }
             return out;
           }""", probes)
    for probe in planted:
        if probe["missing"]:
            fails.add(label, "probe selector %s matched nothing -- the check has "
                             "gone stale" % probe["selector"])

    page.click("#btn-lang")
    page.wait_for_function("() => I18N.lang === 'en'", timeout=10000)

    for probe in planted:
        if probe["missing"]:
            continue
        after = page.evaluate("(sel) => document.querySelector(sel).textContent",
                              probe["selector"])
        if after != probe["stamp"]:
            fails.add(label, "%s: %s (was %r, now %r)"
                             % (probe["selector"], probe["why"],
                                probe["stamp"], after[:60]))
        else:
            fails.ok(label, "%s kept its runtime content" % probe["selector"])

    # -- 3. the switch actually switched ------------------------------------
    lang_attr = page.evaluate("() => document.documentElement.lang")
    if not lang_attr.startswith("en"):
        fails.add(label, "documentElement.lang is %r after switching to English"
                         % lang_attr)
    else:
        fails.ok(label, "documentElement.lang -> %s" % lang_attr)

    # -- 4. nothing is missing from the English catalogue -------------------
    page.evaluate("() => I18N.resetMissing()")
    page.evaluate("() => I18N.apply()")
    missing = page.evaluate("() => I18N.missingKeys()")
    if missing:
        fails.add(label, "%d key(s) have no English: %s"
                         % (len(missing), missing[:8]))
    else:
        fails.ok(label, "no missing English keys")

    # -- 5. no raw keys on screen ------------------------------------------
    text = _visible_text(page)
    leaked = _leaked_keys(text, namespaces)
    if leaked:
        fails.add(label, "raw i18n key(s) visible on screen: %s" % leaked[:6])
    else:
        fails.ok(label, "no raw keys on screen")

    # -- 5b. a refusal reads in the chosen language ------------------------
    # The reason a translated UI exists at all is the visitor with no Abaqus
    # licence, and the first thing that visitor meets is a CalculiX refusal.
    # Those sentences come from the backend catalogue, so they are the easiest
    # thing to leave in Chinese behind a fully translated frame.
    if path == "/workbench":
        try:
            # The catalogue arrives over the network after the switch.
            page.wait_for_function(
                "() => I18N.t('ccx.load.pressure') !== 'ccx.load.pressure'",
                timeout=10000)
        except Exception:
            fails.add(label, "the backend message catalogue never arrived "
                             "(GET /api/i18n/messages)")
        rendered = page.evaluate(
            """() => limitationText({
                 reason_key: 'ccx.load.pressure',
                 suffix_key: 'ccx.howto',
                 reason_params: {env: 'ABAQUS_AGENT_ABAQUS_CMD'},
                 reason: '压力载荷需要把 Abaqus 的面名转成 ccx 的单元面编号，尚未验证'
               })""")
        if CJK.search(rendered) or "Pressure loads" not in rendered:
            fails.add(label, "a CalculiX refusal still renders in Chinese with the "
                             "UI in English: %r" % rendered[:90])
        else:
            fails.ok(label, "backend refusals render in English")

    # -- 6. the choice is remembered ---------------------------------------
    # goto rather than reload: the workbench holds an open SSE stream, and
    # Chromium will not report a reload as navigated while one is live.
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_function("() => window.I18N && I18N.lang", timeout=15000)
    if page.evaluate("() => I18N.lang") != "en":
        fails.add(label, "language choice was not remembered across a reload")
    else:
        fails.ok(label, "choice survived a reload")

    ctx.close()

    # -- 7. the page survives losing the engine ----------------------------
    ctx = browser.new_context(locale="zh-CN")
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    # A clean 404 rather than route.abort(): it is what a packaging slip or a
    # reverse proxy actually produces, and an aborted blocking <script> leaves
    # Chromium waiting on the load event forever.
    page.route("**/static/i18n.js",
               lambda route: route.fulfill(status=404, body="",
                                           content_type="application/javascript"))
    # "commit" then poll readyState: with a route handler installed, Chromium
    # does not always surface the domcontentloaded lifecycle event to
    # Playwright, and waiting on it hangs for the full timeout on a page that
    # in fact loaded fine.
    page.goto(url, wait_until="commit", timeout=30000)
    page.wait_for_function("() => document.readyState === 'complete'", timeout=30000)
    page.wait_for_timeout(400)
    if errors:
        fails.add(label, "page threw with /static/i18n.js blocked: %s" % errors[:2])
    else:
        degraded_text = _visible_text(page)
        # "Still shows Chinese" is too weak to mean anything: the page also
        # pulls server-composed Chinese from /api/i18n/messages, so it stayed
        # green for months while the stand-in's register() *replaced* the
        # catalogue on that second call and every label read as its raw key.
        # Ask the question that actually distinguishes the two.
        degraded_leaked = _leaked_keys(degraded_text, namespaces)
        if not CJK.search(degraded_text):
            fails.add(label, "with the engine blocked the page shows no Chinese "
                             "at all -- the stand-in is not applying the catalogue")
        elif degraded_leaked:
            fails.add(label, "with the engine blocked, %d label(s) render as raw "
                             "keys: %s" % (len(degraded_leaked), degraded_leaked[:6]))
        else:
            fails.ok(label, "survives a missing /static/i18n.js, still translated")
    ctx.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    # No default port when this starts its own server: binding a fixed one
    # either collides with a server already running, or -- worse -- silently
    # checks that other server, which may be a different build.
    ap.add_argument("--port", type=int, default=None)
    # Serving is the default because scripts/run_all_real_checks.py runs every
    # gate as `python <script>` with no arguments: a gate that needs a flag to
    # work is a gate that reports FAIL in the harness while passing by hand.
    ap.add_argument("--serve", action=argparse.BooleanOptionalAction,
                    default=True,
                    help="start and stop a server around the run "
                         "(--no-serve to use one already on --port)")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    port = args.port
    if port is None:
        port = _free_port() if args.serve else 8000
    base = "http://127.0.0.1:%d" % port
    fails = Failures()

    def run() -> None:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                for path in PAGES:
                    print("\n== %s ==" % path)
                    _check_page(browser, base, path, fails)
            finally:
                browser.close()

    if args.serve:
        with _server(port):
            run()
    else:
        run()

    if fails:
        print("\nRESULT: FAIL (%d)" % len(fails))
    else:
        print("\nRESULT: PASS")
    # The verdict scripts/run_all_real_checks.py reads. It has to be the last
    # parseable JSON object on stdout.
    print(json.dumps({"schema": "i18n_ui_check/1",
                      "result": "FAIL" if fails else "PASS",
                      "pages": list(PAGES), "failures": list(fails)},
                     ensure_ascii=False))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
