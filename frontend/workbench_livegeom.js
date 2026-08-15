/* workbench_livegeom.js — the model taking shape while it is being written.

   The named-op dialect draws on the XY plane and extrudes along +z: a
   rectangular or circular outline, one base extrude, circular cuts. That is
   exactly what THREE.Shape + ExtrudeGeometry expresses, so the browser can
   draw the half-written spec by itself — no CAE, no round trip, no waiting.

   This is a SKETCH, and it says so on screen. It shows what the model has
   written so far; it does not check anything. A spec that draws here can
   still be refused by the builder (a selector that matches nothing, a cut
   with no straight edge to orient against), and the real CAE preview replaces
   this the moment the proposal lands.

   Classic script sharing the page's global scope: THREE, $, state, t, esc. */

window.WBLiveGeom = (function () {
  const PALETTE = [0x4f7cff, 0xff8a3d, 0x35c88a, 0xc879ff, 0xf2c14e, 0x59d0e0];
  const SEGMENTS = 48;   // circle facets: smooth enough at preview size

  function outlineShape(outline) {
    if (outline.kind === 'rect') {
      const [x1, y1] = outline.corner1;
      const [x2, y2] = outline.corner2;
      const shape = new THREE.Shape();
      shape.moveTo(x1, y1);
      shape.lineTo(x2, y1);
      shape.lineTo(x2, y2);
      shape.lineTo(x1, y2);
      shape.closePath();
      return shape;
    }
    if (outline.kind === 'circle') {
      const shape = new THREE.Shape();
      shape.absarc(outline.center[0], outline.center[1], outline.r, 0, Math.PI * 2, false);
      return shape;
    }
    return null;
  }

  function solidGeometry(part) {
    const shape = outlineShape(part.outline);
    if (!shape) return null;
    for (const hole of part.holes || []) {
      // A through-hole and a blind hole look the same from outside; the
      // sketch draws both as a through hole rather than inventing a depth
      // the spec has not stated yet.
      const path = new THREE.Path();
      path.absarc(hole.center[0], hole.center[1], hole.r, 0, Math.PI * 2, true);
      shape.holes.push(path);
    }
    return new THREE.ExtrudeGeometry(shape, {
      depth: part.depth, bevelEnabled: false, curveSegments: SEGMENTS,
    });
  }

  /* payload: {parts:[{name,outline,holes,depth}], instances:[{part,translate}]}
     Returns {bbox, meshes} added to `group`, or null when nothing drew. */
  function build(group, payload) {
    const byName = {};
    (payload.parts || []).forEach((p, i) => { byName[p.name] = { part: p, idx: i }; });
    const placements = [];
    for (const inst of payload.instances || []) {
      const hit = byName[inst.part];
      if (hit) placements.push({ part: hit.part, idx: hit.idx, at: inst.translate });
    }
    // Parts stream in long before the assembly block does; an un-instanced
    // part sits at the origin rather than not showing up at all.
    const placed = new Set(placements.map(p => p.part.name));
    (payload.parts || []).forEach((p, i) => {
      if (!placed.has(p.name)) placements.push({ part: p, idx: i, at: [0, 0, 0] });
    });

    const box = new THREE.Box3();
    let drew = 0;
    for (const place of placements) {
      const geom = solidGeometry(place.part);
      if (!geom) continue;
      const color = PALETTE[place.idx % PALETTE.length];
      const mesh = new THREE.Mesh(geom, new THREE.MeshPhongMaterial({
        color, transparent: true, opacity: 0.82, shininess: 12,
        side: THREE.DoubleSide, flatShading: false,
      }));
      mesh.position.set(place.at[0], place.at[1], place.at[2]);
      group.add(mesh);
      const wire = new THREE.LineSegments(
        new THREE.EdgesGeometry(geom, 25),
        new THREE.LineBasicMaterial({ color: 0x1c2733, transparent: true, opacity: 0.5 }));
      wire.position.copy(mesh.position);
      group.add(wire);
      geom.computeBoundingBox();
      box.union(geom.boundingBox.clone().translate(mesh.position));
      drew++;
    }
    return drew ? box : null;
  }

  /* A minimal viewer: same look as the real preview, a fraction of the code.
     render(payload) is idempotent — every geom event replaces the scene, so
     a part that changed size while being written does not stack. */
  function create(container) {
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio || 1);
    const size = () => ({
      w: container.clientWidth || 640,
      h: container.clientHeight || 360,
    });
    const s0 = size();
    renderer.setSize(s0.w, s0.h);
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xeef1f5);
    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const key = new THREE.DirectionalLight(0xffffff, 0.7);
    key.position.set(1, 2, 1.5);
    scene.add(key);
    const camera = new THREE.PerspectiveCamera(40, s0.w / s0.h, 0.01, 1e6);
    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;

    let group = new THREE.Group();
    scene.add(group);
    // Re-frame while the model is still growing, but never once the user has
    // taken the camera: dragging the view and having it yanked back a second
    // later is worse than a slightly off framing.
    let userMoved = false;
    controls.addEventListener('start', () => { userMoved = true; });
    const live = { raf: null, disposed: false };

    function frame(box) {
      const center = box.getCenter(new THREE.Vector3());
      const diag = box.getSize(new THREE.Vector3()).length() || 1;
      camera.near = diag / 1000;
      camera.far = diag * 40;
      camera.position.set(center.x + diag * 0.9, center.y + diag * 0.7, center.z + diag * 1.1);
      camera.updateProjectionMatrix();
      controls.target.copy(center);
      controls.update();
    }

    function tick() {
      if (live.disposed) return;
      const s = size();
      if (s.w && (renderer.domElement.width !== Math.floor(s.w * renderer.getPixelRatio()))) {
        renderer.setSize(s.w, s.h);
        camera.aspect = s.w / s.h;
        camera.updateProjectionMatrix();
      }
      controls.update();
      renderer.render(scene, camera);
      live.raf = requestAnimationFrame(tick);
    }
    tick();

    return {
      render(payload) {
        scene.remove(group);
        group.traverse(obj => {
          if (obj.geometry) obj.geometry.dispose();
          if (obj.material) obj.material.dispose();
        });
        group = new THREE.Group();
        scene.add(group);
        const box = build(group, payload);
        if (box && !userMoved) frame(box);
        return !!box;
      },
      dispose() {
        live.disposed = true;
        if (live.raf) cancelAnimationFrame(live.raf);
        controls.dispose();
        renderer.dispose();
        if (renderer.domElement.parentNode) {
          renderer.domElement.parentNode.removeChild(renderer.domElement);
        }
      },
    };
  }

  return { create, build };
})();
