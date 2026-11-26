import * as THREE from 'three';
import { FullScreenQuad } from 'three/addons/postprocessing/Pass.js';
import { buildInitialSpectrum } from './spectrum.js';

// GPU Tessendorf ocean: 3 cascades of 256x256 inverse FFTs (Stockham radix-2,
// two complex transforms per RGBA texel, two textures per pass via MRT).
// Outputs per cascade (half float, mipmapped, repeat-wrapped):
//   disp  = (lambda*Dx, h, lambda*Dz, foam)
//   deriv = (dh/dx, dh/dz, lambda*dDx/dx, lambda*dDz/dz)
//   slope2= (dh/dx^2, dh/dz^2, lambda*dDx/dz, jacobian)

const N = 256;
const LOG2N = 8;

const vs = /* glsl */ `
precision highp float;
in vec3 position;
in vec2 uv;
out vec2 vUv;
void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`;

const common = /* glsl */ `
precision highp float;
precision highp sampler2D;
#define PI 3.141592653589793
vec2 cmul(vec2 a, vec2 b) { return vec2(a.x * b.x - a.y * b.y, a.x * b.y + a.y * b.x); }
vec2 mulI(vec2 a) { return vec2(-a.y, a.x); }
`;

const spectrumFS = /* glsl */ `${common}
uniform sampler2D h0Tex;
uniform float time;
uniform vec3 Ls;
uniform float repeatT;
in vec2 vUv;
out vec4 o0;
void main() {
  vec2 pxa = floor(gl_FragCoord.xy);
  float c = floor(pxa.x / ${N}.0);
  vec2 px = vec2(pxa.x - c * ${N}.0, pxa.y);
  float L = c < 0.5 ? Ls.x : (c < 1.5 ? Ls.y : Ls.z);
  vec2 n = px - step(${N / 2}.0, px) * ${N}.0;
  vec2 k = 2.0 * PI * n / L;
  float kl = length(k);
  if (kl < 1e-6) { o0 = vec4(0.0); return; }
  vec4 h0 = texelFetch(h0Tex, ivec2(pxa), 0);
  float w0 = 2.0 * PI / repeatT;
  float omega = floor(sqrt(9.81 * kl) / w0) * w0;
  float ph = omega * time;
  vec2 e = vec2(cos(ph), sin(ph));
  // h0(k) e^{-i w t} + conj(h0(-k)) e^{+i w t}  -> waves travel along +k
  vec2 h = cmul(h0.xy, vec2(e.x, -e.y)) + cmul(h0.zw, e);
  vec2 ih = mulI(h);
  vec2 kn = k / kl;
  vec2 Dx = -kn.x * ih;
  vec2 Dz = -kn.y * ih;
  vec2 Dy = h;
  o0 = vec4(Dx + mulI(Dy), Dz);
}`;

const fftFS = /* glsl */ `${common}
uniform sampler2D src0;
uniform float subSize;
uniform float horizontal;
in vec2 vUv;
out vec4 o0;
void main() {
  vec2 pxa = floor(gl_FragCoord.xy);
  float c = floor(pxa.x / ${N}.0);
  int off = int(c) * ${N};
  vec2 px = vec2(pxa.x - c * ${N}.0, pxa.y);
  float index = horizontal > 0.5 ? px.x : px.y;
  float half_ = subSize * 0.5;
  float evenIndex = floor(index / subSize) * half_ + mod(index, half_);
  ivec2 ce, co;
  if (horizontal > 0.5) {
    ce = ivec2(off + int(evenIndex), int(px.y));
    co = ivec2(off + int(evenIndex) + ${N / 2}, int(px.y));
  } else {
    ce = ivec2(int(pxa.x), int(evenIndex));
    co = ivec2(int(pxa.x), int(evenIndex) + ${N / 2});
  }
  float ang = 2.0 * PI * index / subSize;
  vec2 tw = vec2(cos(ang), sin(ang));
  vec4 e0 = texelFetch(src0, ce, 0), d0 = texelFetch(src0, co, 0);
  o0 = vec4(e0.xy + cmul(tw, d0.xy), e0.zw + cmul(tw, d0.zw));
}`;

const assembleFS = /* glsl */ `${common}
uniform sampler2D src0;
uniform sampler2D prevDisp;
uniform float colOffset;
uniform float texelM;   // metres per texel of this cascade
uniform float lambda;
uniform float dt;
uniform float foamDecay;
uniform float foamBias;
uniform float foamGain;
in vec2 vUv;
layout(location = 0) out vec4 oDisp;
layout(location = 1) out vec4 oDeriv;
layout(location = 2) out vec4 oSlope2;
vec3 D(ivec2 p) {
  p = (p + ${N}) % ${N};
  vec4 a = texelFetch(src0, p + ivec2(int(colOffset), 0), 0);
  return vec3(a.x, a.y, a.z); // Dx, Dy(h), Dz
}
void main() {
  ivec2 p = ivec2(gl_FragCoord.xy);
  vec3 c = D(p);
  vec3 r = D(p + ivec2(1, 0)), l = D(p - ivec2(1, 0)), u = D(p + ivec2(0, 1)), d = D(p - ivec2(0, 1));
  float inv = 1.0 / (2.0 * texelM);
  float dYdx = (r.y - l.y) * inv, dYdz = (u.y - d.y) * inv;
  float dXdx = (r.x - l.x) * inv, dZdz = (u.z - d.z) * inv;
  float dXdz = (u.x - d.x) * inv;
  float jxx = 1.0 + lambda * dXdx;
  float jzz = 1.0 + lambda * dZdz;
  float jxz = lambda * dXdz;
  float J = jxx * jzz - jxz * jxz;
  float prev = texelFetch(prevDisp, p, 0).w;
  float foamNow = clamp((foamBias - J) * foamGain, 0.0, 1.0);
  float foam = max(prev * exp(-dt / foamDecay), foamNow);
  oDisp = vec4(lambda * c.x, c.y, lambda * c.z, foam);
  oDeriv = vec4(dYdx, dYdz, lambda * dXdx, lambda * dZdz);
  oSlope2 = vec4(dYdx * dYdx, dYdz * dYdz, jxz, J);
}`;

function makeRT(count, type, mip, width = N) {
  const rt = new THREE.WebGLRenderTarget(width, N, {
    count,
    type,
    format: THREE.RGBAFormat,
    depthBuffer: false,
    stencilBuffer: false,
    magFilter: mip ? THREE.LinearFilter : THREE.NearestFilter,
    minFilter: mip ? THREE.LinearMipmapLinearFilter : THREE.NearestFilter,
    wrapS: THREE.RepeatWrapping,
    wrapT: THREE.RepeatWrapping,
    generateMipmaps: mip,
  });
  for (const t of rt.textures) {
    t.generateMipmaps = mip;
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.minFilter = mip ? THREE.LinearMipmapLinearFilter : THREE.NearestFilter;
    t.magFilter = mip ? THREE.LinearFilter : THREE.NearestFilter;
    if (mip) t.anisotropy = 8;
  }
  return rt;
}

export class OceanFFT {
  constructor(renderer, sea) {
    this.renderer = renderer;
    this.size = N;
    this.sea = { ...sea };
    // patch sizes (m). Band limits avoid double counting between cascades.
    this.lengths = [550, 97, 17.3];
    const b1 = ((2 * Math.PI) / this.lengths[1]) * 6;
    const b2 = ((2 * Math.PI) / this.lengths[2]) * 6;
    this.bands = [[0.0001, b1], [b1, b2], [b2, 9999]];
    this.repeatT = 400;
    this.time = 0;

    const raw = (fs) => new THREE.RawShaderMaterial({
      glslVersion: THREE.GLSL3,
      vertexShader: vs,
      fragmentShader: fs,
      uniforms: {},
      depthTest: false,
      depthWrite: false,
    });

    this.specMat = raw(spectrumFS);
    this.specMat.uniforms = { h0Tex: { value: null }, time: { value: 0 }, Ls: { value: new THREE.Vector3(...this.lengths) }, repeatT: { value: this.repeatT } };
    this.fftMat = raw(fftFS);
    this.fftMat.uniforms = { src0: { value: null }, subSize: { value: 2 }, horizontal: { value: 1 } };
    this.asmMat = raw(assembleFS);
    this.asmMat.uniforms = {
      src0: { value: null }, prevDisp: { value: null }, colOffset: { value: 0 }, texelM: { value: 1 },
      lambda: { value: 0.9 }, dt: { value: 0.016 },
      foamDecay: { value: 2.6 }, foamBias: { value: 0.62 }, foamGain: { value: 2.2 },
    };
    this.quad = new FullScreenQuad(this.specMat);

    this.ping = makeRT(1, THREE.FloatType, false, N * 3);
    this.pong = makeRT(1, THREE.FloatType, false, N * 3);
    this.h0 = null;
    this.cascades = this.lengths.map((L, i) => ({
      L,
      out: [makeRT(3, THREE.HalfFloatType, true), makeRT(3, THREE.HalfFloatType, true)],
      cur: 0,
      band: this.bands[i],
    }));
    this.rebuildSpectrum();
  }

  setSea(sea) {
    this.sea = { ...this.sea, ...sea };
    this.rebuildSpectrum();
  }

  rebuildSpectrum() {
    const s = this.sea;
    this.asmMat.uniforms.lambda.value = s.choppiness ?? 0.9;
    // stronger wind -> more whitecaps
    const w = s.windSpeed;
    this.asmMat.uniforms.foamBias.value = THREE.MathUtils.clamp(0.3 + (w - 6) * 0.04, 0.15, 0.85);
    const packed = new Float32Array(N * 3 * N * 4);
    this.cascades.forEach((c, i) => {
      const data = buildInitialSpectrum(N, c.L, c.band[0], c.band[1], s, 1337 + i * 7919);
      for (let y = 0; y < N; y++) packed.set(data.subarray(y * N * 4, (y + 1) * N * 4), (y * N * 3 + i * N) * 4);
    });
    if (this.h0) this.h0.dispose();
    this.h0 = new THREE.DataTexture(packed, N * 3, N, THREE.RGBAFormat, THREE.FloatType);
    this.h0.minFilter = this.h0.magFilter = THREE.NearestFilter;
    this.h0.needsUpdate = true;
  }

  update(dt) {
    const r = this.renderer;
    this.time = (this.time + dt) % this.repeatT;
    const prevRT = r.getRenderTarget();
    const prevAuto = r.autoClear;
    r.autoClear = false;
    // spectrum for the 3 cascades at once (packed side by side)
    this.quad.material = this.specMat;
    this.specMat.uniforms.h0Tex.value = this.h0;
    this.specMat.uniforms.time.value = this.time;
    r.setRenderTarget(this.ping);
    this.quad.render(r);
    // 2D IFFT of all cascades together
    this.quad.material = this.fftMat;
    let src = this.ping, dst = this.pong;
    for (let pass = 0; pass < 2 * LOG2N; pass++) {
      const horizontal = pass < LOG2N;
      const stage = horizontal ? pass : pass - LOG2N;
      this.fftMat.uniforms.src0.value = src.textures[0];
      this.fftMat.uniforms.subSize.value = 2 ** (stage + 1);
      this.fftMat.uniforms.horizontal.value = horizontal ? 1 : 0;
      r.setRenderTarget(dst);
      this.quad.render(r);
      [src, dst] = [dst, src];
    }
    // assemble + foam, one cascade at a time into its own mipmapped textures
    this.quad.material = this.asmMat;
    this.cascades.forEach((c, i) => {
      const prev = c.out[c.cur];
      const next = c.out[1 - c.cur];
      this.asmMat.uniforms.src0.value = src.textures[0];
      this.asmMat.uniforms.texelM.value = c.L / N;
      this.asmMat.uniforms.prevDisp.value = prev.textures[0];
      this.asmMat.uniforms.colOffset.value = i * N;
      this.asmMat.uniforms.dt.value = Math.min(dt, 0.1);
      r.setRenderTarget(next);
      this.quad.render(r);
      c.cur = 1 - c.cur;
    });
    r.setRenderTarget(prevRT);
    r.autoClear = prevAuto;
  }

  /** textures of the current frame for cascade i */
  tex(i) {
    const c = this.cascades[i];
    const t = c.out[c.cur].textures;
    return { disp: t[0], deriv: t[1], slope2: t[2] };
  }
}
