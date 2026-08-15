"""Browser check: the two surfaces are one product, not two skins.

DOM assertions against the live server, because a screenshot cannot tell you
that two pages resolved the same token to the same value.

Pinned defects:
  * `/` and `/workbench` carried separate :root blocks that had drifted —
    different grounds (#09090E vs #141A21), different type stacks (Google-
    hosted JetBrains Mono + IBM Plex vs system Cascadia + Segoe UI Variable).
  * The two pages did not link to each other in either direction; "workbench"
    appeared zero times in index.html, so the product's main surface was
    unreachable from its own home page.
  * `/` fetched fonts from fonts.googleapis.com on every load — a leak, and a
    hard failure on the air-gapped workstations this is meant to run on.
  * The workbench at rest was a 1000px void of grid lines.

Run:  .venv\\Scripts\\python.exe scripts\\run_frontend_coherence_check.py
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Tokens that must resolve identically on both surfaces. If one page needs a
# different value, it needs a different token — not a different vocabulary.
SHARED_TOKENS = [
    "--bg0", "--bg1", "--bg2", "--bg3", "--bg4",
    "--bd", "--bd2", "--bd3",
    "--tx1", "--tx2", "--tx3",
    "--accent", "--accent2", "--blue", "--cyan", "--green", "--yellow", "--red",
    "--ramp", "--mono", "--sans", "--display",
    "--fs-base", "--fs-md", "--r-md", "--s4", "--t-base",
]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP: playwright not installed")
        return 0

    port = _free_port()
    base = "http://127.0.0.1:%d" % port
    proc = subprocess.Popen(
        [sys.executable, "server.py"], cwd=str(ROOT),
        env={**os.environ, "ABAQUS_AGENT_PORT": str(port)},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, text=True, errors="replace")

    failures: list[str] = []
    try:
        deadline = time.time() + 90
        while time.time() < deadline:
            try:
                urllib.request.urlopen(base + "/health", timeout=20).read()
                break
            except Exception:
                time.sleep(1)

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            tokens: dict[str, dict] = {}
            external: dict[str, list] = {}

            for name, path in (("index", "/"), ("workbench", "/workbench")):
                page = browser.new_page(viewport={"width": 1600, "height": 1000})
                hits: list[str] = []
                page.on("request", lambda r, h=hits: (
                    h.append(r.url)
                    if not r.url.startswith(("http://127.0.0.1", "data:", "blob:"))
                    else None))
                page.goto(base + path, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2500)
                tokens[name] = page.evaluate(
                    """ks => { const rs = getComputedStyle(document.documentElement);
                               return Object.fromEntries(
                                 ks.map(k => [k, rs.getPropertyValue(k).trim()])); }""",
                    SHARED_TOKENS)
                external[name] = hits
                if name == "index":
                    link = page.eval_on_selector_all(
                        "a[href='/workbench']", "els => els.length")
                    if not link:
                        failures.append("index has no link to /workbench")
                    solver = page.text_content("#sidebar-solver") or ""
                    if "求解器" not in solver:
                        failures.append("sidebar solver readout missing: %r" % solver)
                    # Rendered text, not source: the source carries a comment
                    # explaining why the badge was removed, and matching that
                    # would fail forever.
                    body_text = page.inner_text("body")
                    if "NO LICENSE REQ" in body_text:
                        failures.append("the removed licensing badge is back")
                else:
                    back = page.eval_on_selector_all(
                        "a[href='/']", "els => els.length")
                    if not back:
                        failures.append("workbench has no link back to /")
                    cards = page.eval_on_selector_all(
                        ".onboard-card", "els => els.length")
                    if cards < 3:
                        failures.append("onboarding starter cards missing (%d)" % cards)
                    # Every card must fit its own content — the global
                    # `button { height: 24px }` rule clipped the third line.
                    clipped = page.eval_on_selector_all(
                        ".onboard-card",
                        "els => els.filter(e => e.scrollHeight > e.clientHeight + 1).length")
                    if clipped:
                        failures.append("%d starter card(s) clip their content" % clipped)
                    # Clicking a card must actually seed the prompt.
                    page.eval_on_selector(".onboard-card", "e => e.click()")
                    seeded = page.eval_on_selector("#chat-input", "e => e.value")
                    if not seeded.strip():
                        failures.append("starter card did not seed the prompt")
                page.close()
            browser.close()

        for token in SHARED_TOKENS:
            a, b = tokens["index"].get(token), tokens["workbench"].get(token)
            if not a:
                failures.append("index does not define %s" % token)
            elif a != b:
                failures.append("%s differs: index=%r workbench=%r" % (token, a, b))

        for name, hits in external.items():
            if hits:
                failures.append("%s makes external requests: %s" % (name, hits[:4]))

        print(json.dumps({"shared_tokens_checked": len(SHARED_TOKENS),
                          "ground": tokens["index"].get("--bg1"),
                          "accent": tokens["index"].get("--accent"),
                          "external_requests": {k: len(v) for k, v in external.items()}},
                         ensure_ascii=False, indent=1))
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
    # parseable JSON object on stdout, and this gate prints one of its own
    # earlier in the run.
    print(json.dumps({"schema": "frontend_coherence_check/1",
                      "result": "FAIL" if failures else "PASS",
                      "failures": failures}, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
