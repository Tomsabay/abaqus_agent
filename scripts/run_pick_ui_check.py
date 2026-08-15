"""Browser check: clicking a body in the 3D preview mentions it; dragging does not.

Real Chromium, real pointer events on the canvas, assertions on what the pick
handler was HANDED rather than on pixels. The failure this exists to prevent
is a click that looks like selection and never reaches the chat — or its dual,
an orbit-drag that fires a pick every time the user lets go of the mouse.

Two halves, same split as run_contact_preview_ui_check.py:

  viewport — a synthetic two-square assembly in a bare page. The camera looks
  at the bbox centre from +x+y+z, so a click at the canvas centre must hit the
  UPPER square (z=1): the ray reaches the z=1 plane before the z=0 one from
  that side, at x≈0.91 y≈0.82 — inside the unit square. That geometry is what
  makes the items deterministic instead of "click and hope".
    1. a left click at the centre picks Upper, and the hit point sits on z=1
    2. a click on empty background picks nothing
    3. a dimmed body stays pickable (emphasis is display, not a hit mask)
    4. a right click picks nothing (right is pan)
    5. a drag longer than the travel threshold picks nothing (drag = orbit;
       run LAST because it really does orbit the camera)

  workbench — the real /workbench page.
    6. createPreviewViewport() wires onPick to viewportPickPart, so a preview
       viewport is never created without the handler (both stream sites share
       that constructor)
    7. viewportPickPart lands a chip + composer text via the SAME addChatRef
       the tree @ uses, and a second pick removes it (toggle, like the tree)
    8. a key with no tree row toasts instead of doing nothing

  face mode (#79) — same real page.
    9. a hit triangle resolves to its pick_face and the chip carries a
       selector GENERATED from the measured bbox — `U:face@box=…` with the
       exact numbers CAE reported, never a face index
   10. the note carries the hit count and, on a cylindrical face, the measured
       radius; two faces whose boxes nest produce `faces@box=` (plural) and a
       count of 2, because a singular selector would assert exactly one and
       stop the build
   11. a triangle no pick_face claims toasts instead of guessing
   12. a selector chip survives the REAL chat round trip: send lands 200, the
       transcript bubble keeps the chip; a selector the build parser refuses
       is a 400 naming it, chips kept

Run:  .venv\\Scripts\\python.exe scripts\\run_pick_ui_check.py --serve
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
sys.path.insert(0, str(ROOT))


@contextlib.contextmanager
def _server(port: int):
    env = {**os.environ, "ABAQUS_AGENT_PORT": str(port),
           "ABAQUS_AGENT_HOST": "127.0.0.1"}
    log_path = Path(tempfile.gettempdir()) / ("pick_ui_check_%d.log" % port)
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
        with contextlib.suppress(Exception):
            proc.wait(timeout=10)
        log.close()


_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<style>body{margin:0}#vp{width:400px;height:300px}</style>
<script src="%(base)s/static/vendor/three.min.js"></script>
<script src="%(base)s/static/vendor/OrbitControls.js"></script>
<script src="%(base)s/static/workbench_viewport.js"></script>
</head><body><div id="vp"></div></body></html>"""

_FIXTURE = """
(() => {
  const square = (z) => ({
    family: 'surface',
    nodes: [0, 0, z, 1, 0, z, 1, 1, z, 0, 1, z],
    tris: [0, 1, 2, 0, 2, 3],
    node_count: 4, tri_count: 2,
  });
  const vp = WBViewport.createStreaming(
    document.getElementById('vp'), { bbox: [[0, 0, 0], [1, 1, 1]], part_count: 2 });
  vp.addPart(Object.assign(square(0), { name: 'LOWER', instance: 'Lower' }), 0);
  vp.addPart(Object.assign(square(1), { name: 'UPPER', instance: 'Upper' }), 1);
  window.__picked = [];
  vp.onPick = (key, info) => window.__picked.push(
    { key, z: info && info.point ? info.point[2] : null });
  window.__vp = vp;
  return { keys: vp.partKeys(), hasOnPick: 'onPick' in vp };
})()
"""


class Items:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.rows.append({"name": name, "status": "pass" if ok else "fail",
                          "detail": detail})
        print("  %-4s  %-36s %s" % ("PASS" if ok else "FAIL", name, detail))

    def failed(self) -> int:
        return sum(1 for r in self.rows if r["status"] != "pass")


def _viewport_items(browser, base: str, items: Items) -> None:
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.set_content(_PAGE % {"base": base})
    page.wait_for_function("typeof THREE !== 'undefined' && !!window.WBViewport")

    built = page.evaluate(_FIXTURE)
    if built["keys"] != ["Lower", "Upper"] or not built["hasOnPick"]:
        items.add("assembly_builds", False,
                  "partKeys()=%r hasOnPick=%s -- nothing below can run"
                  % (built["keys"], built["hasOnPick"]))
        page.close()
        return
    items.add("assembly_builds", True, "two squares, onPick slot present")

    box = page.locator("#vp canvas").bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2

    def picked():
        return page.evaluate("() => window.__picked")

    def clear():
        page.evaluate("() => { window.__picked = []; }")

    # 1. A left click at the centre. The ray from the +x+y+z camera reaches the
    #    z=1 square first (at x≈0.91, y≈0.82) — see the module docstring.
    page.mouse.click(cx, cy)
    page.wait_for_timeout(100)
    got = picked()
    on_top = (len(got) == 1 and got[0]["key"] == "Upper"
              and got[0]["z"] is not None and abs(got[0]["z"] - 1.0) < 1e-6)
    items.add("click_picks_the_body_under_it", on_top,
              "picked=%r (want one hit, key Upper, on the z=1 plane)" % (got,))
    clear()

    # 2. Empty background: the model projects centre-right from this camera,
    #    so the top-left corner of the canvas misses it.
    page.mouse.click(box["x"] + 4, box["y"] + 4)
    page.wait_for_timeout(100)
    got = picked()
    items.add("background_click_picks_nothing", got == [],
              "picked=%r" % (got,))
    clear()

    # 3. Dim Upper via emphasis, click it anyway. Emphasis is display; a body
    #    the user can still see (12% opacity) must still answer a click, or
    #    selection could never MOVE off the emphasised part.
    page.evaluate("() => window.__vp.emphasize(['Lower'])")
    page.mouse.click(cx, cy)
    page.wait_for_timeout(100)
    got = picked()
    items.add("dimmed_body_stays_pickable",
              len(got) == 1 and got[0]["key"] == "Upper",
              "picked=%r with Upper dimmed to 12%%" % (got,))
    page.evaluate("() => window.__vp.clearEmphasis()")
    clear()

    # 4. Right button is pan, not pick.
    page.mouse.click(cx, cy, button="right")
    page.wait_for_timeout(100)
    got = picked()
    items.add("right_click_picks_nothing", got == [], "picked=%r" % (got,))
    clear()

    # 5. A drag. 60px of travel is an orbit by any definition; it also really
    #    does orbit the camera, which is why this item runs last.
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + 60, cy, steps=6)
    page.mouse.up()
    page.wait_for_timeout(100)
    got = picked()
    items.add("drag_picks_nothing", got == [],
              "picked=%r after a 60px left-drag" % (got,))

    items.add("no_page_errors", not errors,
              "; ".join(errors[:3]) if errors else "none")
    page.close()


# One instance row with a spec path, shaped like build_tree ships it. Seeded
# directly because the pick handler is a pure page function; driving it through
# a real preview stream would demand a solver run this gate must not need.
_WB_FIXTURE = """
(() => {
  state.tree = { spec_ok: true, tree: { dialect: 'v2', unknown_keys: [], groups: [
    { id: 'assembly', label: '装配', count: 1, rows: [
      { id: 'inst:U', kind: 'instance', label: 'U', detail: 'Upper',
        instance: 'U', part: 'Upper', path: 'assembly.instances[0]',
        facts: [], children: [] },
    ] },
  ] } };
  state.chatRefs = [];
  viewportPickPart('U');
  const after1 = {
    refs: state.chatRefs.map(r => r.ref),
    chips: [...document.querySelectorAll('#chat-refs .chat-ref')].map(e => e.textContent),
    composer: document.getElementById('chat-input').value,
  };
  viewportPickPart('U');
  const after2 = { refs: state.chatRefs.map(r => r.ref) };
  viewportPickPart('Ghost');
  const after3 = {
    refs: state.chatRefs.map(r => r.ref),
    toasts: [...document.querySelectorAll('.toast')].map(e => e.textContent),
  };
  return { after1, after2, after3 };
})()
"""


def _workbench_items(browser, base: str, items: Items) -> None:
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base + "/workbench", wait_until="load")
    try:
        page.wait_for_function(
            "typeof viewportPickPart === 'function' "
            "&& typeof createPreviewViewport === 'function'", timeout=10_000)
    except Exception:
        items.add("page_exposes_the_pick_handler", False,
                  "viewportPickPart/createPreviewViewport not on /workbench")
        page.close()
        return
    items.add("page_exposes_the_pick_handler", True, "both present")

    wired = page.evaluate("""() => {
      const vp = createPreviewViewport(document.createElement('div'),
                                       { bbox: [[0,0,0],[1,1,1]], part_count: 0 });
      const ok = vp.onPick === viewportPickPart;
      vp.dispose();
      return ok;
    }""")
    items.add("preview_constructor_wires_the_handler", bool(wired),
              "createPreviewViewport().onPick === viewportPickPart: %s" % wired)

    got = page.evaluate(_WB_FIXTURE)
    a1, a2, a3 = got["after1"], got["after2"], got["after3"]
    items.add("pick_lands_a_chip_via_addChatRef",
              a1["refs"] == ["inst:U"]
              and any("@U" in c for c in a1["chips"])
              and "@U" in a1["composer"],
              "refs=%r chips=%r composer=%r" % (a1["refs"], a1["chips"],
                                                a1["composer"]))
    items.add("second_pick_removes_the_chip", a2["refs"] == [],
              "refs after the second pick=%r" % (a2["refs"],))
    ghost_toast = [t for t in a3["toasts"] if "Ghost" in t]
    items.add("unknown_key_toasts_instead_of_silence",
              a3["refs"] == [] and len(ghost_toast) == 1,
              "refs=%r ghost toasts=%r" % (a3["refs"], ghost_toast))

    _face_mode_items(page, items)

    items.add("no_page_errors_on_workbench", not errors,
              "; ".join(errors[:3]) if errors else "none")
    page.close()


# Two faces of a fake instance P on backend part 0: the big flat top (its box
# CONTAINS the small one, so picking the small face must count 2 and go
# plural) and a small cylindrical boss carrying a measured radius.
_FACE_FIXTURE = """
(() => {
  state.previewAssembly = { pick_faces: [
    { instance: 'P', face: 2, bbox: [[0, 0, 10], [100, 50, 10]],
      normal: [0, 0, 1], area: 5000, node_count: 121, capped: false,
      parts: [{ part: 0, tris: [4, 5] }] },
    { instance: 'P', face: 7, bbox: [[40, 20, 10], [60, 30, 10]],
      radius: 5.5, area: 172.8, node_count: 40, capped: false,
      parts: [{ part: 0, tris: [9] }] },
  ] };
  state.chatRefs = [];
  state.pickMode = 'face';
  const out = {};
  viewportPickPart('P', { partIndex: 0, faceIndex: 4 });
  out.flat = state.chatRefs.map(r => ({ sel: r.selector, note: r.note,
                                        label: r.label }));
  viewportPickPart('P', { partIndex: 0, faceIndex: 4 });
  out.afterToggle = state.chatRefs.length;
  viewportPickPart('P', { partIndex: 0, faceIndex: 9 });
  out.boss = state.chatRefs.map(r => ({ sel: r.selector, note: r.note }));
  state.chatRefs = [];
  viewportPickPart('P', { partIndex: 0, faceIndex: 77 });
  out.miss = { refs: state.chatRefs.length,
               toasts: [...document.querySelectorAll('.toast')]
                 .map(e => e.textContent) };
  state.pickMode = 'part';
  return out;
})()
"""


def _face_mode_items(page, items: Items) -> None:
    got = page.evaluate(_FACE_FIXTURE)

    # Box semantics run in ONE direction: a candidate matches when its box
    # fits inside the QUERY box. The big flat face's box contains the boss's,
    # so picking the big face honestly catches 2 and must go plural — while
    # picking the small boss catches only itself and stays singular.
    flat = got["flat"][0] if got["flat"] else {}
    items.add("face_pick_generates_the_measured_selector",
              flat.get("sel") == "P:faces@box=0,0,10,100,50,10"
              and flat.get("label") == "P:face#2"
              and "2 个面" in flat.get("note", ""),
              "big face's box contains the boss's -> plural + count 2; "
              "chip=%r" % (flat,))
    items.add("second_face_pick_toggles_off", got["afterToggle"] == 0,
              "chips after picking the same face twice: %d"
              % got["afterToggle"])

    boss = got["boss"][0] if got["boss"] else {}
    items.add("small_face_stays_singular_and_carries_the_radius",
              boss.get("sel") == "P:face@box=40,20,10,60,30,10"
              and "1 个面" in boss.get("note", "")
              and "5.5" in boss.get("note", ""),
              "chip=%r" % (boss,))
    items.add("unclaimed_triangle_toasts_instead_of_guessing",
              got["miss"]["refs"] == 0
              and any("几何面" in t for t in got["miss"]["toasts"]),
              "refs=%d toasts=%r" % (got["miss"]["refs"],
                                     got["miss"]["toasts"][-2:]))


def _chat_round_trip_items(browser, base: str, items: Items) -> None:
    """A selector chip through the REAL chat endpoint, template backend."""
    import urllib.request

    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    req = urllib.request.Request(
        base + "/api/workbench/sessions", method="POST",
        data=json.dumps({}).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        sid = json.loads(resp.read())["session_id"]

    page.goto("%s/workbench?session=%s" % (base, sid), wait_until="networkidle")
    page.wait_for_selector("#chat-input", timeout=20_000)
    page.select_option("#backend-select", "template")

    # First message: the template engine writes a spec, so the session HAS one
    # for the second message's mention to resolve against.
    page.fill("#chat-input", "一块 100x50x10 的钢板，固定一端，压另一端")
    page.click("#btn-send")
    page.wait_for_selector(".msg.assistant .bubble", timeout=60_000)

    good = {"kind": "selector", "selector": "P:face@box=0,0,10,100,50,10",
            "label": "P:face#2", "note": "包围盒实测自 CAE 预览"}
    page.evaluate(
        "(chip) => { state.chatRefs = [chip]; renderChatRefs(); }", good)
    page.fill("#chat-input", "@P:face#2 在这个面上加载荷")
    before = page.evaluate("() => document.querySelectorAll('.msg').length")
    page.click("#btn-send")
    page.wait_for_function(
        "n => document.querySelectorAll('.msg').length >= n + 2", arg=before,
        timeout=60_000)
    sent = page.evaluate("""() => {
      const users = [...document.querySelectorAll('.msg.user')];
      const last = users[users.length - 1];
      return {
        bubbleRefs: last ? [...last.querySelectorAll('.bubble-refs .chat-ref')]
          .map(e => e.textContent) : [],
        chips: document.querySelectorAll('#chat-refs .chat-ref').length,
      };
    }""")
    items.add("selector_chip_survives_the_real_send",
              any("P:face#2" in c for c in sent["bubbleRefs"])
              and sent["chips"] == 0,
              "transcript refs=%r chips left=%d"
              % (sent["bubbleRefs"], sent["chips"]))

    bad = {"kind": "selector", "selector": "P:face@box=1,2,3",
           "label": "P:face#9", "note": ""}
    page.evaluate(
        "(chip) => { state.chatRefs = [chip]; renderChatRefs(); }", bad)
    page.fill("#chat-input", "@P:face#9 改这里")
    page.click("#btn-send")
    page.wait_for_selector(".toast.error", timeout=30_000)
    refused = page.evaluate("""() => ({
      toast: [...document.querySelectorAll('.toast.error')]
        .map(e => e.textContent).join(' | '),
      chips: document.querySelectorAll('#chat-refs .chat-ref').length,
    })""")
    items.add("a_selector_the_build_would_refuse_is_a_400_naming_it",
              "box" in refused["toast"] and refused["chips"] == 1,
              "toast=%r chips kept=%d"
              % (refused["toast"][:120], refused["chips"]))

    items.add("no_page_errors_on_the_round_trip", not errors,
              "; ".join(errors[:3]) if errors else "none")
    page.close()


def _answers(port: int) -> bool:
    import urllib.request
    try:
        urllib.request.urlopen("http://127.0.0.1:%d/" % port, timeout=2)
        return True
    except Exception:
        return False


def _skip(reason: str) -> int:
    """No browser here is not a failing check (SKIPPED counts as passing in
    run_all_real_checks.py; what it must never do is report PASS)."""
    print("SKIPPED: %s" % reason)
    print(json.dumps({"overall": "skipped", "reason": reason, "items": []},
                     ensure_ascii=False))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8141)
    ap.add_argument("--serve", action="store_true",
                    help="start a server even if one already answers")
    ap.add_argument("--no-serve", action="store_true",
                    help="fail rather than start one")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _skip("playwright is not installed")

    base = "http://127.0.0.1:%d" % args.port
    items = Items()

    def run() -> None:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                print("\n== viewport ==")
                _viewport_items(browser, base, items)
                print("\n== workbench ==")
                _workbench_items(browser, base, items)
                print("\n== chat round trip ==")
                _chat_round_trip_items(browser, base, items)
            finally:
                browser.close()

    already = _answers(args.port)
    try:
        if already and not args.serve:
            print("using the server already on :%d" % args.port)
            run()
        elif args.no_serve:
            return _skip("nothing answers on :%d and --no-serve was given"
                         % args.port)
        else:
            with _server(args.port):
                if not _answers(args.port):
                    return _skip("the server did not come up on :%d" % args.port)
                run()
    except Exception as exc:                     # chromium missing, WebGL off
        if "playwright" in repr(type(exc)).lower() and "executable" in str(exc).lower():
            return _skip("chromium is not installed for playwright")
        raise

    overall = "fail" if items.failed() else "pass"
    # Human line first, JSON LAST — run_all_real_checks.py parses from the
    # first `{` to the end of stdout.
    print("\nRESULT: %s (%d/%d)"
          % (overall.upper(), len(items.rows) - items.failed(), len(items.rows)))
    print(json.dumps({"overall": overall, "items": items.rows},
                     ensure_ascii=False))
    return 1 if items.failed() else 0


if __name__ == "__main__":
    sys.exit(main())
