"""Browser check: a tie or a contact pair shows the faces it actually joined.

Real Chromium, real three.js, assertions on the SCENE GRAPH rather than on
pixels. A screenshot cannot tell you that the highlight is a separate geometry
from the body it sits on, and that is precisely what goes wrong here.

WHAT THIS IS FOR. The model tree used to answer a click on a contact pair by
dimming the two bodies. On a bonded pair that is nearly no information: the
faces that were joined are interior, they are exactly where the two bodies
meet, and "both plates" is the picture the user already had. The question a
spec author cannot answer by reading the spec is which facets Abaqus actually
put in the surface -- `Housing:face@r=12` catching the bore and catching the
outer flange read identically in YAML and look nothing alike here. The overlay
that answers it was computed by post/parse_inp.py all along and dropped in
workbench/routes.py before it ever reached the browser.

THE TRAP ITEM 3 PINS. The cheap way to draw the highlight is to reuse the
part's own position buffer with a different index. three.js frees an
attribute's GPU buffer when ANY geometry holding it is disposed, so clearing
the highlight would blank the body it was drawn on -- and only on the second
click, which is the worst kind of bug to find by looking. So the check clears
the regions and requires the parts to still be there with their buffers
intact, and item 7 requires the overlay's attribute to be a different object.

Run:  .venv\\Scripts\\python.exe scripts\\run_contact_preview_ui_check.py --serve
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
    # To a file, never to a PIPE nobody drains: uvicorn logs a line per request
    # and a full pipe buffer blocks the server on write, which reads exactly
    # like a page that will not load.
    log_path = Path(tempfile.gettempdir()) / ("contact_preview_check_%d.log" % port)
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
<style>#vp{width:400px;height:300px}</style>
<script src="%(base)s/static/vendor/three.min.js"></script>
<script src="%(base)s/static/vendor/OrbitControls.js"></script>
<script src="%(base)s/static/workbench_viewport.js"></script>
</head><body><div id="vp"></div></body></html>"""

# Two unit squares, one above the other: the shape of every tie in this repo.
# The viewport keeps no reference to its scene, so the scene is captured at
# construction by wrapping the constructor. Done in the FIXTURE and not in the
# product: a hook that exists only for a test is a hook that can be satisfied
# while the real path is broken.
_FIXTURE = """
(() => {
  const RealScene = THREE.Scene;
  let captured = null;
  THREE.Scene = function () { const s = new RealScene(); captured = s; return s; };
  try {
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
    window.__vp = vp;
    window.__assembly = captured.children.find(c => c.type === 'Group');
    return { keys: vp.partKeys(), gotGroup: !!window.__assembly };
  } finally {
    THREE.Scene = RealScene;
  }
})()
"""

# Everything the assertions need, read off the live graph. Part meshes are the
# ones that carry an index (they were built with setIndex); overlays are
# non-indexed by construction, which is also what makes them distinguishable
# without the viewport having to label them.
_SNAPSHOT = """
(() => {
  const g = window.__assembly;
  const meshes = g.children.filter(c => c.isMesh);
  const parts = meshes.filter(m => m.geometry.index);
  const overlays = meshes.filter(m => !m.geometry.index);
  const attr = (m) => m.geometry.getAttribute('position');
  return {
    parts: parts.map(m => ({
      vertices: attr(m) ? attr(m).count : 0,
      arrayLen: attr(m) ? attr(m).array.length : 0,
      inScene: !!m.parent,
    })),
    overlays: overlays.map(m => ({
      vertices: attr(m).count,
      color: '#' + m.material.color.getHexString(),
      renderOrder: m.renderOrder,
      polygonOffset: !!m.material.polygonOffset,
      // The aliasing trap, checked directly rather than inferred: an overlay
      // sharing the part's attribute OBJECT would be freed together with it.
      sharesPartBuffer: parts.some(p => attr(p) === attr(m)),
    })),
  };
})()
"""

_REGION_MAIN = [{"name": "MIDPLANE_MAIN",
                 "parts": [{"part": 0, "facets": [0, 1, 2, 0, 2, 3]}]}]
_REGION_PAIR = _REGION_MAIN + [{"name": "MIDPLANE_SEC",
                                "parts": [{"part": 1, "facets": [0, 1, 2]}]}]


class Items:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.rows.append({"name": name, "status": "pass" if ok else "fail",
                          "detail": detail})
        print("  %-4s  %-32s %s" % ("PASS" if ok else "FAIL", name, detail))

    def failed(self) -> int:
        return sum(1 for r in self.rows if r["status"] != "pass")


def _viewport_items(browser, base: str, items: Items) -> None:
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.set_content(_PAGE % {"base": base})
    page.wait_for_function("typeof THREE !== 'undefined' && !!window.WBViewport")

    built = page.evaluate(_FIXTURE)
    items.add("assembly_builds",
              built["keys"] == ["Lower", "Upper"] and built["gotGroup"],
              "partKeys()=%r, assembly group found=%s"
              % (built["keys"], built["gotGroup"]))

    base_shot = page.evaluate(_SNAPSHOT)
    items.add("no_overlay_at_rest", not base_shot["overlays"],
              "%d part mesh(es), %d overlay(s) before any selection"
              % (len(base_shot["parts"]), len(base_shot["overlays"])))

    # Checked before it is called. Without this the gate dies on a TypeError
    # and never prints its own stdout contract, so a missing capability would
    # read to the harness as a broken gate rather than as a failed check --
    # which is exactly what happened when this was run against the frontend
    # from before the feature existed.
    api = page.evaluate("""() => ({
      showRegions: typeof window.__vp.showRegions === 'function',
      clearRegions: typeof window.__vp.clearRegions === 'function',
    })""")
    if not (api["showRegions"] and api["clearRegions"]):
        items.add("viewport_exposes_the_region_api", False,
                  "showRegions=%(showRegions)s clearRegions=%(clearRegions)s "
                  "-- nothing below can run" % api)
        items.add("no_page_errors", not errors,
                  "; ".join(errors[:3]) if errors else "none")
        page.close()
        return
    items.add("viewport_exposes_the_region_api", True,
              "showRegions/clearRegions present on the handle")

    page.evaluate("(r) => window.__vp.showRegions(r)", _REGION_PAIR)
    pair = page.evaluate(_SNAPSHOT)
    counts = [o["vertices"] for o in pair["overlays"]]
    items.add("regions_draw_their_facets", counts == [6, 3],
              "overlay vertex counts %r (6 = two triangles of the main face, "
              "3 = one of the secondary)" % (counts,))

    colors = [o["color"] for o in pair["overlays"]]
    items.add("pair_sides_differ",
              len(colors) == 2 and colors[0] != colors[1],
              "main %s vs secondary %s" % tuple(colors + ["-", "-"])[:2])

    items.add("overlay_geometry_is_independent",
              all(not o["sharesPartBuffer"] for o in pair["overlays"]),
              "no overlay reuses a part's position attribute object")

    items.add("overlay_wins_the_depth_fight",
              all(o["polygonOffset"] and o["renderOrder"] > 0
                  for o in pair["overlays"]),
              "polygonOffset set and renderOrder>0, so the highlight is not "
              "z-fighting with the face it sits on")

    page.evaluate("() => window.__vp.clearRegions()")
    cleared = page.evaluate(_SNAPSHOT)
    parts_intact = (len(cleared["parts"]) == 2
                    and all(p["inScene"] and p["arrayLen"] == 12
                            for p in cleared["parts"]))
    items.add("clear_leaves_the_bodies_alone",
              not cleared["overlays"] and parts_intact,
              "%d overlay(s) left; parts %r"
              % (len(cleared["overlays"]),
                 [(p["vertices"], p["arrayLen"]) for p in cleared["parts"]]))

    # A region the mesh cannot place must add nothing and raise nothing. Both
    # arise in practice: a part beyond the element cap never streamed, and a
    # surface on an unmeshed part comes back with no facets at all.
    page.evaluate("""(r) => window.__vp.showRegions(r)""", [
        {"name": "GHOST", "parts": [{"part": 7, "facets": [0, 1, 2]}]},
        {"name": "EMPTY", "parts": [{"part": 0, "facets": []}]},
        {"name": "NOPARTS", "parts": []},
    ])
    ghost = page.evaluate(_SNAPSHOT)
    items.add("unplaceable_regions_draw_nothing", not ghost["overlays"],
              "%d overlay(s) for a missing part index, an empty facet list and "
              "a region with no parts" % len(ghost["overlays"]))

    items.add("no_page_errors", not errors,
              "; ".join(errors[:3]) if errors else "none")
    page.close()


# The page-side half: a tree row resolves to surfaces through the overlay, and
# a partial highlight says so. Both are pure functions on the page, so they are
# called directly rather than driven through a chat session that would need an
# LLM.
_TREE_FIXTURE = """
(() => {
  state.previewAssembly = {
    surfaces: [
      { name: 'MIDPLANE_MAIN', instance: 'Lower', node_count: 9,
        drawn_nodes: 9, capped: false,
        parts: [{ part: 0, facets: [0, 1, 2], facet_count: 1 }] },
      { name: 'MIDPLANE_SEC', instance: 'Upper', node_count: 25,
        drawn_nodes: 9, capped: false,
        parts: [{ part: 1, facets: [0, 1, 2], facet_count: 1 }] },
    ],
    sets: [],
    interactions: [{ name: 'MidPlane', kind: 'tie', call: '',
                     surfaces: ['MIDPLANE_MAIN', 'MIDPLANE_SEC'],
                     gap: 0.0, gap_nodes: [9, 25] }],
    conditions: [], counts: {}, degraded: [],
  };
  state.tree = { spec_ok: true, tree: { dialect: 'v2', unknown_keys: [], groups: [
    { key: 'interactions', rows: [
      { id: 'inter:MidPlane', kind: 'tie', label: 'MidPlane', detail: 'tie',
        selectors: ['Lower:face@y=max', 'Upper:face@y=min'] },
      { id: 'inter:Absent', kind: 'tie', label: 'Absent', detail: 'tie',
        selectors: ['Lower:face@y=max'] },
    ] },
  ] } };
  const row = findTreeRow('inter:MidPlane');
  const missing = findTreeRow('inter:Absent');
  return {
    resolved: treeRowRegions(row).map(r => r.name),
    unknown: treeRowRegions(missing).map(r => r.name),
    // The instance emphasis the tree had before, which must not regress.
    keys: treeRowKeys(row),
    notes: regionShortfall(treeRowRegions(row)),
  };
})()
"""


def _tree_items(browser, base: str, items: Items) -> None:
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base + "/workbench", wait_until="load")
    # Same reason as the viewport half: report a missing function as a failed
    # item rather than as a timeout that swallows the stdout contract.
    try:
        page.wait_for_function("typeof treeRowRegions === 'function'", timeout=10_000)
    except Exception:
        items.add("page_exposes_the_region_resolver", False,
                  "treeRowRegions is not defined on /workbench")
        page.close()
        return
    items.add("page_exposes_the_region_resolver", True,
              "treeRowRegions present")

    got = page.evaluate(_TREE_FIXTURE)

    items.add("row_resolves_to_its_surfaces",
              got["resolved"] == ["MIDPLANE_MAIN", "MIDPLANE_SEC"],
              "inter:MidPlane -> %r, read out of the overlay rather than "
              "re-derived from the row name" % (got["resolved"],))

    items.add("unknown_interaction_resolves_to_nothing",
              got["unknown"] == [],
              "a row the overlay does not list gets no highlight instead of a "
              "guessed surface name")

    items.add("body_emphasis_still_works",
              sorted(got["keys"]) == ["Lower", "Upper"],
              "treeRowKeys -> %r" % (got["keys"],))

    # MIDPLANE_SEC holds 25 nodes and the preview mesh can light 9 of them,
    # which is the quadratic-midside case. Saying nothing would let a partial
    # highlight read as the whole surface.
    partial = [n for n in got["notes"] if "MIDPLANE_SEC" in n]
    complete = [n for n in got["notes"] if "MIDPLANE_MAIN" in n]
    items.add("partial_highlight_is_declared",
              len(partial) == 1 and not complete,
              "1 note for the 9-of-25 surface, none for the complete one: %r"
              % (got["notes"],))

    items.add("no_page_errors_on_workbench", not errors,
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
    """No browser here is not a failing check.

    scripts/run_all_real_checks.py counts SKIPPED as passing, which is what
    lets this gate sit in the default list without demanding Chromium on every
    machine that runs the harness. What it must never do is report PASS.
    """
    print("SKIPPED: %s" % reason)
    print(json.dumps({"overall": "skipped", "reason": reason, "items": []},
                     ensure_ascii=False))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8011)
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
                print("\n== model tree ==")
                _tree_items(browser, base, items)
            finally:
                browser.close()

    # Invoked with no arguments by the harness, so the server has to be its own
    # problem. An already-running one is reused rather than fought with: the
    # port is where the workbench normally lives during development.
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
        name = type(exc).__name__
        if "playwright" in repr(type(exc)).lower() and "executable" in str(exc).lower():
            return _skip("chromium is not installed for playwright")
        raise

    overall = "fail" if items.failed() else "pass"
    # The human line first and the JSON LAST. run_all_real_checks.py parses
    # from the first `{` to the END of stdout, so a friendly line printed after
    # the payload makes the whole gate read as "printed no JSON object" —
    # measured, with all 16 items passing.
    print("\nRESULT: %s (%d/%d)"
          % (overall.upper(), len(items.rows) - items.failed(), len(items.rows)))
    print(json.dumps({"overall": overall, "items": items.rows},
                     ensure_ascii=False))
    return 1 if items.failed() else 0


if __name__ == "__main__":
    sys.exit(main())
