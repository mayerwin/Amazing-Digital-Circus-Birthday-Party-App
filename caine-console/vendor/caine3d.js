/* =============================================================================
 *  caine3d.js — the 3D Caine for the Console.
 *
 *  Primary: loads the REAL Caine (caine.glb — the Sketchfab model, cleaned and
 *  rigged in Blender: a fitted skeleton with a looping "Idle" clip (arms gesture,
 *  head turns, body bobs/leans) + a "mouthOpen" jaw morph). It frames the whole
 *  figure, plays the Idle via AnimationMixer, drives the jaw morph from the live
 *  audio loudness when talking, and adds a gentle floating drift on top. If the
 *  GLB can't load (no WebGL / offline copy missing), it falls back to a simple
 *  procedural Caine so the console still shows a talking head.
 *  (See walk_demo.html for a rig-test page: walking + talking.)
 *
 *  API (global):
 *     const c = Caine3D.mount(containerEl);   // null if THREE/WebGL absent
 *     c.speak(true|false);                    // start / stop the talking mouth
 *     c.dispose();
 * ========================================================================== */
(function () {
  "use strict";

  function hasWebGL() {
    try { const c = document.createElement("canvas");
      return !!(window.WebGLRenderingContext && (c.getContext("webgl") || c.getContext("experimental-webgl"))); }
    catch (e) { return false; }
  }

  function mount(container) {
    if (!container || typeof THREE === "undefined" || !hasWebGL()) return null;
    const W = () => container.clientWidth || 320, H = () => container.clientHeight || 360;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(30, W() / H(), 0.01, 100);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(W(), H());
    renderer.outputEncoding = THREE.sRGBEncoding;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;     // richer contrast, less flat
    renderer.toneMappingExposure = 1.08;
    renderer.domElement.style.display = "block";
    container.appendChild(renderer.domElement);

    // iPad Safari can drop the WebGL context when the screen sleeps / tab backgrounds.
    // Don't go black — fall back to the animated eyes so Caine still "reacts" when talking.
    renderer.domElement.addEventListener("webglcontextlost", function (e) {
      e.preventDefault(); cancelAnimationFrame(raf);
      container.innerHTML = '<div class="caine-fallback" id="caineFb">◉ ‿ ◉</div>';
    }, false);

    // image-based lighting — neon "studio" reflections so the matte model looks lit & glossy
    try {
      const pmrem = new THREE.PMREMGenerator(renderer);
      const es = new THREE.Scene();
      es.add(new THREE.Mesh(new THREE.SphereGeometry(60, 16, 8),
        new THREE.MeshBasicMaterial({ color: 0x241844, side: THREE.BackSide })));
      [[0x6af2ff, -10, 7, 9], [0xff7cc0, 11, 2, -5], [0xfff2d0, 0, 14, 7], [0x9b6bff, -6, -8, 6]].forEach(function (p) {
        const s = new THREE.Mesh(new THREE.SphereGeometry(5, 12, 8), new THREE.MeshBasicMaterial({ color: p[0] }));
        s.position.set(p[1], p[2], p[3]); es.add(s);
      });
      scene.environment = pmrem.fromScene(es, 0.5).texture;
      pmrem.dispose();
    } catch (e) {}

    // key / rim / fill on top of the IBL
    scene.add(new THREE.AmbientLight(0xb9c6d6, 0.4));
    const key = new THREE.DirectionalLight(0xbfefff, 0.9); key.position.set(-3, 4, 6); scene.add(key);
    const rim = new THREE.DirectionalLight(0xff7cc0, 0.7);  rim.position.set(4, 1.2, -2); scene.add(rim);
    const fill = new THREE.DirectionalLight(0xfff0cc, 0.4); fill.position.set(0, 3, 7); scene.add(fill);

    const root = new THREE.Group(); scene.add(root);   // we sway/float this

    // animation state
    let raf = 0, t0 = performance.now(), talking = false, sp = 0;
    let mouths = [], glideAmp = 0.12, mixer = null;   // mixer plays the rigged Idle (arms/head/body)
    const clock = new THREE.Clock();
    let proc = null;           // procedural fallback control
    let mouthCur = 0, mouthLevel = 0, levelDriven = false;   // audio-driven jaw level (0..1)

    // ---------- frame the WHOLE figure with margin so the roaming never crops ----------
    function frameBody() {
      const model = root.children[0]; if (!model) return;
      model.updateMatrixWorld(true);
      const box = new THREE.Box3();
      model.traverse(o => { if (o.isMesh && o.geometry) { o.geometry.computeBoundingBox();
        box.union(o.geometry.boundingBox.clone().applyMatrix4(o.matrixWorld)); } });
      const size = box.getSize(new THREE.Vector3()), ctr = box.getCenter(new THREE.Vector3());
      model.position.set(-ctr.x, -ctr.y, -ctr.z);               // centre the whole figure
      const fov = camera.fov * Math.PI / 180, aspect = W() / H();
      const dY = (size.y / 2) / Math.tan(fov / 2);
      const dX = (size.x / 2) / (Math.tan(fov / 2) * aspect);
      camera.position.set(0, 0, Math.max(dY, dX) * 1.52);       // margin so the bigger float never crops him
      camera.lookAt(0, 0, 0);
      glideAmp = size.y * 0.12;                                 // base for the float/sway (scaled in frame())
    }

    function loadGLB() {
      if (typeof THREE.GLTFLoader === "undefined") { buildProcedural(); return; }
      new THREE.GLTFLoader().load("caine.glb?v=20260619l", function (gltf) {
        root.add(gltf.scene);
        // The model is SKINNED to a small skeleton with a looping "Idle" clip (arms gesture,
        // head turns, body bobs/leans) + a "mouthOpen" jaw morph for talking. A gentle root
        // float on top makes him drift in space. (Head meshes are rigid-skinned 100% to the
        // head bone so the face never warps.)
        if (gltf.animations && gltf.animations.length) {
          const idle = THREE.AnimationClip.findByName(gltf.animations, "Idle")
                    || gltf.animations.filter(c => c.duration > 0.2)[0];
          if (idle) { mixer = new THREE.AnimationMixer(gltf.scene); mixer.clipAction(idle).play(); }
        }
        gltf.scene.traverse(o => {
          if (o.morphTargetDictionary && "mouthOpen" in o.morphTargetDictionary)
            mouths.push({ mesh: o, idx: o.morphTargetDictionary["mouthOpen"] });
          if (o.isMesh && o.material) { const ms = Array.isArray(o.material) ? o.material : [o.material];
            ms.forEach(function (m) {        // glossier: sharper reflections so the coat/outfit isn't matte
              if ("envMapIntensity" in m) m.envMapIntensity = 1.6;
              if ("roughness" in m && m.roughness != null) m.roughness = Math.max(0.16, m.roughness * 0.55);
              if ("metalness" in m && m.metalness != null) m.metalness = Math.min(0.8, Math.max(m.metalness, 0.16));
              m.needsUpdate = true;
            }); }
        });
        if (!mouths.length) { /* no morph found -> still show the model, just no mouth */ }
        frameBody();
      }, undefined, function () { buildProcedural(); });   // offline / missing -> fallback
    }

    // ---------- procedural fallback (simple Caine head) ----------
    function buildProcedural() {
      camera.position.set(0, 0.25, 11.6); camera.lookAt(0, 0.1, 0);
      proc = makeProcedural(root);
    }

    loadGLB();

    function frame(now) {
      const t = (now - t0) / 1000;
      if (mixer) mixer.update(clock.getDelta());        // the rigged Idle: arms gesture, head turns, body bobs/leans
      // gentle floating drift on top of the skeletal idle (he hovers in space like in the show)
      const gl = proc ? 0.25 : glideAmp;
      root.position.x = Math.sin(t * 0.55) * gl * 0.7;
      root.position.y = Math.sin(t * 0.8) * gl * 0.6;
      root.rotation.y = Math.sin(t * 0.45) * 0.10;        // small extra drift; the skeleton does the real turning
      root.rotation.z = Math.sin(t * 0.6) * 0.025;
      if (proc) root.scale.setScalar(1 + Math.sin(t * 1.9) * 0.02);   // procedural fallback breathes here

      // mouth: driven by the real audio loudness (closes on silences); flutter only if no analyser
      let target = 0;
      if (levelDriven) { target = Math.min(1, mouthLevel); }
      else if (talking) { sp += 0.05 + Math.random() * 0.02;
        const env = 0.5 + 0.5 * Math.sin(sp * 6.0), fl = 0.5 + 0.5 * Math.sin(sp * 11.3 + 1.7);
        target = 0.12 + env * fl * 0.72; }
      mouthCur += (target - mouthCur) * 0.45;
      if (mouths.length) for (const m of mouths) m.mesh.morphTargetInfluences[m.idx] = mouthCur;
      if (proc) proc.setJaw(mouthCur);

      if (proc) proc.tick(t, talking);
      renderer.render(scene, camera);
      raf = requestAnimationFrame(frame);
    }
    raf = requestAnimationFrame(frame);

    function onResize() {
      camera.aspect = W() / H(); camera.updateProjectionMatrix(); renderer.setSize(W(), H());
      if (!proc && root.children.length) frameBody();    // re-fit the real model
    }
    window.addEventListener("resize", onResize);
    const ro = ("ResizeObserver" in window) ? new ResizeObserver(onResize) : null; if (ro) ro.observe(container);

    return {
      speak(on) { talking = !!on; if (on) sp = Math.random() * 10; },
      setMouthLevel(v) { mouthLevel = (typeof v === "number" && isFinite(v)) ? Math.max(0, v) : 0; levelDriven = true; },
      dispose() {
        cancelAnimationFrame(raf); window.removeEventListener("resize", onResize); if (ro) ro.disconnect();
        renderer.dispose(); if (renderer.domElement.parentNode) renderer.domElement.parentNode.removeChild(renderer.domElement);
      }
    };
  }

  // ===================== procedural fallback Caine (primitives) =====================
  function makeProcedural(root) {
    const PAL = { head: 0x1f4350, face: 0xf3ead2, eye: 0x36ecff, teeth: 0xfdfdfb, mouth: 0x270a1c,
                  lip: 0xe9d9b6, hat: 0x16121d, band: 0xff3ea5, glove: 0xf6efe0, cheek: 0xff8fc4 };
    const std = (c, o) => new THREE.MeshStandardMaterial(Object.assign({ color: c, roughness: 0.55, metalness: 0.04 }, o || {}));
    const headPivot = new THREE.Group(); root.add(headPivot);
    const head = new THREE.Mesh(new THREE.SphereGeometry(1.62, 48, 36), std(PAL.head, { roughness: 0.45 }));
    head.scale.set(1.04, 1.06, 0.58); headPivot.add(head);
    const face = new THREE.Mesh(new THREE.SphereGeometry(1.24, 40, 30), std(PAL.face, { roughness: 0.62 }));
    face.scale.set(1.0, 1.05, 0.42); face.position.z = 0.62; headPivot.add(face);
    function crescent() {
      const s = new THREE.Shape(); s.absarc(0, 0, 0.44, 0, Math.PI * 2, false);
      const h = new THREE.Path(); h.absarc(0, 0.24, 0.44, 0, Math.PI * 2, true); s.holes.push(h);
      const g = new THREE.ExtrudeGeometry(s, { depth: 0.07, bevelEnabled: true, bevelThickness: 0.02, bevelSize: 0.012, bevelSegments: 2, curveSegments: 36 });
      g.center(); return new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: PAL.eye, emissive: PAL.eye, emissiveIntensity: 0.85, roughness: 0.35 }));
    }
    const eyeL = crescent(), eyeR = crescent();
    eyeL.position.set(-0.52, 0.52, 1.24); eyeL.rotation.z = 0.28; eyeL.scale.set(0.82, 0.82, 1);
    eyeR.position.set(0.52, 0.52, 1.24); eyeR.rotation.z = -0.28; eyeR.scale.set(0.82, 0.82, 1);
    headPivot.add(eyeL, eyeR);
    const mouthW = 1.3;
    const cavity = new THREE.Mesh(new THREE.BoxGeometry(mouthW, 0.62, 0.12), std(PAL.mouth, { roughness: 0.85 }));
    cavity.position.set(0, -0.46, 1.16); headPivot.add(cavity);
    function teeth(n, parent, y) { const w = mouthW / n * 0.82;
      for (let i = 0; i < n; i++) { const t = new THREE.Mesh(new THREE.BoxGeometry(w, 0.18, 0.1), std(PAL.teeth, { roughness: 0.4 }));
        t.position.set(-mouthW / 2 + (i + 0.5) * (mouthW / n), y, 0); parent.add(t); } }
    const upper = new THREE.Group(); upper.position.set(0, -0.28, 1.24); teeth(8, upper, 0); headPivot.add(upper);
    const jaw = new THREE.Group(); jaw.position.set(0, -0.30, 1.18);
    const lip = new THREE.Mesh(new THREE.BoxGeometry(mouthW + 0.14, 0.2, 0.22), std(PAL.lip, { roughness: 0.6 })); lip.position.set(0, -0.42, 0.02); jaw.add(lip);
    const lt = new THREE.Group(); lt.position.set(0, -0.16, 0.06); teeth(8, lt, 0); jaw.add(lt); headPivot.add(jaw);
    const hat = new THREE.Group();
    hat.add(new THREE.Mesh(new THREE.CylinderGeometry(1.02, 1.02, 0.1, 40), std(PAL.hat, { roughness: 0.5 })));
    const top = new THREE.Mesh(new THREE.CylinderGeometry(0.64, 0.7, 0.92, 40), std(PAL.hat, { roughness: 0.5 })); top.position.y = 0.5; hat.add(top);
    const band = new THREE.Mesh(new THREE.CylinderGeometry(0.71, 0.71, 0.2, 40), new THREE.MeshStandardMaterial({ color: PAL.band, emissive: PAL.band, emissiveIntensity: 0.4, roughness: 0.5 })); band.position.y = 0.16; hat.add(band);
    hat.position.set(0.05, 1.62, 0.1); hat.rotation.z = -0.13; headPivot.add(hat);
    let blink = 0, nextBlink = 1.6;
    return {
      setJaw(v) { jaw.rotation.x = -v * 0.5; },
      tick(t) { nextBlink -= 1 / 60; if (nextBlink <= 0) { blink = 1; nextBlink = 1.8 + Math.random() * 3; }
        if (blink > 0) blink = Math.max(0, blink - 0.14); const ey = 1.05 * (1 - 0.82 * blink); eyeL.scale.y = ey; eyeR.scale.y = ey; }
    };
  }

  window.Caine3D = { mount, hasWebGL };
})();
