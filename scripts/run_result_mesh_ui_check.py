"""Browser check: the results viewport draws an assembly, not a nest of wires.

A node label is not a key. Every part instance in an ODB numbers its nodes
from 1, and `abaqus-agent-mesh/1` keyed coordinates, fields and -- worst --
face identity by the bare label. Measured on the bearing-block acceptance ODB
(3 instances, 57030 nodes, 34831 elements):

    distinct labels          37622 of 57030   (19408 nodes unreachable)
    real exterior faces      10590
    faces the /1 walk found   3928             (6662 deleted as "interior")
    exported bbox y          [0, 40]           (the assembly reaches 50)
    surface edges over 20mm  25.7% of 12840    (mesh seeds are 1.5 to 7 mm)

The overwrite is the half that is easy to see; the deletion is the half that
matters. `exterior_faces` counts a face by its sorted node labels, so one
instance's face and another's collide into a single key, the count reaches two,
and BOTH are dropped as interior. That is how 63% of a surface disappears
while the run reports COMPLETED and every KPI stays correct.

This gate is hermetic -- no Abaqus, no solver. It builds two instances that
number their nodes identically, exactly as Abaqus does, and drives the real
`WBViewport.create` in real Chromium.

    1. bare labels delete the surface entirely (the mechanism, in the small)
    2. scoped labels keep both instances and place them where they belong
    3. the per-instance ranges are contiguous and carry no cross-part triangle
    4. the scoped mesh RENDERS as solid geometry -- edge density below the floor
    5. the SAME mesh, cross-wired the way the bug wired it, renders as a wire
       nest above the ceiling. Without 5, item 4 only proves the metric can
       say yes

Items 4 and 5 put a number on "五颜六色闪来闪去". Three candidate metrics were
measured on the two renders before one was chosen, rather than a threshold
being guessed:

    metric          clean      cross-wired   separation
    coverage        0.1607     0.1972        1.2x   (too weak to judge on)
    speckle         0.0020     0.0101        5.0x
    edge density    0.0079     0.0554        7.0x   <- judged on this

Edge density -- the fraction of pixels with a strong luminance gradient -- is
both the widest gap and the closest to what the eye is reacting to: a nest of
slivers is edges nearly everywhere, a shaded solid is edges only at its
silhouette and its feature lines. Speckle and coverage are still reported, so
a future change that moves them shows up in the record.

Run:  .venv\\Scripts\\python.exe scripts\\run_result_mesh_ui_check.py
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Measured on the fixtures below: clean 0.0079, cross-wired 0.0554. Both
# thresholds sit strictly inside that gap and on neither measurement, so a
# small renderer change does not flip the verdict and a real regression still
# does. The clean render has 2.5x of headroom, the broken one 1.6x.
EDGE_DENSITY_FLOOR = 0.020
EDGE_DENSITY_CEILING = 0.035


@contextlib.contextmanager
def _server(port: int):
    env = {**os.environ, "ABAQUS_AGENT_PORT": str(port),
           "ABAQUS_AGENT_HOST": "127.0.0.1"}
    log_path = Path(tempfile.gettempdir()) / ("result_mesh_ui_%d.log" % port)
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
<style>body{margin:0;background:#fff}#vp{width:900px;height:600px}</style>
<script src="%(base)s/static/vendor/three.min.js"></script>
<script src="%(base)s/static/vendor/OrbitControls.js"></script>
<script src="%(base)s/static/workbench_viewport.js"></script>
</head><body><div id="vp"></div></body></html>"""


# ---------------------------------------------------------------------------
# Fixture: two instances, each numbering its nodes from 1 -- as Abaqus does.
# ---------------------------------------------------------------------------

def _block(nx, ny, nz, origin):
    """A structured hex block. Labels start at 1, like every instance's do."""
    ox, oy, oz = origin
    coords = {}
    label_at = {}
    label = 1
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                coords[label] = (ox + i * 1.0, oy + j * 1.0, oz + k * 1.0)
                label_at[(i, j, k)] = label
                label += 1
    conns = []
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                conns.append((
                    label_at[(i, j, k)], label_at[(i + 1, j, k)],
                    label_at[(i + 1, j + 1, k)], label_at[(i, j + 1, k)],
                    label_at[(i, j, k + 1)], label_at[(i + 1, j, k + 1)],
                    label_at[(i + 1, j + 1, k + 1)], label_at[(i, j + 1, k + 1)],
                ))
    return coords, conns


def _fixture(scoped):
    """Both blocks reuse labels 1..N. `scoped` decides whether that matters."""
    from post.export_odb_mesh import build_surface

    a_coords, a_conns = _block(4, 4, 4, (0.0, 0.0, 0.0))
    b_coords, b_conns = _block(4, 4, 4, (0.0, 8.0, 0.0))

    coords = {}
    elements = []
    for name, (cs, conns) in (("A", (a_coords, a_conns)),
                              ("B", (b_coords, b_conns))):
        for label, xyz in cs.items():
            coords[(name, label) if scoped else label] = xyz
        for conn in conns:
            scoped_conn = [(name, n) for n in conn] if scoped else list(conn)
            elements.append(("C3D8", scoped_conn))
    return build_surface(coords, elements)


def _mesh_payload(flat_nodes, flat_tris, ordered_labels):
    """The shape `WBViewport.create` consumes, with a smooth field on it.

    The field is the y coordinate: on correct geometry it reads as a clean
    gradient, so any speckle in the frame comes from the geometry rather than
    from a noisy field.
    """
    from post.export_odb_mesh import group_by_instance

    ys = flat_nodes[1::3]
    lo, hi = (min(ys), max(ys)) if ys else (0.0, 1.0)
    grouping = group_by_instance(flat_tris, ordered_labels)
    xs = flat_nodes[0::3]
    zs = flat_nodes[2::3]
    return {
        "format": "abaqus-agent-mesh/2",
        "step": "Fixture",
        "is_modal": False, "mode": None, "frequency": None,
        "node_count": len(ordered_labels),
        "tri_count": len(flat_tris) // 3,
        "nodes": flat_nodes,
        "tris": flat_tris,
        "fields": {"mises": {"values": list(ys), "min": lo, "max": hi}},
        "displacement": [0.0] * (len(ordered_labels) * 3),
        "instances": grouping["groups"],
        "cross_instance_tris": grouping["cross_instance_tris"],
        "unscoped_field_values": 0,
        "bbox": [[min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]]
        if xs else [[0, 0, 0], [0, 0, 0]],
    }


def _cross_wire(mesh, stride=3):
    """Rewire every `stride`-th triangle across the two parts.

    This is what the bug produced -- a triangle whose corners belong to
    different instances -- reproduced deliberately so item 5 can prove the
    speckle metric is capable of failing.
    """
    out = dict(mesh)
    tris = list(mesh["tris"])
    n = mesh["node_count"]
    for t in range(0, len(tris) // 3, stride):
        tris[3 * t + 2] = (tris[3 * t + 2] + n // 2) % n
    out["tris"] = tris
    return out


def _render_metrics(png_bytes):
    """{edge_density, speckle, coverage} for one frame.

    edge_density -- pixels whose luminance jumps hard against the next pixel,
      right or down. A shaded solid has these only on silhouettes and feature
      lines; a nest of slivers has them nearly everywhere. This is the judged
      one.
    speckle -- pixels that disagree with the median of their four neighbours.
    coverage -- pixels that are not the page background.
    """
    import numpy as np
    from PIL import Image

    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    rgb = np.asarray(img, dtype=np.int16)
    g = np.asarray(img.convert("L"), dtype=np.int16)

    gx = np.abs(np.diff(g, axis=1))[:-1, :]
    gy = np.abs(np.diff(g, axis=0))[:, :-1]
    edge_density = float(np.mean((gx + gy) > 30))

    c = g[1:-1, 1:-1]
    stack = np.stack([g[:-2, 1:-1], g[2:, 1:-1], g[1:-1, :-2], g[1:-1, 2:]])
    speckle = float(np.mean(np.abs(c - np.median(stack, axis=0)) > 24))

    bg = rgb[0, 0].astype(np.int16)
    coverage = float(np.mean(np.abs(rgb - bg).sum(axis=2) > 12))
    return {"edge_density": edge_density, "speckle": speckle,
            "coverage": coverage}


class Items:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.rows.append({"name": name, "status": "pass" if ok else "fail",
                          "detail": detail})
        print("  %-4s  %-42s %s" % ("PASS" if ok else "FAIL", name, detail))

    def failed(self) -> int:
        return sum(1 for r in self.rows if r["status"] != "pass")


def _render(page, base: str, mesh: dict, png_path: Path) -> bytes:
    page.set_content(_PAGE % {"base": base})
    page.wait_for_function("typeof THREE !== 'undefined' && !!window.WBViewport")
    page.evaluate(
        "(m) => { window.__vp = WBViewport.create(document.getElementById('vp'), m); }",
        mesh)
    page.wait_for_timeout(700)
    shot = page.locator("#vp canvas").screenshot(path=str(png_path))
    return shot


def _trust_items(browser, base: str, clean: dict, items: Items) -> None:
    """The real /workbench page, judging real payloads.

    Run directories are never regenerated -- a run id hashes the spec, not the
    exporter -- so every mesh.json written before instance scoping is still on
    disk and still draws the wrong assembly. The page could not say so, because
    nothing read `format`. These three items are the difference between adding
    a warning and proving it fires.
    """
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base + "/workbench")
    page.wait_for_function("typeof meshTrustNotes === 'function'", timeout=20000)

    def notes(mesh):
        return page.evaluate("(m) => meshTrustNotes(m)", mesh)

    got = notes(clean)
    items.add(
        "a_current_mesh_carries_no_warning",
        got["legacy"] == "" and got["broken"] == "" and not errors,
        "format %s -> no notes; page errors: %s"
        % (clean["format"], errors or "none"))

    legacy = dict(clean, format="abaqus-agent-mesh/1")
    got = notes(legacy)
    items.add(
        "a_pre_fix_mesh_says_so",
        bool(got["legacy"]) and not got["broken"],
        "format abaqus-agent-mesh/1 -> %r" % got["legacy"][:90])

    # node_count left as-is while the coordinate array is cut short: WebGL
    # sizes a colour buffer from one and indexes with the other, and paints
    # rather than throwing.
    contradictory = dict(clean, nodes=clean["nodes"][:-3], cross_instance_tris=4)
    got = notes(contradictory)
    items.add(
        "a_self_contradictory_mesh_says_so",
        bool(got["broken"]),
        "short node array + 4 cross-instance tris -> %r" % got["broken"][:120])

    page.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8153)
    ap.add_argument("--out", type=Path,
                    default=ROOT / "artifacts" / "result_mesh_ui" / "report.json")
    args = ap.parse_args()

    out_dir = args.out.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    items = Items()
    started = time.time()

    # ---- data items, no browser needed ------------------------------------
    bare_nodes, bare_tris, bare_labels = _fixture(scoped=False)
    items.add(
        "bare_labels_delete_the_whole_surface",
        bare_tris == [] and bare_labels == [],
        "two blocks numbered alike collapse into one: %d tris, %d nodes -- "
        "every face paired with its twin in the other instance and was called "
        "interior" % (len(bare_tris) // 3, len(bare_labels)))

    nodes, tris, labels = _fixture(scoped=True)
    ys = nodes[1::3]
    # 4x4x4 block: 6 faces x 16 quads x 2 tris = 192 tris, 98 surface nodes
    ok = (len(tris) // 3 == 384 and len(labels) == 196
          and min(ys) == 0.0 and max(ys) == 12.0)
    items.add(
        "scoped_labels_keep_both_instances",
        ok,
        "%d tris, %d nodes, y spans [%.1f, %.1f] -- both blocks present and "
        "8 units apart, as built" % (len(tris) // 3, len(labels),
                                     min(ys), max(ys)))

    mesh = _mesh_payload(nodes, tris, labels)
    groups = mesh["instances"]
    ok = (len(groups) == 2 and mesh["cross_instance_tris"] == 0
          and [g["name"] for g in groups] == ["A", "B"]
          and all(g["tri_count"] == 192 for g in groups))
    items.add(
        "per_instance_ranges_are_contiguous",
        ok,
        "groups=%s cross_instance_tris=%d"
        % ([(g["name"], g["tri_start"], g["tri_count"]) for g in groups],
           mesh["cross_instance_tris"]))

    broken = _cross_wire(mesh)
    ok = broken["tris"] != mesh["tris"]
    items.add("cross_wired_fixture_differs", ok,
              "the deliberately corrupted mesh is not the clean one")

    # ---- render items -----------------------------------------------------
    clean_m = None
    broken_m = None
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        items.add("playwright_available", False, "%s" % exc)
        sync_playwright = None

    if sync_playwright is not None:
        base = "http://127.0.0.1:%d" % args.port
        with _server(args.port), sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1000, "height": 700})
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            clean_png = _render(page, base, mesh, out_dir / "render_scoped.png")
            clean_m = _render_metrics(clean_png)
            items.add(
                "the_scoped_mesh_renders_as_solid_geometry",
                clean_m["edge_density"] < EDGE_DENSITY_FLOOR and not errors,
                "edge density %.4f < %.3f floor (speckle %.4f, coverage %.4f); "
                "page errors: %s"
                % (clean_m["edge_density"], EDGE_DENSITY_FLOOR,
                   clean_m["speckle"], clean_m["coverage"], errors or "none"))

            broken_png = _render(page, base, broken,
                                 out_dir / "render_cross_wired.png")
            broken_m = _render_metrics(broken_png)
            items.add(
                "the_cross_wired_mesh_renders_as_a_wire_nest",
                broken_m["edge_density"] > EDGE_DENSITY_CEILING,
                "edge density %.4f > %.3f ceiling (speckle %.4f, coverage "
                "%.4f) -- the metric can say no, which is what makes the item "
                "above mean something"
                % (broken_m["edge_density"], EDGE_DENSITY_CEILING,
                   broken_m["speckle"], broken_m["coverage"]))

            _trust_items(browser, base, mesh, items)
            browser.close()

    report = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "seconds": round(time.time() - started, 1),
        "render_metrics": {"scoped": clean_m, "cross_wired": broken_m,
                           "edge_density_floor": EDGE_DENSITY_FLOOR,
                           "edge_density_ceiling": EDGE_DENSITY_CEILING},
        "overall": "pass" if items.failed() == 0 else "fail",
        "items": items.rows,
    }
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if items.failed() else 0


if __name__ == "__main__":
    raise SystemExit(main())
