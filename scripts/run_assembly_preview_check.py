"""Put a real assembly preview through the real viewport, in a real browser.

The payload side is checked by pytest and cross-checked against Abaqus's own
coordinates (tests/test_parse_inp_assembly.py). This asks the remaining
question, which no amount of JSON inspection answers: does the WebGL viewport
actually put two bodies on screen, in two places?

That question is not rhetorical. Before this batch, every assembly previewed as
an empty viewport under a SUCCESS-looking header, because post/parse_inp.py
refused any deck whose *Instance carried a placement row and nothing downstream
noticed the refusal.

No server needed — the check loads three.js and frontend/workbench_viewport.js
into a scratch page and drives WBViewport directly, so it exercises the shipped
renderer rather than a reimplementation of it.

Run:

    .venv\\Scripts\\python.exe scripts\\run_assembly_preview_check.py
    .venv\\Scripts\\python.exe scripts\\run_assembly_preview_check.py --mesh <preview_mesh.json>
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_CASE = ROOT / "cases" / "two_plate_tie"

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><style>
html,body{margin:0;background:#11161c} #vp{width:1000px;height:640px}
</style></head><body>
<div id="vp"></div>
<script src="VENDOR_THREE"></script>
<script>
// Record what the viewport puts in the scene, without asking the viewport to
// expose anything for our benefit. Widening a shipped API so a test can watch
// it is how a test ends up observing a hook rather than the product.
window.__added = [];
(function () {
  var _add = THREE.Object3D.prototype.add;
  THREE.Object3D.prototype.add = function () {
    for (var i = 0; i < arguments.length; i++) window.__added.push(arguments[i]);
    return _add.apply(this, arguments);
  };
})();
</script>
<script src="VENDOR_ORBIT"></script>
<script src="VIEWPORT_JS"></script>
<script>
window.__ready = false;
window.__error = null;
window.addEventListener('load', function () {
  try {
    var mesh = MESH_JSON;
    window.__vp = WBViewport.create(document.getElementById('vp'), mesh);
    window.__ready = true;
  } catch (e) {
    window.__error = String(e && e.stack || e);
  }
});
</script></body></html>
"""

# Read off the scene rather than off the payload: this is the question the
# payload cannot answer.
PROBE = """() => {
  const found = [];
  (window.__added || []).forEach(function (obj) {
    const g = obj && obj.geometry;
    if (!g || !g.attributes || !g.attributes.position) return;
    const pos = g.attributes.position;
    let lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
    for (let i = 0; i < pos.count; i++) {
      for (let k = 0; k < 3; k++) {
        const v = pos.getComponent ? pos.getComponent(i, k) : pos.array[i * 3 + k];
        if (v < lo[k]) lo[k] = v;
        if (v > hi[k]) hi[k] = v;
      }
    }
    found.push({name: obj.name || '', type: obj.type, count: pos.count, lo: lo, hi: hi,
                visible: obj.visible, isMesh: !!obj.isMesh});
  });
  return {objects: found};
}"""


# A body has to cover a visible share of the frame; below this it is a stray
# antialiasing fringe rather than something a user would call "on screen".
MIN_BODY_COVERAGE = 0.002      # 0.2% of pixels
MIN_TOTAL_COVERAGE = 0.01      # 1% of pixels
RENDER_TIMEOUT_MS = 15000
HUE_BUCKETS = 24               # 15 degrees each


def _analyse(png: bytes) -> dict:
    """Colour census of a frame. Deliberately not a pixel-perfect baseline.

    A baseline image would break on every camera tweak and teach everyone to
    re-bless it. What matters here is only: is anything drawn, and is it drawn
    in more than one BODY.

    Bodies are counted by hue, not by exact RGB. Directional lighting spreads
    one part across hundreds of shades, so an exact-RGB census reported the
    orange plate at 1.05% and the blue one — plainly visible in the frame — as
    a scatter of values none of which cleared the threshold. Hue survives
    shading; the viewport's fallback palette (0x4a6fa5 steel blue, 0xd97757
    brick orange, ...) is chosen to be distinguishable exactly that way.
    """
    import colorsys
    import io
    from collections import Counter

    from PIL import Image

    image = Image.open(io.BytesIO(png)).convert("RGB")
    pixels = list(image.getdata())
    census = Counter(pixels)
    background, _n = census.most_common(1)[0]
    total = len(pixels)

    hues = Counter()
    covered = 0
    for colour, count in census.items():
        if max(abs(a - b) for a, b in zip(colour, background)) <= 12:
            continue
        covered += count
        h, _l, s = colorsys.rgb_to_hls(*[c / 255.0 for c in colour])
        # Greys carry no hue: edge lines, the axes helper and the antialiasing
        # fringe all land there, and none of them is a body.
        if s < 0.15:
            continue
        hues[int(h * HUE_BUCKETS) % HUE_BUCKETS] += count

    bodies = {bucket: n / total for bucket, n in hues.items()
              if n / total >= MIN_BODY_COVERAGE}
    return {"png": png, "size": image.size, "background": background,
            "coverage": covered / total, "bodies": bodies,
            "hue_span": [round(b * 360.0 / HUE_BUCKETS) for b in sorted(bodies)]}


def _wait_for_pixels(page_obj, failures: list) -> dict | None:
    """Screenshot only once the renderer has actually drawn a frame.

    WBViewport draws from requestAnimationFrame, so the first screenshot after
    `create()` returns is an empty frame. This check originally took it and
    reported PASS on a blank image — the scene-graph probe was satisfied while
    nothing had reached the screen, which is the same shape of defect the whole
    batch exists to prevent.

    Note also that canvas.toDataURL() is NOT usable here: three.js leaves
    preserveDrawingBuffer off, so it hands back an all-black image (measured:
    640000/640000 pure black) even while the page composites correctly. The
    page screenshot goes through the compositor and shows what a user sees.
    """
    try:
        import PIL  # noqa: F401
    except ImportError:
        failures.append("Pillow is required for the pixel check: pip install Pillow")
        return None

    waited = 0
    best = None
    while waited < RENDER_TIMEOUT_MS:
        best = _analyse(page_obj.screenshot())
        if best["coverage"] >= MIN_TOTAL_COVERAGE:
            break
        page_obj.wait_for_timeout(250)
        waited += 250

    print("  frame: %dx%d background=%s coverage=%.2f%% distinct bodies=%d "
          "hues=%s"
          % (best["size"][0], best["size"][1], best["background"],
             100 * best["coverage"], len(best["bodies"]), best["hue_span"]))
    for bucket, share in sorted(best["bodies"].items(), key=lambda kv: -kv[1]):
        print("    hue ~%3d deg   %.2f%% of frame"
              % (round(bucket * 360.0 / HUE_BUCKETS), 100 * share))

    if best["coverage"] < MIN_TOTAL_COVERAGE:
        failures.append(
            "nothing rendered: %.3f%% of the frame differs from the background "
            "after %d ms" % (100 * best["coverage"], waited))
    elif len(best["bodies"]) < 2:
        failures.append(
            "only %d body colour(s) on screen; an assembly preview that draws "
            "one blob is indistinguishable from a single part"
            % len(best["bodies"]))
    return best


def _find_mesh(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    runs = sorted((DEFAULT_CASE / "runs").glob("*/preview_mesh.json"))
    if not runs:
        raise SystemExit(
            "no preview_mesh.json under %s/runs — build the case first:\n"
            "  .venv\\Scripts\\python.exe agent\\orchestrator.py "
            "cases\\two_plate_tie\\spec.yaml cases\\two_plate_tie\\expected.json "
            "cases\\two_plate_tie\\runner.json" % DEFAULT_CASE)
    return runs[-1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh", default=None)
    parser.add_argument("--shot", default=None, help="write a PNG here")
    args = parser.parse_args()

    mesh_path = _find_mesh(args.mesh)
    mesh = json.loads(mesh_path.read_text(encoding="utf-8"))
    print("mesh: %s" % mesh_path)
    print("  parse_ok=%s part_count=%s node_count=%s element_count=%s"
          % (mesh.get("parse_ok"), mesh.get("part_count"),
             mesh.get("node_count"), mesh.get("element_count")))
    for problem in mesh.get("problems", []):
        print("  problem: %s" % problem)

    failures: list[str] = []
    if not mesh.get("parse_ok"):
        failures.append("the payload itself is a refusal; nothing to render")
    if (mesh.get("part_count") or 0) < 2:
        failures.append("expected an assembly (>= 2 parts), got %s"
                        % mesh.get("part_count"))

    page = (PAGE
            .replace("VENDOR_THREE", (ROOT / "frontend" / "vendor" / "three.min.js").as_uri())
            .replace("VENDOR_ORBIT", (ROOT / "frontend" / "vendor" / "OrbitControls.js").as_uri())
            .replace("VIEWPORT_JS", (ROOT / "frontend" / "workbench_viewport.js").as_uri())
            .replace("MESH_JSON", json.dumps(mesh)))
    scratch = Path(tempfile.gettempdir()) / "abaqus_agent_assembly_preview.html"
    scratch.write_text(page, encoding="utf-8")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--use-gl=swiftshader",
                                           "--enable-unsafe-swiftshader"])
        try:
            ctx = browser.new_context(viewport={"width": 1000, "height": 640},
                                      device_scale_factor=2)
            page_obj = ctx.new_page()
            console: list[str] = []
            page_obj.on("console", lambda m: console.append("%s: %s" % (m.type, m.text)))
            page_obj.on("pageerror", lambda e: console.append("pageerror: %s" % e))
            page_obj.goto(scratch.as_uri(), wait_until="load", timeout=30000)
            page_obj.wait_for_function(
                "() => window.__ready === true || window.__error !== null",
                timeout=30000)

            error = page_obj.evaluate("() => window.__error")
            if error:
                failures.append("WBViewport.create threw: %s" % error)
                result = {}
            else:
                result = page_obj.evaluate(PROBE)

            pixels = _wait_for_pixels(page_obj, failures)
            if args.shot and pixels is not None:
                Path(args.shot).write_bytes(pixels["png"])
                print("  screenshot: %s" % args.shot)

            if result.get("error"):
                failures.append("probe: %s" % result["error"])
            objects = [o for o in result.get("objects", []) if o["count"] > 0]
            print("  scene geometries: %d" % len(objects))
            for obj in objects:
                print("    %-10s %-6s verts=%-6d x[%.2f,%.2f] y[%.2f,%.2f] z[%.2f,%.2f] visible=%s"
                      % (obj["name"] or "-", obj["type"], obj["count"],
                         obj["lo"][0], obj["hi"][0], obj["lo"][1], obj["hi"][1],
                         obj["lo"][2], obj["hi"][2], obj["visible"]))

            bodies = [o for o in objects if o["isMesh"] and o["visible"]]
            if len(bodies) < (mesh.get("part_count") or 0):
                failures.append(
                    "payload has %s parts but only %d visible meshes reached the "
                    "scene" % (mesh.get("part_count"), len(bodies)))

            # The whole point: the bodies must occupy DIFFERENT space. Two
            # instances of one part drawn without the assembly transform land
            # on identical boxes, which is exactly the wrong picture this
            # batch existed to stop.
            boxes = {tuple(round(v, 4) for v in o["lo"] + o["hi"]) for o in bodies}
            if bodies and len(boxes) < len(bodies):
                failures.append(
                    "%d of %d bodies share a bounding box — the instances were "
                    "drawn stacked at their part-local coordinates"
                    % (len(bodies) - len(boxes) + 1, len(bodies)))

            for line in console:
                if "error" in line.lower():
                    failures.append("console: %s" % line)
        finally:
            browser.close()

    print()
    if failures:
        for f in failures:
            print("FAIL: %s" % f)
        print("RESULT: FAIL")
    else:
        print("RESULT: PASS")
    # The verdict scripts/run_all_real_checks.py reads. It has to be the last
    # parseable JSON object on stdout.
    print(json.dumps({"schema": "assembly_preview_check/1",
                      "result": "FAIL" if failures else "PASS",
                      "failures": failures}, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
