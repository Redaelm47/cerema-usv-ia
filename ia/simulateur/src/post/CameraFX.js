import * as THREE from 'three';
import { FullScreenQuad } from 'three/addons/postprocessing/Pass.js';

// Camera model: HDR scene -> auto exposure -> physically motivated bloom (lens
// glare) -> lens (distortion, lateral chromatic aberration, vignetting) -> AgX
// film response -> sensor noise. Aims at the look of a real marine camera.

const vs = /* glsl */ `
precision highp float;
in vec3 position;
in vec2 uv;
out vec2 vUv;
void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`;

const downFS = /* glsl */ `
precision highp float;
uniform sampler2D uSrc;
uniform vec2 uTexel;
uniform float uFirst;
uniform float uExposure;
uniform float uThreshold;
in vec2 vUv;
out vec4 fragColor;
float luma(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }
vec3 karis(vec3 c) { return c / (1.0 + luma(c)); }
void main() {
  vec2 t = uTexel;
  vec3 a = texture(uSrc, vUv + t * vec2(-2, 2)).rgb, b = texture(uSrc, vUv + t * vec2(0, 2)).rgb, c = texture(uSrc, vUv + t * vec2(2, 2)).rgb;
  vec3 d = texture(uSrc, vUv + t * vec2(-2, 0)).rgb, e = texture(uSrc, vUv).rgb, f = texture(uSrc, vUv + t * vec2(2, 0)).rgb;
  vec3 g = texture(uSrc, vUv + t * vec2(-2, -2)).rgb, h = texture(uSrc, vUv + t * vec2(0, -2)).rgb, i = texture(uSrc, vUv + t * vec2(2, -2)).rgb;
  vec3 j = texture(uSrc, vUv + t * vec2(-1, 1)).rgb, k = texture(uSrc, vUv + t * vec2(1, 1)).rgb;
  vec3 l = texture(uSrc, vUv + t * vec2(-1, -1)).rgb, m = texture(uSrc, vUv + t * vec2(1, -1)).rgb;
  vec3 col;
  if (uFirst > 0.5) {
    // Karis average on the first level kills sun-glint fireflies
    vec3 g0 = karis((j + k + l + m) * 0.25) * 0.5;
    vec3 g1 = karis((a + b + d + e) * 0.25) * 0.125;
    vec3 g2 = karis((b + c + e + f) * 0.25) * 0.125;
    vec3 g3 = karis((d + e + g + h) * 0.25) * 0.125;
    vec3 g4 = karis((e + f + h + i) * 0.25) * 0.125;
    col = g0 + g1 + g2 + g3 + g4;
    col = col / max(1.0 - luma(col), 1e-3);
    col *= uExposure;
    float br = luma(col);
    float soft = clamp(br - uThreshold * 0.5, 0.0, uThreshold);
    soft = soft * soft / (4.0 * uThreshold + 1e-4);
    col *= max(soft, br - uThreshold) / max(br, 1e-4);
  } else {
    col = e * 0.125 + (a + c + g + i) * 0.03125 + (b + d + f + h) * 0.0625 + (j + k + l + m) * 0.125;
  }
  fragColor = vec4(col, 1.0);
}`;

const upFS = /* glsl */ `
precision highp float;
uniform sampler2D uSrc;   // lower (smaller) level, already upsampled chain
uniform sampler2D uBase;  // this level's downsample
uniform vec2 uTexel;
uniform float uRadius;
in vec2 vUv;
out vec4 fragColor;
void main() {
  vec2 t = uTexel * uRadius;
  vec3 s = texture(uSrc, vUv + vec2(-t.x, t.y)).rgb + texture(uSrc, vUv + vec2(0, t.y)).rgb * 2.0 + texture(uSrc, vUv + vec2(t.x, t.y)).rgb
         + texture(uSrc, vUv + vec2(-t.x, 0)).rgb * 2.0 + texture(uSrc, vUv).rgb * 4.0 + texture(uSrc, vUv + vec2(t.x, 0)).rgb * 2.0
         + texture(uSrc, vUv + vec2(-t.x, -t.y)).rgb + texture(uSrc, vUv + vec2(0, -t.y)).rgb * 2.0 + texture(uSrc, vUv + vec2(t.x, -t.y)).rgb;
  fragColor = vec4(texture(uBase, vUv).rgb + s / 16.0, 1.0);
}`;

const lumFS = /* glsl */ `
precision highp float;
uniform sampler2D uSrc;
in vec2 vUv;
out vec4 fragColor;
void main() {
  // 4x4 taps per output texel, log-average with centre weighting
  vec2 px = 1.0 / vec2(64.0, 36.0);
  float s = 0.0;
  for (int y = 0; y < 4; y++) for (int x = 0; x < 4; x++) {
    vec2 o = (vec2(x, y) + 0.5) / 4.0 - 0.5;
    vec3 c = texture(uSrc, vUv + o * px).rgb;
    float l = dot(c, vec3(0.2126, 0.7152, 0.0722));
    s += log(max(l, 1e-4));
  }
  fragColor = vec4(s / 16.0, 0.0, 0.0, 1.0);
}`;

const finalFS = /* glsl */ `
precision highp float;
uniform sampler2D uScene;
uniform sampler2D uBloom;
uniform float uExposure;
uniform float uBloomStrength;
uniform float uTime;
uniform vec2 uRes;
uniform float uGrain;
uniform float uCA;
uniform float uDistort;
uniform float uVignette;
uniform float uSaturation;
uniform float uContrast;
uniform vec3 uWhiteBalance;
uniform vec4 uDrops[32];
uniform int uDropCount;
uniform float uWash;
uniform float uRainLens;  // rain hitting the camera dome, 0..1
uniform float uFog;       // condensation (buée) inside / on the dome, 0..1
in vec2 vUv;
out vec4 fragColor;

vec3 agxContrast(vec3 x) {
  vec3 x2 = x * x; vec3 x4 = x2 * x2;
  return 15.5 * x4 * x2 - 40.14 * x4 * x + 31.96 * x4 - 6.868 * x2 * x + 0.4298 * x2 + 0.1191 * x - 0.00232;
}
vec3 agx(vec3 v) {
  const mat3 m = mat3(0.842479062253094, 0.0423282422610123, 0.0423756549057051,
                      0.0784335999999992, 0.878468636469772, 0.0784336,
                      0.0792237451477643, 0.0791661274605434, 0.879142973793104);
  const float lo = -12.47393, hi = 4.026069;
  v = m * v;
  v = clamp(log2(max(v, vec3(1e-10))), lo, hi);
  v = (v - lo) / (hi - lo);
  return agxContrast(v);
}
vec3 agxLook(vec3 v) {
  float l = dot(v, vec3(0.2126, 0.7152, 0.0722));
  v = pow(max(v, 0.0), vec3(uContrast));
  return l + uSaturation * (v - l);
}
vec3 agxEotf(vec3 v) {
  const mat3 mi = mat3(1.19687900512017, -0.0528968517574562, -0.0529716355144438,
                       -0.0980208811401368, 1.15190312990417, -0.0980434501171241,
                       -0.0990297440797205, -0.0989611768448433, 1.15107367264116);
  v = mi * v;
  return pow(max(v, 0.0), vec3(2.2));
}
vec3 toSRGB(vec3 c) {
  c = clamp(c, 0.0, 1.0);
  return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(0.0031308, c));
}
float hash(vec3 p) { p = fract(p * 0.1031); p += dot(p, p.zyx + 31.32); return fract((p.x + p.y) * p.z); }
float wh(vec2 p) { return hash(vec3(p, 7.7)); }
float wn(vec2 p) { vec2 i = floor(p), f = fract(p); vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(wh(i), wh(i + vec2(1.0, 0.0)), u.x), mix(wh(i + vec2(0.0, 1.0)), wh(i + vec2(1.0, 1.0)), u.x), u.y); }

vec2 rlHash2(vec2 p) { vec3 p3 = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973)); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.xx + p3.yz) * p3.zy); }

// Raindrops stuck on the dome, one layer of cells (one drop per cell at most). Returns the
// refraction offset (a drop shows an inverted, magnified piece of the scene) and its coverage.
vec3 rainBeads(vec2 p, float cell, float t, float density, float seed) {
  vec2 q = p / cell + seed;
  vec2 id = floor(q);
  vec2 f = fract(q) - 0.5;
  vec2 h = rlHash2(id + seed * 7.13);
  if (h.x > density) return vec3(0.0);
  // a drop lands, stays a while, dries; then the cell gets a new one somewhere else
  float rate = 0.045 + 0.07 * h.y;
  float cyc = t * rate + h.x * 13.0;
  float life = fract(cyc);
  vec2 g = rlHash2(id + floor(cyc) * 1.37 + 3.3);
  float grow = smoothstep(0.0, 0.02, life) * (1.0 - smoothstep(0.75, 1.0, life));
  vec2 c = (g - 0.5) * 0.55;
  float r = (0.13 + 0.3 * g.x * g.x) * grow;
  vec2 d = f - c;
  d.y *= 1.0 - 0.22 * clamp(d.y / max(r, 1e-3), -1.0, 1.0); // heavier at the bottom
  // never a perfect circle
  float l = length(d) / max(r, 1e-4) * (1.0 + 0.22 * (wn(f * 5.0 + h * 31.0) - 0.5));
  if (l > 1.0) return vec3(0.0);
  // the dome is a few cm from the lens: the drop edge is soft, not a sharp bubble outline
  return vec3(-d * cell * 1.5, smoothstep(1.0, 0.25, l));
}

// Drops running down the dome, with the wet track they leave (clears the fog)
vec4 rainRunners(vec2 p, float t, float density, float aspect) {
  float colW = 0.085;
  float col = floor(p.x / colW);
  vec2 h = rlHash2(vec2(col, 17.0));
  if (h.x > density) return vec4(0.0);
  float speed = 0.05 + 0.11 * h.y;
  float cyc = t * speed + h.x * 5.0;
  float y = 1.25 - fract(cyc) * 1.7;
  vec2 g = rlHash2(vec2(col, floor(cyc)));
  float x = (col + 0.3 + 0.4 * g.x) * colW + sin(p.y * 11.0 + g.y * 6.0) * 0.006;
  float r = 0.009 + 0.012 * g.y;
  vec2 d = vec2(p.x - x, p.y - y);
  d.y *= d.y > 0.0 ? 0.55 : 1.15;
  float l = length(d) / r;
  vec4 res = vec4(0.0);
  if (l < 1.0) res = vec4(-d * 1.5, smoothstep(1.0, 0.25, l), 0.0);
  float above = p.y - y;
  if (above > 0.0) {
    float tr = smoothstep(r * 0.75, r * 0.2, abs(p.x - x)) * (1.0 - smoothstep(0.0, 0.45, above));
    res.w = tr;
    res.xy += vec2(sin(above * 90.0 + g.x * 9.0), 0.0) * 0.0015 * tr;
  }
  return res;
}

float fogNoise(vec2 p) { return wn(p) * 0.6 + wn(p * 2.3 + 7.1) * 0.4; }

vec3 sceneLod(vec2 uv, float lod) {
  // mip-blurred scene, four taps to hide the square shape of the mips
  vec2 o = exp2(lod) / uRes * 0.7;
  return 0.25 * (textureLod(uScene, uv + vec2(o.x, o.y * 0.4), lod).rgb + textureLod(uScene, uv + vec2(-o.x * 0.4, o.y), lod).rgb
              + textureLod(uScene, uv - vec2(o.x, o.y * 0.4), lod).rgb + textureLod(uScene, uv - vec2(-o.x * 0.4, o.y), lod).rgb);
}

void main() {
  vec2 c = vUv - 0.5;
  float aspect = uRes.x / uRes.y;
  vec2 cc = vec2(c.x * aspect, c.y);
  float r2 = dot(cc, cc);
  // barrel distortion of a wide marine camera lens
  vec2 uvD = 0.5 + c * (1.0 + uDistort * r2) / (1.0 + uDistort * 0.25);
  // water drops on the dome: each one is a tiny fish-eye showing a flipped, blurred view
  float dropShade = 1.0, dropHi = 0.0, dropBlur = 0.0;
  for (int i = 0; i < 32; i++) {
    if (i >= uDropCount) break;
    vec4 d = uDrops[i];
    vec2 dv = vec2((vUv.x - d.x) * aspect, vUv.y - d.y);
    float rr = length(dv) / d.z;
    if (rr < 1.0) {
      // the dome is a few cm from the lens: drops are strongly out of focus
      float hgt = sqrt(1.0 - rr * rr);
      vec2 n = dv / d.z;
      float edge = smoothstep(1.0, 0.45, rr);
      vec2 inside = vec2(d.x, d.y) - vec2(n.x / aspect, n.y) * d.z * (1.8 - 0.9 * hgt);
      uvD = mix(uvD, inside, d.w * edge * 0.75);
      dropShade = mix(1.0, 0.9 + 0.12 * hgt, d.w * edge);
      dropHi = pow(max(dot(normalize(n + 1e-4), vec2(-0.55, 0.83)), 0.0), 6.0) * smoothstep(0.3, 0.9, rr) * edge * d.w * 0.25;
      dropBlur = max(dropBlur, d.w * (0.6 + 0.4 * edge));
      break;
    }
  }
  // water film after a wave washed over the dome
  if (uWash > 0.0) {
    // irregular sheet of water draining down the dome
    vec2 q = vUv * vec2(5.0, 2.5) + vec2(0.0, uTime * 0.9);
    vec2 q2 = vUv * vec2(13.0, 6.0) + vec2(uTime * 0.2, uTime * 1.6);
    vec2 w = vec2(wn(q) - 0.5, wn(q + 17.3) - 0.5) * 0.7 + vec2(wn(q2) - 0.5, wn(q2 + 5.1) - 0.5) * 0.3;
    uvD += w * 0.035 * uWash;
    dropBlur = max(dropBlur, uWash * 0.85);
  }
  // rain on the dome: many beads, some running down; they are a few cm from the lens, out of focus
  float rainCov = 0.0, track = 0.0, rim = 0.0;
  if (uRainLens > 0.0) {
    vec2 pr = vec2(vUv.x * aspect, vUv.y);
    float dens = uRainLens;
    vec3 L = rainBeads(pr, 0.05, uTime, 0.2 + 0.6 * dens, 0.0);
    vec3 b2 = rainBeads(pr, 0.03, uTime * 1.2, 0.06 + 0.34 * dens, 4.7);
    vec3 b3 = rainBeads(pr, 0.1, uTime * 0.8, 0.04 + 0.45 * dens * dens, 9.2);
    vec4 rn = rainRunners(pr, uTime, 0.15 + 0.7 * dens, aspect);
    if (b2.z > L.z) L = b2;
    if (b3.z > L.z) L = b3;
    if (rn.z > L.z) L = rn.xyz;
    track = rn.w;
    rainCov = L.z;
    rim = L.z * (1.0 - L.z) * 4.0 * 0.35;
    uvD += vec2(L.x / aspect, L.y) * L.z + vec2(rn.x / aspect, rn.y) * track * (1.0 - L.z);
  }
  // blur: drops and water film are out of focus, condensation scatters the light
  float fogAmt = uFog * (0.55 + 0.45 * fogNoise(vUv * vec2(aspect, 1.0) * 2.5 + uTime * 0.01)) * (0.75 + 0.6 * r2);
  fogAmt *= 1.0 - max(rainCov, track * 0.85);       // water running on the dome wipes the fog away
  float wet = uRainLens * 0.35 * (1.0 - rainCov);    // thin film of water between the drops
  float lod = max(max(dropBlur * 2.6, rainCov * 3.2), fogAmt * 2.2 + wet * 1.0);
  // lateral chromatic aberration grows towards the edges
  vec2 dir = c * uCA * (0.3 + r2);
  vec3 col;
  col.r = textureLod(uScene, uvD + dir, 0.0).r;
  col.g = textureLod(uScene, uvD, 0.0).g;
  col.b = textureLod(uScene, uvD - dir, 0.0).b;
  if (lod > 0.02) col = mix(col, sceneLod(uvD, lod), clamp(lod * 1.4, 0.0, 1.0));
  // condensation: a milky veil that lifts the shadows and washes the contrast out
  if (fogAmt > 0.0) {
    vec3 veil = sceneLod(uvD, 6.0) * 1.08;
    col = mix(col, veil, clamp(fogAmt * 0.55, 0.0, 0.7));
  }
  col *= dropShade;
  col *= 1.0 - rim * 0.25;
  col *= uExposure;
  vec3 bl;
  bl.r = texture(uBloom, uvD + dir * 2.0).r;
  bl.g = texture(uBloom, uvD).g;
  bl.b = texture(uBloom, uvD - dir * 2.0).b;
  col += bl * uBloomStrength;
  col += vec3(dropHi) * 1.5;
  // optical vignetting (cos^4 law, softened)
  float vig = pow(1.0 / (1.0 + r2 * uVignette), 2.0);
  col *= vig;
  col *= uWhiteBalance;
  vec3 m = agxEotf(agxLook(agx(col)));
  // sensor noise: luminance-dependent, stronger in shadows, temporal
  float n = hash(vec3(gl_FragCoord.xy, floor(uTime * 60.0))) + hash(vec3(gl_FragCoord.yx * 1.7, floor(uTime * 60.0) + 7.0)) - 1.0;
  float lum = dot(m, vec3(0.2126, 0.7152, 0.0722));
  m += n * uGrain * (0.35 + 0.65 * (1.0 - sqrt(clamp(lum, 0.0, 1.0)))) * 0.1;
  vec3 s = toSRGB(m);
  // 8-bit dithering
  s += (hash(vec3(gl_FragCoord.xy, uTime)) - 0.5) / 255.0;
  fragColor = vec4(s, 1.0);
}`;

export class CameraFX {
  constructor(renderer) {
    this.renderer = renderer;
    this.hdr = new THREE.WebGLRenderTarget(4, 4, {
      type: THREE.HalfFloatType,
      samples: 4,
      depthBuffer: true,
      // mipmaps give cheap blur levels for the drops, the water film and the condensation
      generateMipmaps: true,
      minFilter: THREE.LinearMipmapLinearFilter,
      magFilter: THREE.LinearFilter,
    });
    this.levels = [];
    this.quad = new FullScreenQuad();
    const raw = (fs, uniforms) =>
      new THREE.RawShaderMaterial({ glslVersion: THREE.GLSL3, vertexShader: vs, fragmentShader: fs, uniforms, depthTest: false, depthWrite: false });
    this.downMat = raw(downFS, {
      uSrc: { value: null }, uTexel: { value: new THREE.Vector2() }, uFirst: { value: 0 },
      uExposure: { value: 1 }, uThreshold: { value: 1.4 },
    });
    this.upMat = raw(upFS, { uSrc: { value: null }, uBase: { value: null }, uTexel: { value: new THREE.Vector2() }, uRadius: { value: 1 } });
    this.lumMat = raw(lumFS, { uSrc: { value: null } });
    this.finalMat = raw(finalFS, {
      uScene: { value: null }, uBloom: { value: null },
      uExposure: { value: 1 }, uBloomStrength: { value: 0.06 },
      uTime: { value: 0 }, uRes: { value: new THREE.Vector2(1, 1) },
      uGrain: { value: 0.14 }, uCA: { value: 0.0035 }, uDistort: { value: 0.06 }, uVignette: { value: 0.55 },
      uSaturation: { value: 1.08 }, uContrast: { value: 1.08 },
      uWhiteBalance: { value: new THREE.Vector3(1, 1, 1) },
      uDrops: { value: Array.from({ length: 32 }, () => new THREE.Vector4()) },
      uDropCount: { value: 0 },
      uWash: { value: 0 },
      uRainLens: { value: 0 },
      uFog: { value: 0 },
    });
    this.lumRT = new THREE.WebGLRenderTarget(64, 36, { type: THREE.FloatType, depthBuffer: false, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter });
    this.lumBuf = new Float32Array(64 * 36 * 4);
    this.lumPending = false;
    this.avgLum = 0.2;
    this.exposure = 1.0;
    this.exposureBias = 0; // EV
    this.autoExposure = true;
    this.manualExposure = 1;
    this.lumTimer = 0;
  }

  setSize(w, h) {
    this.hdr.setSize(w, h);
    for (const l of this.levels) { l.down.dispose(); l.up.dispose(); }
    this.levels = [];
    let lw = Math.max(1, w >> 1), lh = Math.max(1, h >> 1);
    for (let i = 0; i < 7 && lw > 2 && lh > 2; i++) {
      const o = { type: THREE.HalfFloatType, depthBuffer: false, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter, wrapS: THREE.ClampToEdgeWrapping, wrapT: THREE.ClampToEdgeWrapping };
      this.levels.push({ down: new THREE.WebGLRenderTarget(lw, lh, o), up: new THREE.WebGLRenderTarget(lw, lh, o), w: lw, h: lh });
      lw >>= 1; lh >>= 1;
    }
    this.finalMat.uniforms.uRes.value.set(w, h);
  }

  get target() { return this.hdr; }

  _measure(dt) {
    const r = this.renderer;
    this.lumTimer += dt;
    if (this.lumPending || this.lumTimer < 0.2) return;
    this.lumTimer = 0;
    this.quad.material = this.lumMat;
    this.lumMat.uniforms.uSrc.value = this.hdr.texture;
    r.setRenderTarget(this.lumRT);
    this.quad.render(r);
    this.lumPending = true;
    r.readRenderTargetPixelsAsync(this.lumRT, 0, 0, 64, 36, this.lumBuf).then(() => {
      let s = 0, wsum = 0;
      for (let y = 0; y < 36; y++) for (let x = 0; x < 64; x++) {
        const cx = (x + 0.5) / 64 - 0.5, cy = (y + 0.5) / 36 - 0.5;
        const w = Math.exp(-(cx * cx + cy * cy) * 4);
        s += this.lumBuf[(y * 64 + x) * 4] * w; wsum += w;
      }
      const v = Math.exp(s / wsum);
      if (Number.isFinite(v)) this.avgLum = v;
      this.lumPending = false;
    }).catch(() => { this.lumPending = false; });
  }

  render(dt, time) {
    const r = this.renderer;
    const prevAuto = r.autoClear;
    r.autoClear = false;
    this._measure(dt);
    // exposure adaptation (log-domain, ~1 s), like a camera's AE
    const key = 0.16;
    const target = this.autoExposure ? key / Math.max(this.avgLum, 1e-4) : this.manualExposure;
    const biased = target * Math.pow(2, this.exposureBias);
    const k = 1 - Math.exp(-dt * 1.8);
    this.exposure = Math.exp(Math.log(this.exposure) + (Math.log(biased) - Math.log(this.exposure)) * k);

    if (!this.levels.length) { r.autoClear = prevAuto; return; }
    // bloom chain
    let src = this.hdr.texture;
    let sw = this.hdr.width, sh = this.hdr.height;
    this.quad.material = this.downMat;
    this.levels.forEach((l, i) => {
      this.downMat.uniforms.uSrc.value = src;
      this.downMat.uniforms.uTexel.value.set(1 / sw, 1 / sh);
      this.downMat.uniforms.uFirst.value = i === 0 ? 1 : 0;
      this.downMat.uniforms.uExposure.value = this.exposure;
      r.setRenderTarget(l.down);
      this.quad.render(r);
      src = l.down.texture; sw = l.w; sh = l.h;
    });
    this.quad.material = this.upMat;
    let low = this.levels[this.levels.length - 1].down.texture;
    for (let i = this.levels.length - 2; i >= 0; i--) {
      const l = this.levels[i];
      const lower = this.levels[i + 1];
      this.upMat.uniforms.uSrc.value = low;
      this.upMat.uniforms.uBase.value = l.down.texture;
      this.upMat.uniforms.uTexel.value.set(1 / lower.w, 1 / lower.h);
      r.setRenderTarget(l.up);
      this.quad.render(r);
      low = l.up.texture;
    }

    const f = this.finalMat.uniforms;
    f.uScene.value = this.hdr.texture;
    f.uBloom.value = low;
    f.uExposure.value = this.exposure;
    f.uTime.value = time;
    this.quad.material = this.finalMat;
    r.setRenderTarget(null);
    this.quad.render(r);
    r.autoClear = prevAuto;
  }
}
