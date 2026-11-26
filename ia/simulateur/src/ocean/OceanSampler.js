import * as THREE from 'three';
import { FullScreenQuad } from 'three/addons/postprocessing/Pass.js';

// Reads the simulated sea surface back to the CPU (asynchronously) at a set of
// world points, so hulls float on the same waves that are rendered.
// The choppy displacement is inverted with a fixed-point iteration so the
// returned height is the surface height *at* the requested x,z.

const MAX = 256;

export class OceanSampler {
  constructor(renderer, fft) {
    this.renderer = renderer;
    this.fft = fft;
    this.points = new Float32Array(MAX * 4);
    this.pointTex = new THREE.DataTexture(this.points, MAX, 1, THREE.RGBAFormat, THREE.FloatType);
    this.pointTex.minFilter = this.pointTex.magFilter = THREE.NearestFilter;
    this.rt = new THREE.WebGLRenderTarget(MAX, 1, { type: THREE.FloatType, depthBuffer: false, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter });
    this.out = new Float32Array(MAX * 4);
    this.results = new Float32Array(MAX * 4);
    this.count = 0;
    this.pending = false;
    this.slots = [];
    this.mat = new THREE.RawShaderMaterial({
      glslVersion: THREE.GLSL3,
      uniforms: {
        uPts: { value: this.pointTex },
        uDisp0: { value: null }, uDisp1: { value: null }, uDisp2: { value: null },
        uL: { value: new THREE.Vector3(...fft.lengths) },
        uSeaLevel: { value: 0 },
      },
      vertexShader: /* glsl */ `
        precision highp float;
        in vec3 position;
        void main() { gl_Position = vec4(position.xy, 0.0, 1.0); }`,
      fragmentShader: /* glsl */ `
        precision highp float;
        uniform sampler2D uPts;
        uniform sampler2D uDisp0; uniform sampler2D uDisp1; uniform sampler2D uDisp2;
        uniform vec3 uL;
        uniform float uSeaLevel;
        out vec4 fragColor;
        vec3 disp(vec2 xz, float lod) {
          return textureLod(uDisp0, xz / uL.x, lod).xyz + textureLod(uDisp1, xz / uL.y, lod).xyz + textureLod(uDisp2, xz / uL.z, lod).xyz;
        }
        void main() {
          vec4 p = texelFetch(uPts, ivec2(gl_FragCoord.x, 0), 0);
          float lod = p.z; // smoothing (larger hulls ignore short waves)
          vec2 x0 = p.xy;
          for (int i = 0; i < 4; i++) { vec3 d = disp(x0, lod); x0 = p.xy - d.xz; }
          vec3 d = disp(x0, lod);
          fragColor = vec4(uSeaLevel + d.y, d.x, d.z, 1.0);
        }`,
      depthTest: false,
      depthWrite: false,
    });
    this.quad = new FullScreenQuad(this.mat);
  }

  /** register n points, returns a slot id; positions updated via setPoint */
  alloc(n) {
    this.free = this.free || {};
    const list = this.free[n];
    if (list && list.length) return list.pop();
    const start = this.count;
    this.count += n;
    if (this.count > MAX) { this.count -= n; return -1; }
    return start;
  }

  release(start, n) {
    if (start < 0) return;
    this.free = this.free || {};
    (this.free[n] = this.free[n] || []).push(start);
  }

  setPoint(i, x, z, lod = 0) {
    this.points[i * 4] = x;
    this.points[i * 4 + 1] = z;
    this.points[i * 4 + 2] = lod;
  }

  height(i) { return this.results[i * 4]; }

  update(seaLevel) {
    this._n = (this._n || 0) + 1;
    if (this.pending || this.count === 0) return;
    for (let i = 0; i < 3; i++) this.mat.uniforms['uDisp' + i].value = this.fft.tex(i).disp;
    this.mat.uniforms.uSeaLevel.value = seaLevel;
    this.pointTex.needsUpdate = true;
    const r = this.renderer;
    const prev = r.getRenderTarget();
    r.setRenderTarget(this.rt);
    this.quad.render(r);
    r.setRenderTarget(prev);
    this.pending = true;
    r.readRenderTargetPixelsAsync(this.rt, 0, 0, MAX, 1, this.out)
      .then(() => { this.results.set(this.out); this.pending = false; })
      .catch(() => { this.pending = false; });
  }
}
