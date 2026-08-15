"""Browser-level proof that @-mentions work end to end — and refuse honestly.

The feature (#77): selection-as-context. A tree row exposes an @ button;
clicking it attaches a chip to the composer, inserts @Name into the text, and
the send carries the selection to the server, where it resolves to the spec
fragment the row was drawn from. The failure this exists to prevent is a
mention that LOOKS attached and never reaches the model — a chip is one DOM
node away from being decoration.

Items:
  1. rows with a spec path offer the @; the chip and the composer text appear
  2. a sent message carries the mention: the transcript bubble keeps the chip,
     the reply acknowledges the selection, and the chips clear for the next
     message
  3. a mention the spec cannot resolve is REFUSED on send — error toast, chips
     kept so the user can fix them, and NOTHING appended to the transcript
  4. the tree keeps working after all of it (no page errors anywhere)

Usage (needs playwright chromium):
  .venv\\Scripts\\python.exe scripts\\run_mention_ui_check.py
Exit 0 = every item passed, or Chromium is absent and the gate skipped itself.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 8139
BASE = "http://127.0.0.1:%d" % PORT
OUT_DIR = ROOT / "artifacts" / "mention_ui_check"

SPEC_YAML = """\
meta:
  abaqus_release: '2021'
  model_name: TwoPlates
  units: mm_MPa_t
  description: two plates tied face to face
  missing_questions: []
material:
  name: Steel
  E: 210000.0
  nu: 0.3
parts:
- name: Lower
  features:
  - op: sketch
    id: o
    plane: XY
    profile:
      rect:
        corner1: [0.0, 0.0]
        corner2: [100.0, 50.0]
  - op: extrude
    sketch: o
    depth: 10.0
  section:
    type: solid
    material: Steel
  mesh:
    seed: 5.0
    element: C3D8I
- name: Upper
  features:
  - op: sketch
    id: o
    plane: XY
    profile:
      rect:
        corner1: [0.0, 0.0]
        corner2: [100.0, 50.0]
  - op: extrude
    sketch: o
    depth: 10.0
  section:
    type: solid
    material: Steel
  mesh:
    seed: 5.0
    element: C3D8I
assembly:
  instances:
  - name: L
    part: Lower
    translate: [0.0, 0.0, 0.0]
  - name: U
    part: Upper
    translate: [0.0, 0.0, 10.0]
interactions:
- name: Bond
  type: tie
  main: L:face@z=max
  secondary: U:face@z=min
steps:
- name: Press
  type: Static
  bcs:
  - name: Fix
    region: L:face@z=min
    type: encastre
  loads:
  - name: Top
    region: U:face@z=max
    type: pressure
    value: 1.0
outputs:
  kpis:
  - name: U_MAX
    type: field_max
    location: whole_model
    component: U3
"""

BOOTSTRAP = r'''
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, r"{root}")
out = Path(r"{out}")
sess_dir = out / "sessions"
sess_dir.mkdir(parents=True, exist_ok=True)
os.environ["ABAQUS_AGENT_WORKBENCH_SESSION_DIR"] = str(sess_dir)

import server

now = time.time()
session = {{
    "session_id": "wb-mention", "title": "mention check",
    "created_at": now, "updated_at": now,
    "messages": [], "current_spec_yaml": {spec_yaml!r}, "pending": None,
    "runs": [],
}}
(sess_dir / "wb-mention.json").write_text(
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
    try:
        from playwright.sync_api import Error as PWError
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(json.dumps({"overall": "skipped",
                          "reason": "playwright is not installed"}))
        return 0

    started = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    boot_path = OUT_DIR / "_bootstrap.py"
    boot_path.write_text(
        BOOTSTRAP.format(root=str(ROOT), out=str(OUT_DIR), port=PORT,
                         spec_yaml=SPEC_YAML),
        encoding="utf-8")

    log = open(OUT_DIR / "server.log", "w", encoding="utf-8")  # noqa: SIM115
    proc = subprocess.Popen(
        [sys.executable, str(boot_path)], cwd=str(ROOT),
        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
    )
    items: list[dict] = []

    def add(item_id: str, ok: bool, note: str, **extra) -> None:
        row = {"id": item_id, "status": "pass" if ok else "fail", "note": note}
        row.update(extra)
        items.append(row)

    try:
        wait_health()
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
            page.goto("%s/workbench?session=wb-mention" % BASE,
                      wait_until="networkidle")
            page.wait_for_selector(".tree-row.clickable", timeout=20_000)

            # 1. The @ affordance, the chip, and the composer text.
            at_count = page.locator(".tree-at").count()
            # Hover first: the @ is display:none until the row is hovered, and
            # that is exactly how a user reaches it, so the gate does the same
            # rather than forcing a click through a hidden element.
            page.hover('.tree-row[data-row="part:Upper"]')
            page.locator('.tree-row[data-row="part:Upper"] .tree-at').click()
            page.wait_for_timeout(200)
            state1 = page.evaluate(
                """() => ({
                    chips: [...document.querySelectorAll('#chat-refs .chat-ref')]
                        .map(e => e.textContent),
                    composer: document.getElementById('chat-input').value,
                    held: document.querySelectorAll('.tree-at.held').length,
                })""")
            add("1_at_click_attaches_chip_and_composer_text",
                at_count > 0
                and any("@Upper" in c for c in state1["chips"])
                and "@Upper" in state1["composer"]
                and state1["held"] == 1,
                "%d rows offer @; after clicking part:Upper — chips=%s, "
                "composer=%r, held-marks=%d"
                % (at_count, state1["chips"], state1["composer"], state1["held"]))
            page.screenshot(path=str(OUT_DIR / "1_chip_attached.png"))

            # 2. Send with the template backend; the mention must survive into
            #    the transcript and be acknowledged, and the chips must clear.
            page.select_option("#backend-select", "template")
            page.fill("#chat-input", "@Upper 这块板加厚到 20")
            page.click("#btn-send")
            page.wait_for_selector(".msg.assistant .bubble", timeout=60_000)
            page.wait_for_timeout(400)
            state2 = page.evaluate(
                """() => {
                    const users = [...document.querySelectorAll('.msg.user')];
                    const last = users[users.length - 1];
                    const asst = [...document.querySelectorAll('.msg.assistant .bubble')];
                    return {
                        bubbleRefs: last
                            ? [...last.querySelectorAll('.bubble-refs .chat-ref')]
                                .map(e => e.textContent)
                            : [],
                        reply: asst.length ? asst[asst.length - 1].innerText : '',
                        chipsLeft: document.querySelectorAll('#chat-refs .chat-ref').length,
                    };
                }""")
            add("2_send_carries_the_mention_and_clears_the_chips",
                any("@Upper" in c for c in state2["bubbleRefs"])
                and "模板引擎" in state2["reply"]
                and state2["chipsLeft"] == 0,
                "transcript chip=%s; reply acknowledges=%r…; chips left=%d"
                % (state2["bubbleRefs"], state2["reply"][:80],
                   state2["chipsLeft"]))
            page.screenshot(path=str(OUT_DIR / "2_sent_with_mention.png"))

            # 3. A dangling mention refuses on send: toast, chips kept, and the
            #    transcript untouched. Injected through the same state the UI
            #    uses, because no click can produce a ghost row.
            before = page.evaluate(
                "() => document.querySelectorAll('.msg').length")
            page.evaluate(
                """() => {
                    state.chatRefs = [{ref: 'part:Ghost', label: 'Ghost'}];
                    renderChatRefs();
                }""")
            page.fill("#chat-input", "@Ghost 改一下")
            page.click("#btn-send")
            page.wait_for_selector(".toast.error", timeout=30_000)
            page.wait_for_timeout(400)
            state3 = page.evaluate(
                """() => ({
                    toast: [...document.querySelectorAll('.toast.error')]
                        .map(e => e.textContent).join(' | '),
                    chips: document.querySelectorAll('#chat-refs .chat-ref').length,
                    msgs: document.querySelectorAll('.msg').length,
                })""")
            add("3_a_dangling_mention_is_refused_and_chips_stay",
                "part:Ghost" in state3["toast"]
                and state3["chips"] == 1
                and state3["msgs"] == before,
                "toast=%r; chips kept=%d; transcript %d -> %d messages"
                % (state3["toast"][:120], state3["chips"], before,
                   state3["msgs"]))
            page.screenshot(path=str(OUT_DIR / "3_dangling_refused.png"))

            add("4_no_page_errors", not errors,
                "pageerror count=%d %s" % (len(errors), errors[:2]))
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()

    failed = [i for i in items if i["status"] != "pass"]
    payload = {"schema": "gate/1",
               "overall": "fail" if failed else "pass",
               "items": items,
               "seconds": round(time.time() - started, 1)}
    (OUT_DIR / "report.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    for item in items:
        print("[%-4s] %s — %s" % (item["status"], item["id"],
                                  str(item["note"])[:160]))
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
