import * as THREE from 'three';
import { FullScreenQuad } from 'three/addons/postprocessing/Pass.js';

// World-anchored wake field around the camera: turbulent foam trails behind
// hulls, bow-wave foam, and surface disturbance that roughens the water.
// r = foam, g/b = slope perturbation, a = disturbance.

const RES = 1024;
const MAXE = 32;

export class WakeSystem {
  constructor(renderer, size = 900) {
    this.renderer = renderer;
    this.size = size;
    this.texel = size / RES;
    const o = { type: THREE.HalfFloatType, depthBuffer: false, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter, wrapS: THREE.ClampToEdgeWrapping, wrapT: THREE.ClampToEdgeWrapping };
    this.rt = [new THREE.WebGLRenderTarget(RES, RES, o), new THREE.WebGLRenderTarget(RES, RES, o)];
    this.cur = 0;
    this.origin = new THREE.Vector2(0, 0);
    this.shift = new THREE.Vector2();
    this.emitters = [];
    this.seg = Array.from({ length: MAXE }, () => new THREE.Vector4());
    this.prm = Array.from({ length: MAXE }, () => new THREE.Vector4());
    this.mat = new THREE.RawShaderMaterial({
      glslVersion: THREE.GLSL3,
      uniforms: {
        uPrev: { value: null }, uShift: { value: this.shift }, uOrigin: { value: this.origin },
        uSize: { value: size }, uDt: { value: 0.016 }, uTime: { value: 0 },
        uSeg: { value: this.seg }, uPrm: { value: this.prm }, uCount: { value: 0 },
      },
      vertexShader: /* glsl */ `
        precision highp float;
        in vec3 position; in vec2 uv; out vec2 vUv;
        void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`,
      fragmentShader: /* glsl */ `
        precision highp float;
        uniform sampler2D uPrev;
        uniform vec2 uShift;
        uniform vec2 uOrigin;
        uniform float uSize;
        uniform float uDt;
        uniform float uTime;
        uniform vec4 uSeg[${MAXE}];
        uniform vec4 uPrm[${MAXE}];
        uniform int uCount;
        in vec2 vUv;
        out vec4 fragColor;
        float hash12(vec2 p) { vec3 p3 = fract(vec3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }
        float vnoise(vec2 p) { vec2 i = floor(p), f = fract(p); vec2 u = f * f * (3.0 - 2.0 * f);
          return mix(mix(hash12(i), hash12(i + vec2(1, 0)), u.x), mix(hash12(i + vec2(0, 1)), hash12(i + vec2(1, 1)), u.x), u.y); }
        void main() {
          vec2 px = 1.0 / vec2(${RES}.0);
          vec2 uv = vUv + uShift;
          vec4 c = vec4(0.0);
          vec4 nr = vec4(0.0), nl = vec4(0.0), nu = vec4(0.0), nd = vec4(0.0);
          if (all(greaterThan(uv, px)) && all(lessThan(uv, 1.0 - px))) {
            nr = texture(uPrev, uv + vec2(px.x, 0)); nl = texture(uPrev, uv - vec2(px.x, 0));
            nu = texture(uPrev, uv + vec2(0, px.y)); nd = texture(uPrev, uv - vec2(0, px.y));
            vec4 m = texture(uPrev, uv);
            c = mix(m, (nr + nl + nu + nd) * 0.25, 0.07); // slow spreading
            c.r *= exp(-uDt / 22.0);   // foam lifetime
            c.a *= exp(-uDt / 70.0);   // the calm turbulent track lasts much longer
          }
          vec2 w = uOrigin + vUv * uSize;
          float tex = vnoise(w * 0.9 + uTime * 0.05) * 0.6 + vnoise(w * 2.7) * 0.4;
          for (int i = 0; i < ${MAXE}; i++) {
            if (i >= uCount) break;
            vec2 a = uSeg[i].xy, b = uSeg[i].zw;
            vec2 ab = b - a;
            float t = clamp(dot(w - a, ab) / max(dot(ab, ab), 1e-6), 0.0, 1.0);
            float d = length(w - (a + ab * t));
            float hw = uPrm[i].x;
            float k = 1.0 - smoothstep(hw * 0.35, hw, d);
            float add = k * uPrm[i].y * uDt * (0.55 + 0.9 * tex);
            c.r = min(c.r + add, 1.6);
            c.a = min(c.a + k * uPrm[i].z * uDt, 2.0);
          }
          // slope perturbation from the disturbance gradient + chaotic small scale ripples
          float dx = nr.a - nl.a;
          float dz = nu.a - nd.a;
          vec2 rip = vec2(vnoise(w * 1.7 + uTime * 0.7), vnoise(w * 1.7 - uTime * 0.6 + 13.0)) - 0.5;
          c.gb = vec2(dx, dz) * 0.35 + rip * clamp(c.a, 0.0, 1.0) * 0.18;
          fragColor = c;
        }`,
      depthTest: false,
      depthWrite: false,
    });
    this.quad = new FullScreenQuad(this.mat);
  }

  /** emitters: [{a:[x,z], b:[x,z], halfWidth, foam, disturb}] (world metres) */
  update(dt, time, center, emitters) {
    // snap origin to the texel grid around the camera
    const nx = Math.floor((center.x - this.size / 2) / this.texel) * this.texel;
    const nz = Math.floor((center.z - this.size / 2) / this.texel) * this.texel;
    this.shift.set((nx - this.origin.x) / this.size, (nz - this.origin.y) / this.size);
    this.origin.set(nx, nz);
    // only emitters that touch the wake area
    const m = 60, x0 = nx - m, x1 = nx + this.size + m, z0 = nz - m, z1 = nz + this.size + m;
    const inside = emitters.filter((e) => Math.max(e.a[0], e.b[0]) > x0 && Math.min(e.a[0], e.b[0]) < x1 && Math.max(e.a[1], e.b[1]) > z0 && Math.min(e.a[1], e.b[1]) < z1);
    const n = Math.min(inside.length, MAXE);
    for (let i = 0; i < n; i++) {
      const e = inside[i];
      this.seg[i].set(e.a[0], e.a[1], e.b[0], e.b[1]);
      this.prm[i].set(e.halfWidth, e.foam, e.disturb, 0);
    }
    const u = this.mat.uniforms;
    u.uCount.value = n;
    u.uDt.value = Math.min(dt, 0.1);
    u.uTime.value = time;
    u.uPrev.value = this.rt[this.cur].texture;
    const r = this.renderer;
    const prev = r.getRenderTarget();
    r.setRenderTarget(this.rt[1 - this.cur]);
    this.quad.render(r);
    r.setRenderTarget(prev);
    this.cur = 1 - this.cur;
  }

  get texture() { return this.rt[this.cur].texture; }
  get rect() { return new THREE.Vector3(this.origin.x, this.origin.y, this.size); }
}
