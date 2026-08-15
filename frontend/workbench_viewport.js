/*
 * workbench_viewport.js — interactive 3D contour viewport for the workbench.
 * Renders the mesh.json exported by post/export_odb_mesh.py with three.js
 * (vendored UMD r128). Exposes window.WBViewport.create(container, mesh).
 */
'use strict';

window.WBViewport = (function () {

  // Abaqus-style rainbow: blue -> cyan -> green -> yellow -> red
  function rainbow(t) {
    t = Math.max(0, Math.min(1, t));
    const stops = [
      [0.00, 0x16, 0x39, 0xC8], [0.25, 0x23, 0xAE, 0xE3],
      [0.50, 0x3D, 0xCC, 0x7E], [0.75, 0xFF, 0xB8, 0x30],
      [1.00, 0xFF, 0x45, 0x60],
    ];
    for (let i = 1; i < stops.length; i++) {
      if (t <= stops[i][0]) {
        const [t0, r0, g0, b0] = stops[i - 1];
        const [t1, r1, g1, b1] = stops[i];
        const k = (t - t0) / (t1 - t0);
        return [ (r0 + (r1 - r0) * k) / 255,
                 (g0 + (g1 - g0) * k) / 255,
                 (b0 + (b1 - b0) * k) / 255 ];
      }
    }
    return [1, 0.27, 0.38];
  }

  // Fallback palette for parts whose backend name didn't match a keyword.
  const PART_PALETTE = [
    0x4a6fa5, 0xd97757, 0x8fa5b8, 0xc9a961, 0x5a7f5f,
    0x8e6ac1, 0x35a29f, 0xb0596f, 0x6b7280, 0xf59e0b,
  ];

  // A viewport is routinely constructed while its tab is display:none, where
  // clientWidth/Height are 0. That is not merely cosmetic: a 0x0 drawing buffer
  // makes WebGL context creation THROW outright in Chromium
  // ("Error creating WebGL context"), which would kill the whole preview.
  // Build at a placeholder size and let the ResizeObserver correct it the
  // moment the container gets real layout.
  const FALLBACK_W = 640, FALLBACK_H = 360;
  function viewportSize(container) {
    return {
      w: container.clientWidth || FALLBACK_W,
      h: container.clientHeight || FALLBACK_H,
    };
  }

  function resolvePartColor(part, idx) {
    if (typeof part.color === 'string' && part.color.startsWith('#')) {
      return parseInt(part.color.slice(1), 16);
    }
    return PART_PALETTE[idx % PART_PALETTE.length];
  }

  // The model tree draws a swatch beside every instance, and the swatch has to
  // be the colour that instance actually is in the viewport. Exported rather
  // than reimplemented in the page: two copies of a palette agree right up
  // until one of them is edited.
  function colorFor(part, idx) {
    const hex = resolvePartColor(part || {}, idx || 0);
    return '#' + hex.toString(16).padStart(6, '0');
  }

  // A part is addressed by the name the backend gave it. For a v2 assembly
  // that is the INSTANCE name (post/parse_inp.py:parts_from_instance_dump),
  // which is also what the model tree keys its rows on, so a row click and a
  // mesh handle meet without a lookup table in between.
  function handleKey(part) {
    if (!part) return '';
    if (typeof part.instance === 'string' && part.instance) return part.instance;
    const name = String(part.name || '');
    // "Bar:C3D8I" — a single instance split by element type keeps one key.
    return name.includes(':') ? name.split(':')[0] : name;
  }

  // Build one part's THREE resources and push into the shared assembly. Used
  // by both the eager createMultipart() path and the streaming addPart() flow.
  function addPartToAssembly(assembly, partHandles, part, idx) {
    if (!part || !Array.isArray(part.nodes) || !part.nodes.length) return null;
    const color = resolvePartColor(part, idx);
    const positions = new Float32Array(part.nodes);
    if (part.family === 'surface' && Array.isArray(part.tris) && part.tris.length) {
      const geom = new THREE.BufferGeometry();
      geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      geom.setIndex(part.tris);
      geom.computeVertexNormals();
      const mat = new THREE.MeshPhongMaterial({
        color, side: THREE.DoubleSide,
        shininess: 18, specular: 0x333333, flatShading: false,
        polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
      });
      const surface = new THREE.Mesh(geom, mat);
      assembly.add(surface);
      const edgesGeom = new THREE.EdgesGeometry(geom, 20);
      const wire = new THREE.LineSegments(edgesGeom,
        new THREE.LineBasicMaterial({ color: 0x1c2733, transparent: true, opacity: 0.55 }));
      assembly.add(wire);
      const handle = { geom, mat, edgesGeom, wire, mesh: surface,
                       key: handleKey(part), baseColor: color, index: idx };
      partHandles.push(handle);
      return handle;
    }
    if (part.family === 'line' && Array.isArray(part.lines) && part.lines.length) {
      const geom = new THREE.BufferGeometry();
      geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      geom.setIndex(part.lines);
      const mat = new THREE.LineBasicMaterial({ color, linewidth: 2 });
      const beams = new THREE.LineSegments(geom, mat);
      assembly.add(beams);
      const handle = { geom, mat, mesh: beams, key: handleKey(part),
                       baseColor: color, index: idx };
      partHandles.push(handle);
      return handle;
    }
    return null;
  }

  // The two sides of a tie or a contact pair, drawn as themselves.
  //
  // Dimming the two BODIES was what the tree did before, and on a bonded pair
  // that is nearly no information: the faces that were joined are the interior
  // ones, they are exactly where the two bodies meet, and "both plates" is a
  // picture the user already had. What is worth seeing is which facets Abaqus
  // actually put in the surface — a selector that caught one face of eight, or
  // caught the outside of the flange instead of the bore, looks identical in
  // the spec text and completely different here.
  const REGION_MAIN = 0xff5a3c;    // main / master side
  const REGION_SECONDARY = 0x2f7de1;
  function regionColor(idx) {
    return idx % 2 === 0 ? REGION_MAIN : REGION_SECONDARY;
  }

  // Standalone geometry rather than the part's own position buffer with a
  // different index. Sharing would be cheaper and is a trap: three.js frees an
  // attribute's GPU buffer when ANY geometry holding it is disposed, so
  // clearing a highlight would blank the body it was drawn on.
  function regionGeometry(partGeom, facets) {
    const src = partGeom.getAttribute('position');
    if (!src) return null;
    const positions = new Float32Array(facets.length * 3);
    for (let i = 0; i < facets.length; i++) {
      const v = facets[i];
      positions[i * 3] = src.getX(v);
      positions[i * 3 + 1] = src.getY(v);
      positions[i * 3 + 2] = src.getZ(v);
    }
    const geom = new THREE.BufferGeometry();
    geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geom.computeVertexNormals();
    return geom;
  }

  // `regions` is what post/parse_inp.py:_overlay_region emitted, verbatim:
  // [{name, parts: [{part: <backend part index>, facets: [...]}]}, ...]
  function applyRegions(assembly, partHandles, overlays, regions) {
    for (const o of overlays) {
      assembly.remove(o.mesh);
      o.geom.dispose();
      o.mat.dispose();
    }
    overlays.length = 0;
    if (!regions || !regions.length) return overlays;

    const byIndex = new Map();
    for (const h of partHandles) {
      if (h && typeof h.index === 'number') byIndex.set(h.index, h);
    }
    regions.forEach(function (region, ri) {
      const color = typeof region.color === 'number' ? region.color : regionColor(ri);
      for (const entry of (region && region.parts) || []) {
        const handle = byIndex.get(entry.part);
        if (!handle || !handle.geom) continue;
        let facets = entry.facets;
        // The face-pick payload ships triangle INDICES (what a raycast hit
        // carries) rather than vertex triples; convert against the part's own
        // index buffer so both spellings light the same geometry.
        if ((!facets || !facets.length) && entry.tris && entry.tris.length
            && handle.geom.getIndex()) {
          const idx = handle.geom.getIndex().array;
          facets = [];
          for (const t of entry.tris) {
            facets.push(idx[3 * t], idx[3 * t + 1], idx[3 * t + 2]);
          }
        }
        if (!facets || !facets.length) continue;
        const geom = regionGeometry(handle.geom, facets);
        if (!geom) continue;
        const mat = new THREE.MeshPhongMaterial({
          color, side: THREE.DoubleSide, shininess: 40, specular: 0x555555,
          // The highlight sits ON the body it belongs to, so it loses the depth
          // test by a hair without this. Offset toward the camera rather than
          // switching depthTest off: a surface behind another body must stay
          // hidden, or the picture claims a line of sight that does not exist.
          polygonOffset: true, polygonOffsetFactor: -2 - ri,
          polygonOffsetUnits: -2 - ri,
        });
        const mesh = new THREE.Mesh(geom, mat);
        mesh.renderOrder = 2;
        assembly.add(mesh);
        overlays.push({ mesh, geom, mat });
      }
    });
    return overlays;
  }

  // Clicking a body picks it; dragging orbits. The two are told apart by
  // pointer travel, not by timing: a deliberate orbit moves further than this
  // and a mouse click jitters less. Left button only — right pans, middle
  // dollies, and stealing either would break Abaqus muscle memory.
  //
  // The ray is cast against the part meshes themselves, never against region
  // overlays or edge wires: those are display, and a pick that answered with
  // a highlight instead of the body under it would be a lie one z-fight deep.
  // A dimmed part stays pickable on purpose — clicking another body is how a
  // selection moves.
  const PICK_MAX_TRAVEL_PX = 5;
  function installPicking(renderer, camera, partHandles, diag, api) {
    const raycaster = new THREE.Raycaster();
    // Beam parts draw as 1px lines; without a world-unit threshold they are
    // unhittable. Scaled to the model rather than fixed: the same slop in mm
    // would swallow a whole micro-assembly.
    raycaster.params.Line = { threshold: diag * 0.01 };
    const down = { x: 0, y: 0, active: false };
    function onDown(ev) {
      if (ev.button !== 0) return;
      down.active = true; down.x = ev.clientX; down.y = ev.clientY;
    }
    function onUp(ev) {
      if (!down.active || ev.button !== 0) return;
      down.active = false;
      if (Math.hypot(ev.clientX - down.x, ev.clientY - down.y) > PICK_MAX_TRAVEL_PX) return;
      if (typeof api.onPick !== 'function') return;
      const rect = renderer.domElement.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      raycaster.setFromCamera(new THREE.Vector2(
        ((ev.clientX - rect.left) / rect.width) * 2 - 1,
        -((ev.clientY - rect.top) / rect.height) * 2 + 1), camera);
      const meshes = [];
      for (const h of partHandles) { if (h && h.mesh) meshes.push(h.mesh); }
      const hits = raycaster.intersectObjects(meshes, false);
      if (!hits.length) return;
      const handle = partHandles.find(h => h && h.mesh === hits[0].object);
      if (handle) {
        api.onPick(handle.key, {
          point: [hits[0].point.x, hits[0].point.y, hits[0].point.z],
          // Which triangle of the part was hit and which backend part it is —
          // the two numbers the face-level pick resolves against pick_faces.
          // A LineSegments hit has no triangle; null says so.
          faceIndex: typeof hits[0].faceIndex === 'number' ? hits[0].faceIndex : null,
          partIndex: typeof handle.index === 'number' ? handle.index : null,
        });
      }
    }
    renderer.domElement.addEventListener('pointerdown', onDown);
    renderer.domElement.addEventListener('pointerup', onUp);
    return function unbind() {
      renderer.domElement.removeEventListener('pointerdown', onDown);
      renderer.domElement.removeEventListener('pointerup', onUp);
    };
  }

  // Selecting a row in the model tree dims everything that row is not about.
  // Dim rather than hide: a contact pair means nothing without the two bodies
  // still visible around it, and a viewport that empties on a click reads as a
  // bug. Named parts also get their edges brightened, because on a dark
  // assembly a colour change alone is easy to miss.
  const DIM_OPACITY = 0.12;
  function applyEmphasis(partHandles, keys) {
    const wanted = keys && keys.length ? new Set(keys) : null;
    for (const h of partHandles) {
      if (!h || !h.mat) continue;
      const on = !wanted || wanted.has(h.key);
      h.mat.transparent = !on;
      h.mat.opacity = on ? 1 : DIM_OPACITY;
      h.mat.depthWrite = on;
      h.mat.needsUpdate = true;
      if (h.wire) {
        h.wire.visible = on;
        h.wire.material.opacity = on && wanted ? 0.9 : 0.55;
      }
    }
  }

  function create(container, mesh) {
    // Multi-part mesh (custom_inp / any inp with several ELSET blocks) — the
    // backend hands us mesh.parts=[{name, family, nodes, tris|lines, color}].
    // We render each part as its own Mesh (surface) or LineSegments (beams)
    // so users can see a real assembly, not one blob.
    if (Array.isArray(mesh.parts) && mesh.parts.length > 0) {
      return createMultipart(container, mesh);
    }
    const nodeCount = mesh.node_count;
    const base = new Float32Array(mesh.nodes);
    const disp = new Float32Array(mesh.displacement || new Array(nodeCount * 3).fill(0));

    const bbox = mesh.bbox;
    const diag = Math.hypot(bbox[1][0] - bbox[0][0], bbox[1][1] - bbox[0][1], bbox[1][2] - bbox[0][2]) || 1;
    const center = [
      (bbox[0][0] + bbox[1][0]) / 2, (bbox[0][1] + bbox[1][1]) / 2, (bbox[0][2] + bbox[1][2]) / 2,
    ];
    let maxDisp = 0;
    for (let i = 0; i < nodeCount; i++) {
      const d = Math.hypot(disp[i * 3], disp[i * 3 + 1], disp[i * 3 + 2]);
      if (d > maxDisp) maxDisp = d;
    }
    // Auto scale so peak deformation reads as ~8% of the model diagonal
    const autoScale = maxDisp > 0 ? (0.08 * diag) / maxDisp : 0;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(window.devicePixelRatio || 1);
    const initSize = viewportSize(container);
    renderer.setSize(initSize.w, initSize.h);
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    // Abaqus-ish light-gray background — high contrast against dark edges.
    scene.background = new THREE.Color(0xeef1f5);

    // Three-light rig for engineering shading: soft ambient + strong key + fill.
    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const keyLight = new THREE.DirectionalLight(0xffffff, 0.75);
    keyLight.position.set(diag * 2, diag * 3, diag * 2);
    scene.add(keyLight);
    const fillLight = new THREE.DirectionalLight(0xffffff, 0.28);
    fillLight.position.set(-diag * 2, -diag * 1, -diag * 1.5);
    scene.add(fillLight);

    const camera = new THREE.PerspectiveCamera(
      40, initSize.w / initSize.h, diag / 1000, diag * 40);
    camera.position.set(center[0] + diag * 0.9, center[1] + diag * 0.7, center[2] + diag * 1.1);
    camera.lookAt(center[0], center[1], center[2]);

    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.target.set(center[0], center[1], center[2]);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    // Abaqus muscle memory: right-click drag pans, middle button dollies,
    // left button orbits. OrbitControls defaults this already, but be explicit.
    controls.mouseButtons = {
      LEFT: THREE.MOUSE.ROTATE,
      MIDDLE: THREE.MOUSE.DOLLY,
      RIGHT: THREE.MOUSE.PAN,
    };
    controls.enablePan = true;
    controls.screenSpacePanning = true;

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(base.slice(), 3));
    geometry.setIndex(Array.from(mesh.tris));
    geometry.setAttribute('color',
      new THREE.BufferAttribute(new Float32Array(nodeCount * 3), 3));
    geometry.computeVertexNormals();

    // Shaded material with per-vertex color (contour fill) + Phong highlights.
    const material = new THREE.MeshPhongMaterial({
      vertexColors: true, side: THREE.DoubleSide,
      shininess: 18, specular: 0x333333, flatShading: false,
      polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
    });
    const surface = new THREE.Mesh(geometry, material);
    scene.add(surface);

    // Feature-edge overlay (~20° angle) — this is what makes it read as CAD,
    // not a shiny blob. Sharper than a full WireframeGeometry.
    const edgesGeom = new THREE.EdgesGeometry(geometry, 20);
    const wire = new THREE.LineSegments(edgesGeom,
      new THREE.LineBasicMaterial({ color: 0x1c2733, transparent: true, opacity: 0.55 }));
    scene.add(wire);

    // Coordinate triad — Abaqus-standard R=X, G=Y, B=Z; sits at the bbox
    // origin corner so users always know which way is up.
    const axes = new THREE.AxesHelper(diag * 0.18);
    axes.position.set(bbox[0][0], bbox[0][1], bbox[0][2]);
    scene.add(axes);

    const state = {
      field: mesh.fields.mises ? 'mises' : (mesh.fields.u_mag ? 'u_mag' : null),
      deformScale: mesh.is_modal ? autoScale : 0,
      playing: !!mesh.is_modal,
      raf: null, t0: performance.now(), disposed: false,
    };

    function applyField() {
      const colors = geometry.attributes.color.array;
      const field = state.field && mesh.fields[state.field];
      for (let i = 0; i < nodeCount; i++) {
        // Neutral engineering gray-blue when no field is set — plays well
        // with Phong lighting and reads clearly on a white background.
        let rgb = [0.68, 0.74, 0.82];
        if (field) {
          const span = (field.max - field.min) || 1;
          rgb = rainbow((field.values[i] - field.min) / span);
        }
        colors[i * 3] = rgb[0]; colors[i * 3 + 1] = rgb[1]; colors[i * 3 + 2] = rgb[2];
      }
      geometry.attributes.color.needsUpdate = true;
    }

    function applyDeform(factor) {
      const pos = geometry.attributes.position.array;
      const k = state.deformScale * factor;
      for (let i = 0; i < nodeCount * 3; i++) pos[i] = base[i] + disp[i] * k;
      geometry.attributes.position.needsUpdate = true;
      wire.geometry.dispose();
      wire.geometry = new THREE.EdgesGeometry(geometry, 20);
    }

    let wireRefresh = 0;
    function tick(now) {
      if (state.disposed) return;
      state.raf = requestAnimationFrame(tick);
      if (state.playing && state.deformScale > 0) {
        const factor = Math.sin((now - state.t0) / 1000 * Math.PI * 2 * 0.6);
        const pos = geometry.attributes.position.array;
        const k = state.deformScale * factor;
        for (let i = 0; i < nodeCount * 3; i++) pos[i] = base[i] + disp[i] * k;
        geometry.attributes.position.needsUpdate = true;
        // Rebuilding the wireframe every frame is wasteful — refresh sparsely.
        if (++wireRefresh % 6 === 0) {
          wire.geometry.dispose();
          wire.geometry = new THREE.EdgesGeometry(geometry, 20);
        }
      }
      controls.update();
      renderer.render(scene, camera);
    }

    // The viewport is often constructed while its tab is display:none (a page
    // reload lands on the spec tab, and the preview builds in the background),
    // so clientWidth is 0 and the WebGL drawing buffer would stay 0x0 forever —
    // a window 'resize' listener never fires when a tab is merely shown.
    // Observe the container itself so the first non-zero layout sizes us.
    function onResize() {
      if (state.disposed) return;
      const w = container.clientWidth, h = container.clientHeight;
      if (!w || !h) return;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    }
    const resizeObs = typeof ResizeObserver !== 'undefined'
      ? new ResizeObserver(onResize) : null;
    if (resizeObs) resizeObs.observe(container);
    window.addEventListener('resize', onResize);

    applyField();
    applyDeform(state.playing ? 0 : 1);
    tick(performance.now());

    // Snapshot the initial camera so the UI can offer a "reset view" button.
    const homePos = camera.position.clone();
    const homeTarget = controls.target.clone();

    const axisScale = { x: 1, y: 1, z: 1 };

    return {
      autoScale,
      setField(name) { state.field = name; applyField(); },
      setDeform(scale) {
        state.deformScale = scale;
        if (!state.playing) applyDeform(1);
      },
      setPlaying(on) {
        state.playing = on;
        if (!on) applyDeform(1);
      },
      resetView() {
        camera.position.copy(homePos);
        controls.target.copy(homeTarget);
        controls.update();
      },
      // Instant cheat-scale a single axis — used by the parametric slider
      // panel to show geometry-change feedback without re-running CAE. Applies
      // to both the shaded surface and the edge overlay so they stay aligned.
      setAxisScale(axis, factor) {
        if (!'xyz'.includes(axis)) return;
        axisScale[axis] = factor;
        surface.scale.set(axisScale.x, axisScale.y, axisScale.z);
        wire.scale.set(axisScale.x, axisScale.y, axisScale.z);
        if (typeof axes !== 'undefined') {
          axes.scale.set(axisScale.x, axisScale.y, axisScale.z);
        }
      },
      dispose() {
        state.disposed = true;
        cancelAnimationFrame(state.raf);
        window.removeEventListener('resize', onResize);
        if (resizeObs) resizeObs.disconnect();
        geometry.dispose(); wire.geometry.dispose(); material.dispose();
        renderer.dispose();
        if (renderer.domElement.parentNode) renderer.domElement.parentNode.removeChild(renderer.domElement);
      },
    };
  }

  function createMultipart(container, mesh) {
    const bbox = mesh.bbox;
    const diag = Math.hypot(
      bbox[1][0] - bbox[0][0], bbox[1][1] - bbox[0][1], bbox[1][2] - bbox[0][2]) || 1;
    const center = [
      (bbox[0][0] + bbox[1][0]) / 2,
      (bbox[0][1] + bbox[1][1]) / 2,
      (bbox[0][2] + bbox[1][2]) / 2,
    ];

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(window.devicePixelRatio || 1);
    const initSize = viewportSize(container);
    renderer.setSize(initSize.w, initSize.h);
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xeef1f5);
    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const keyLight = new THREE.DirectionalLight(0xffffff, 0.75);
    keyLight.position.set(diag * 2, diag * 3, diag * 2);
    scene.add(keyLight);
    const fillLight = new THREE.DirectionalLight(0xffffff, 0.28);
    fillLight.position.set(-diag * 2, -diag * 1, -diag * 1.5);
    scene.add(fillLight);

    const camera = new THREE.PerspectiveCamera(
      40, initSize.w / initSize.h, diag / 1000, diag * 40);
    camera.position.set(center[0] + diag * 0.9, center[1] + diag * 0.7, center[2] + diag * 1.1);
    camera.lookAt(center[0], center[1], center[2]);

    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.target.set(center[0], center[1], center[2]);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.mouseButtons = {
      LEFT: THREE.MOUSE.ROTATE,
      MIDDLE: THREE.MOUSE.DOLLY,
      RIGHT: THREE.MOUSE.PAN,
    };
    controls.enablePan = true;
    controls.screenSpacePanning = true;

    const assembly = new THREE.Group();
    scene.add(assembly);

    // Per-part disposable resources so dispose() can clean up cleanly.
    const partHandles = [];
    const regionOverlays = [];

    mesh.parts.forEach((part, idx) => addPartToAssembly(assembly, partHandles, part, idx));

    const axes = new THREE.AxesHelper(diag * 0.18);
    axes.position.set(bbox[0][0], bbox[0][1], bbox[0][2]);
    scene.add(axes);

    const state = { raf: null, disposed: false };
    function tick() {
      if (state.disposed) return;
      state.raf = requestAnimationFrame(tick);
      controls.update();
      renderer.render(scene, camera);
    }
    // The viewport is often constructed while its tab is display:none (a page
    // reload lands on the spec tab, and the preview builds in the background),
    // so clientWidth is 0 and the WebGL drawing buffer would stay 0x0 forever —
    // a window 'resize' listener never fires when a tab is merely shown.
    // Observe the container itself so the first non-zero layout sizes us.
    function onResize() {
      if (state.disposed) return;
      const w = container.clientWidth, h = container.clientHeight;
      if (!w || !h) return;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    }
    const resizeObs = typeof ResizeObserver !== 'undefined'
      ? new ResizeObserver(onResize) : null;
    if (resizeObs) resizeObs.observe(container);
    window.addEventListener('resize', onResize);
    tick();

    const homePos = camera.position.clone();
    const homeTarget = controls.target.clone();
    const axisScale = { x: 1, y: 1, z: 1 };

    let unbindPick = null;
    const api = {
      // Fields / deform not meaningful on a bare preview assembly — no-op.
      autoScale: 0,
      setField() {},
      setDeform() {},
      setPlaying() {},
      // The page assigns a handler here; a viewport with none swallows clicks.
      onPick: null,
      resetView() {
        camera.position.copy(homePos);
        controls.target.copy(homeTarget);
        controls.update();
      },
      // Emphasis: the model tree hands us the keys a row is about.
      emphasize(keys) { applyEmphasis(partHandles, keys); },
      clearEmphasis() { applyEmphasis(partHandles, null); },
      // The facets of named surfaces -- the two sides of a tie or a
      // contact pair -- drawn on top of the bodies that carry them.
      showRegions(regions) {
        applyRegions(assembly, partHandles, regionOverlays, regions);
      },
      clearRegions() {
        applyRegions(assembly, partHandles, regionOverlays, null);
      },
      partKeys() { return partHandles.map(function (h) { return h && h.key; }); },
      setAxisScale(axis, factor) {
        if (!'xyz'.includes(axis)) return;
        axisScale[axis] = factor;
        assembly.scale.set(axisScale.x, axisScale.y, axisScale.z);
        axes.scale.set(axisScale.x, axisScale.y, axisScale.z);
      },
      dispose() {
        state.disposed = true;
        if (unbindPick) unbindPick();
        cancelAnimationFrame(state.raf);
        window.removeEventListener('resize', onResize);
        if (resizeObs) resizeObs.disconnect();
        applyRegions(assembly, partHandles, regionOverlays, null);
        for (const h of partHandles) {
          h.geom && h.geom.dispose();
          h.mat && h.mat.dispose();
          h.edgesGeom && h.edgesGeom.dispose();
        }
        renderer.dispose();
        if (renderer.domElement.parentNode) {
          renderer.domElement.parentNode.removeChild(renderer.domElement);
        }
      },
    };
    unbindPick = installPicking(renderer, camera, partHandles, diag, api);
    return api;
  }

  // Streaming variant: caller has a meta payload (bbox, part_count) but the
  // actual parts arrive over an SSE stream. Sets up renderer/camera up front
  // so the user sees an empty viewport with axes immediately, then addPart()
  // grows the assembly one part at a time. Returns the same handle shape as
  // createMultipart plus addPart(part)/finalize().
  function createStreaming(container, meta) {
    const bbox = (meta && meta.bbox) || [[0, 0, 0], [1, 1, 1]];
    const diag = Math.hypot(
      bbox[1][0] - bbox[0][0], bbox[1][1] - bbox[0][1], bbox[1][2] - bbox[0][2]) || 1;
    const center = [
      (bbox[0][0] + bbox[1][0]) / 2,
      (bbox[0][1] + bbox[1][1]) / 2,
      (bbox[0][2] + bbox[1][2]) / 2,
    ];

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(window.devicePixelRatio || 1);
    const initSize = viewportSize(container);
    renderer.setSize(initSize.w, initSize.h);
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xeef1f5);
    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const keyLight = new THREE.DirectionalLight(0xffffff, 0.75);
    keyLight.position.set(diag * 2, diag * 3, diag * 2);
    scene.add(keyLight);
    const fillLight = new THREE.DirectionalLight(0xffffff, 0.28);
    fillLight.position.set(-diag * 2, -diag * 1, -diag * 1.5);
    scene.add(fillLight);

    const camera = new THREE.PerspectiveCamera(
      40, initSize.w / initSize.h, diag / 1000, diag * 40);
    camera.position.set(center[0] + diag * 0.9, center[1] + diag * 0.7, center[2] + diag * 1.1);
    camera.lookAt(center[0], center[1], center[2]);

    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.target.set(center[0], center[1], center[2]);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.mouseButtons = {
      LEFT: THREE.MOUSE.ROTATE,
      MIDDLE: THREE.MOUSE.DOLLY,
      RIGHT: THREE.MOUSE.PAN,
    };
    controls.enablePan = true;
    controls.screenSpacePanning = true;

    const assembly = new THREE.Group();
    scene.add(assembly);
    const partHandles = [];
    const regionOverlays = [];
    let addedCount = 0;

    const axes = new THREE.AxesHelper(diag * 0.18);
    axes.position.set(bbox[0][0], bbox[0][1], bbox[0][2]);
    scene.add(axes);

    const state = { raf: null, disposed: false };
    function tick() {
      if (state.disposed) return;
      state.raf = requestAnimationFrame(tick);
      controls.update();
      renderer.render(scene, camera);
    }
    // The viewport is often constructed while its tab is display:none (a page
    // reload lands on the spec tab, and the preview builds in the background),
    // so clientWidth is 0 and the WebGL drawing buffer would stay 0x0 forever —
    // a window 'resize' listener never fires when a tab is merely shown.
    // Observe the container itself so the first non-zero layout sizes us.
    function onResize() {
      if (state.disposed) return;
      const w = container.clientWidth, h = container.clientHeight;
      if (!w || !h) return;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    }
    const resizeObs = typeof ResizeObserver !== 'undefined'
      ? new ResizeObserver(onResize) : null;
    if (resizeObs) resizeObs.observe(container);
    window.addEventListener('resize', onResize);
    tick();

    const homePos = camera.position.clone();
    const homeTarget = controls.target.clone();
    const axisScale = { x: 1, y: 1, z: 1 };

    let unbindPick = null;
    const api = {
      autoScale: 0,
      setField() {}, setDeform() {}, setPlaying() {},
      // The page assigns a handler here; a viewport with none swallows clicks.
      // Parts added mid-stream are picked up automatically: the raycast reads
      // partHandles live rather than snapshotting it at construction.
      onPick: null,
      addPart(part, idx) {
        const at = typeof idx === 'number' ? idx : addedCount;
        addedCount++;
        return addPartToAssembly(assembly, partHandles, part, at);
      },
      finalize() {}, // reserved for post-stream animations (e.g. fit-to-view)
      resetView() {
        camera.position.copy(homePos);
        controls.target.copy(homeTarget);
        controls.update();
      },
      // Emphasis: the model tree hands us the keys a row is about.
      emphasize(keys) { applyEmphasis(partHandles, keys); },
      clearEmphasis() { applyEmphasis(partHandles, null); },
      // The facets of named surfaces -- the two sides of a tie or a
      // contact pair -- drawn on top of the bodies that carry them.
      showRegions(regions) {
        applyRegions(assembly, partHandles, regionOverlays, regions);
      },
      clearRegions() {
        applyRegions(assembly, partHandles, regionOverlays, null);
      },
      partKeys() { return partHandles.map(function (h) { return h && h.key; }); },
      setAxisScale(axis, factor) {
        if (!'xyz'.includes(axis)) return;
        axisScale[axis] = factor;
        assembly.scale.set(axisScale.x, axisScale.y, axisScale.z);
        axes.scale.set(axisScale.x, axisScale.y, axisScale.z);
      },
      dispose() {
        state.disposed = true;
        if (unbindPick) unbindPick();
        cancelAnimationFrame(state.raf);
        window.removeEventListener('resize', onResize);
        if (resizeObs) resizeObs.disconnect();
        applyRegions(assembly, partHandles, regionOverlays, null);
        for (const h of partHandles) {
          h.geom && h.geom.dispose();
          h.mat && h.mat.dispose();
          h.edgesGeom && h.edgesGeom.dispose();
        }
        renderer.dispose();
        if (renderer.domElement.parentNode) {
          renderer.domElement.parentNode.removeChild(renderer.domElement);
        }
      },
    };
    unbindPick = installPicking(renderer, camera, partHandles, diag, api);
    return api;
  }

  return { create, createStreaming, rainbow, colorFor };
})();
