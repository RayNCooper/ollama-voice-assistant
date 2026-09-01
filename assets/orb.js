// The orb: a shader-displaced icosahedron that breathes with the conversation
// and reacts to live audio amplitude (your voice while listening, the reply
// while speaking). Pure ShaderMaterial — no lights, no post-processing, so it
// stays cheap enough to run alongside ASR/TTS on the same machine.
import * as THREE from "./vendor/three.module.js";
import { SIMPLEX } from "./orb.noise.js";

// Per-state palette: [core, rim]. Indigo is the Olio accent; the states shift
// hue and energy around it so the orb alone tells you what the app is doing.
const PALETTE = {
  loading:   [0x2a2f4a, 0x4b5170],
  idle:      [0x4338ca, 0x6366f1],
  listening: [0x4f46e5, 0x8b9cff],
  thinking:  [0x3f2d8f, 0x7c5cff],
  speaking:  [0x4c1d95, 0xa78bfa],
};

// Geometry bounds, kept in sync with the vertex shader above:
//   shell radius 1.22 + max|noise| (0.16+0.07) * max multiplier (0.40+0.30+1.05)
// The camera is fitted to this so the orb can never clip the canvas edges.
const FOV = 42;
const MAX_RADIUS = 1.22 + 0.23 * 1.75;

const VERT = `
uniform float uTime;
uniform float uAmp;
uniform float uEnergy;
varying float vDisp;
varying vec3 vNormalV;
varying vec3 vPosV;
${SIMPLEX}
void main(){
  // Two octaves at different speeds: a slow swell plus a finer shimmer.
  float n1 = snoise(normal * 1.5 + uTime * 0.22);
  float n2 = snoise(normal * 3.6 - uTime * 0.15);
  float disp = n1 * 0.16 + n2 * 0.07;
  disp *= 0.40 + uEnergy * 0.30 + uAmp * 1.05;
  vec3 p = position + normal * disp;
  vDisp = disp;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  vNormalV = normalize(normalMatrix * normal);
  vPosV = mv.xyz;
  gl_Position = projectionMatrix * mv;
}`;

const FRAG = `
uniform vec3 uCore;
uniform vec3 uRim;
uniform float uAmp;
varying float vDisp;
varying vec3 vNormalV;
varying vec3 vPosV;
void main(){
  vec3 V = normalize(-vPosV);
  // Fresnel rim — bright at glancing angles, so the silhouette glows.
  float fres = pow(1.0 - clamp(dot(normalize(vNormalV), V), 0.0, 1.0), 2.4);
  float ridge = smoothstep(-0.05, 0.22, vDisp);
  vec3 col = mix(uCore, uRim, ridge * 0.65 + fres * 0.75);
  col += uRim * uAmp * 0.5;
  gl_FragColor = vec4(col, 1.0);
}`;

// The outer shell: same displacement, additive, backface-rendered. Cheap glow
// without needing an UnrealBloom pass (which lives in examples/jsm).
const SHELL_FRAG = `
uniform vec3 uRim;
uniform float uAmp;
varying vec3 vNormalV;
varying vec3 vPosV;
varying float vDisp;
void main(){
  vec3 V = normalize(-vPosV);
  float fres = pow(1.0 - clamp(dot(normalize(vNormalV), V), 0.0, 1.0), 3.0);
  float a = fres * (0.30 + uAmp * 0.55);
  gl_FragColor = vec4(uRim, a);
}`;

export function createOrb(canvas) {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  } catch {
    return null; // caller falls back to the CSS orb
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 100);

  const uniforms = {
    uTime:   { value: 0 },
    uAmp:    { value: 0 },
    uEnergy: { value: 0 },
    uCore:   { value: new THREE.Color(PALETTE.loading[0]) },
    uRim:    { value: new THREE.Color(PALETTE.loading[1]) },
  };

  const geo = new THREE.IcosahedronGeometry(1, 64);
  const core = new THREE.Mesh(
    geo,
    new THREE.ShaderMaterial({ uniforms, vertexShader: VERT, fragmentShader: FRAG })
  );
  scene.add(core);

  const shell = new THREE.Mesh(
    new THREE.IcosahedronGeometry(1.22, 32),
    new THREE.ShaderMaterial({
      uniforms,
      vertexShader: VERT,
      fragmentShader: SHELL_FRAG,
      transparent: true,
      blending: THREE.AdditiveBlending,
      side: THREE.BackSide,
      depthWrite: false,
    })
  );
  scene.add(shell);

  // Targets are eased toward every frame so state changes glide rather than snap.
  let ampTarget = 0, amp = 0;
  let energyTarget = 0, energy = 0;
  const coreTarget = new THREE.Color(PALETTE.loading[0]);
  const rimTarget  = new THREE.Color(PALETTE.loading[1]);

  function resize() {
    const w = canvas.clientWidth || 1;
    const h = canvas.clientHeight || 1;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    // Fit the camera to whichever axis is tighter, so a non-square canvas
    // (narrow window, odd aspect) still frames the orb whole.
    const vFov = (FOV * Math.PI) / 180;
    const hFov = 2 * Math.atan(Math.tan(vFov / 2) * camera.aspect);
    // A sphere's silhouette subtends asin(R/d), not atan(R/d) — using tan here
    // would still let the widest bulges touch the edge.
    const distV = MAX_RADIUS / Math.sin(vFov / 2);
    const distH = MAX_RADIUS / Math.sin(hFov / 2);
    camera.position.z = Math.max(distV, distH) * 1.06; // 6% breathing room
    camera.updateProjectionMatrix();
  }
  resize();
  const ro = new ResizeObserver(resize);
  ro.observe(canvas);

  const clock = new THREE.Clock();
  let raf = 0;
  function tick() {
    raf = requestAnimationFrame(tick);
    const dt = Math.min(clock.getDelta(), 0.05);
    // Fast attack, slow release: the orb jumps on a syllable and settles gently.
    const k = ampTarget > amp ? 1 - Math.exp(-dt * 18) : 1 - Math.exp(-dt * 5);
    amp += (ampTarget - amp) * k;
    energy += (energyTarget - energy) * (1 - Math.exp(-dt * 3));
    uniforms.uAmp.value = amp;
    uniforms.uEnergy.value = energy;
    uniforms.uTime.value += dt * (0.6 + energy * 0.9 + amp * 1.6);
    uniforms.uCore.value.lerp(coreTarget, 1 - Math.exp(-dt * 4));
    uniforms.uRim.value.lerp(rimTarget, 1 - Math.exp(-dt * 4));
    core.rotation.y += dt * 0.12;
    core.rotation.x += dt * 0.045;
    shell.rotation.copy(core.rotation);
    renderer.render(scene, camera);
  }
  tick();

  return {
    setAmp(v) { ampTarget = Math.max(0, Math.min(1, v)); },
    setState(name) {
      const p = PALETTE[name] || PALETTE.idle;
      coreTarget.setHex(p[0]);
      rimTarget.setHex(p[1]);
      energyTarget = name === "thinking" ? 0.85 : name === "listening" ? 0.5 : name === "speaking" ? 0.7 : 0.15;
      if (name !== "listening" && name !== "speaking") ampTarget = 0;
    },
    dispose() { cancelAnimationFrame(raf); ro.disconnect(); renderer.dispose(); },
  };
}
