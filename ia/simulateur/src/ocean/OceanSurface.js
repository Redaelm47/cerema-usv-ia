import * as THREE from 'three';
import { atmoParsGLSL } from '../sky/atmosphereGLSL.js';
import { cloudParsGLSL } from '../sky/cloudsGLSL.js';
import { subgridSlopeVariance } from './spectrum.js';
import { rainRipplesGLSL } from '../fx/Rain.js';

export const EARTH_CURV = 1 / (2 * 6371000 * (7 / 6)); // with standard refraction

function buildRadialGrid(segments, rings, rMax, s0) {
  // find growth q so that rings reach rMax
  let lo = 1e-4, hi = 0.2;
  for (let i = 0; i < 60; i++) {
    const q = (lo + hi) / 2;
    const r = (s0 * (Math.pow(1 + q, rings) - 1)) / q;
    if (r > rMax) hi = q; else lo = q;
  }
  const q = (lo + hi) / 2;
  const pos = new Float32Array((1 + rings * segments) * 3);
  pos[0] = 0; pos[1] = 0; pos[2] = 0;
  let k = 3;
  for (let i = 1; i <= rings; i++) {
    const r = (s0 * (Math.pow(1 + q, i) - 1)) / q;
    for (let j = 0; j < segments; j++) {
      const a = ((j + (i % 2) * 0.5) / segments) * Math.PI * 2;
      pos[k++] = Math.cos(a) * r;
      pos[k++] = 0;
      pos[k++] = Math.sin(a) * r;
    }
  }
  const idx = [];
  for (let j = 0; j < segments; j++) idx.push(0, 1 + ((j + 1) % segments), 1 + j);
  for (let i = 1; i < rings; i++) {
    const a0 = 1 + (i - 1) * segments, a1 = 1 + i * segments;
    for (let j = 0; j < segments; j++) {
      const j1 = (j + 1) % segments;
      idx.push(a0 + j, a0 + j1, a1 + j);
      idx.push(a0 + j1, a1 + j1, a1 + j);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setIndex(idx);
  g.boundingSphere = new THREE.Sphere(new THREE.Vector3(), rMax);
  return { geometry: g, q };
}

const oceanVS = /* glsl */ `
uniform sampler2D uDisp0;
uniform sampler2D uDisp1;
uniform sampler2D uDisp2;
uniform vec3 uL;
uniform vec2 uCenter;
uniform float uSeaLevel;
uniform float uCurv;
uniform float uQ;
uniform float uS0;
uniform sampler2D uDem;
uniform vec4 uDemRect;
uniform sampler2D uDemNear;
uniform vec4 uDemNearRect;
uniform float uHasDem;
varying vec3 vWorld;
varying vec2 vXZ;
varying float vDepth;

float lodFor(float spacing, float L) { return max(0.0, log2(spacing / (L / 256.0)) + 1.0); }

void main() {
  vec2 local = position.xz;
  float r = length(local);
  float spacing = uS0 + r * uQ;
  vec2 xz = local + uCenter;
  float depth = 60.0;
  if (uHasDem > 0.5) {
    vec2 duv = (xz - uDemRect.xy) / uDemRect.zw;
    if (all(greaterThan(duv, vec2(0.0))) && all(lessThan(duv, vec2(1.0)))) {
      depth = uSeaLevel - textureLod(uDem, duv, 0.0).r;
    }
    vec2 nuv = (xz - uDemNearRect.xy) / uDemNearRect.zw;
    float e = min(min(nuv.x, nuv.y), min(1.0 - nuv.x, 1.0 - nuv.y));
    if (e > 0.0) depth = mix(depth, uSeaLevel - textureLod(uDemNear, nuv, 0.0).r, smoothstep(0.0, 0.015, e));
  }
  // waves shoal and die out over the last metres of depth
  float amp = clamp(depth / 6.0, 0.08, 1.0);
  vec3 d = vec3(0.0);
  d += textureLod(uDisp0, xz / uL.x, lodFor(spacing, uL.x)).xyz;
  d += textureLod(uDisp1, xz / uL.y, lodFor(spacing, uL.y)).xyz;
  d += textureLod(uDisp2, xz / uL.z, lodFor(spacing, uL.z)).xyz;
  d *= amp;
  vec3 wp = vec3(xz.x + d.x, uSeaLevel + d.y, xz.y + d.z);
  vWorld = wp;
  vXZ = xz;
  vDepth = depth;
  vec2 dc = wp.xz - cameraPosition.xz;
  wp.y -= dot(dc, dc) * uCurv;
  gl_Position = projectionMatrix * viewMatrix * vec4(wp, 1.0);
}`;

const oceanFS = /* glsl */ `
precision highp sampler3D;
${atmoParsGLSL}
${cloudParsGLSL}
uniform sampler2D uDisp0;
uniform sampler2D uDisp1;
uniform sampler2D uDisp2;
uniform sampler2D uDeriv0;
uniform sampler2D uDeriv1;
uniform sampler2D uDeriv2;
uniform sampler2D uSlope20;
uniform sampler2D uSlope21;
uniform sampler2D uSlope22;
uniform vec3 uL;
uniform float uSubVar;
uniform vec3 uSunColor;
uniform sampler2D uEnvMap;
uniform float uEnvMaxLod;
uniform vec3 uWaterAlbedo;
uniform vec3 uSSSColor;
uniform float uFoamScale;
uniform float uTime;
uniform float uSeaLevel;
uniform sampler2D uWake;
uniform vec3 uWakeRect;
uniform float uCloudShadowOn;
uniform vec3 uShipShadow[8];   // xz centre (x,z) + radius
uniform vec4 uShipShadowDir[8]; // forward xz, length/2, beam/2
uniform int uShipShadowCount;
${rainRipplesGLSL}
uniform vec4 uDry;      // USV hull footprint: centre xz, forward xz
uniform vec2 uDryExt;   // half length, half beam
varying vec3 vWorld;
varying vec2 vXZ;
varying float vDepth;

vec2 equirectUV(vec3 d) {
  return vec2(atan(d.z, d.x) * (0.5 / PI) + 0.5, asin(clamp(d.y, -1.0, 1.0)) / PI + 0.5);
}
vec3 envSample(vec3 d, float lod) { return textureLod(uEnvMap, equirectUV(d), lod).rgb; }

float erfc_(float x) { return 2.0 * exp(-x * x) / (2.319 * x + sqrt(4.0 + 1.52 * x * x)); }
float Lambda(float cosTheta, float sigmaSq) {
  float v = cosTheta / sqrt(max((1.0 - cosTheta * cosTheta) * (2.0 * sigmaSq), 1e-8));
  return max(0.0, (exp(-v * v) - v * sqrt(PI) * erfc_(v)) / (2.0 * v * sqrt(PI)));
}
// Bruneton, Neyret, Holzschuch 2010 - Real-time realistic ocean lighting
float reflectedSunRadiance(vec3 L, vec3 V, vec3 N, vec3 Tx, vec3 Ty, vec2 sigmaSq) {
  vec3 H = normalize(L + V);
  float zH = max(dot(H, N), 1e-3);
  float zetax = dot(H, Tx) / zH;
  float zetay = dot(H, Ty) / zH;
  float zL = dot(L, N), zV = dot(V, N);
  float zH2 = zH * zH;
  float p = exp(-0.5 * (zetax * zetax / sigmaSq.x + zetay * zetay / sigmaSq.y)) / (2.0 * PI * sqrt(sigmaSq.x * sigmaSq.y));
  float vx = dot(V, Tx), vy = dot(V, Ty), lx = dot(L, Tx), ly = dot(L, Ty);
  float cV2 = vx * vx / max(vx * vx + vy * vy, 1e-6);
  float sigmaV2 = sigmaSq.x * cV2 + sigmaSq.y * (1.0 - cV2);
  float cL2 = lx * lx / max(lx * lx + ly * ly, 1e-6);
  float sigmaL2 = sigmaSq.x * cL2 + sigmaSq.y * (1.0 - cL2);
  float fresnel = 0.02 + 0.98 * pow(1.0 - clamp(dot(V, H), 0.0, 1.0), 5.0);
  zL = max(zL, 0.01); zV = max(zV, 0.01);
  return fresnel * p / ((1.0 + Lambda(zL, sigmaL2) + Lambda(zV, sigmaV2)) * zV * zH2 * zH2 * 4.0);
}
float meanFresnel(float cosThetaV, float sigmaV) {
  return pow(1.0 - cosThetaV, 5.0 * exp(-2.69 * sigmaV)) / (1.0 + 22.7 * pow(sigmaV, 1.5));
}

// small value noise for foam texture
float hash12(vec2 p) { vec3 p3 = fract(vec3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }
float vnoise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash12(i), hash12(i + vec2(1, 0)), u.x), mix(hash12(i + vec2(0, 1)), hash12(i + vec2(1, 1)), u.x), u.y);
}
float foamPattern(vec2 p) {
  float n = vnoise(p * 1.7) * 0.5 + vnoise(p * 4.1 + 3.7) * 0.3 + vnoise(p * 9.3 - 1.3) * 0.2;
  return n;
}
// lacy, broken foam: ridges of a few noise octaves
float foamLace(vec2 p) {
  float a = 1.0 - abs(vnoise(p * 2.3) * 2.0 - 1.0);
  float b = 1.0 - abs(vnoise(p * 5.9 + 7.1) * 2.0 - 1.0);
  float c = vnoise(p * 13.7 - 3.3);
  return clamp(a * a * 0.55 + b * b * 0.35 + c * 0.25, 0.0, 1.0);
}

void main() {
  {
    vec2 rel = vWorld.xz - uDry.xy;
    vec2 q = vec2(dot(rel, uDry.zw), dot(rel, vec2(-uDry.w, uDry.z))) / uDryExt;
    if (dot(q, q) < 1.0 && abs(q.x) < 0.98) discard;
  }
  vec3 toCam = cameraPosition - vWorld;
  float dist = length(toCam);
  vec3 V = toCam / dist;
  vec2 uv0 = vXZ / uL.x, uv1 = vXZ / uL.y, uv2 = vXZ / uL.z;
  vec4 g0 = texture(uDeriv0, uv0), g1 = texture(uDeriv1, uv1), g2 = texture(uDeriv2, uv2);
  vec4 s0 = texture(uSlope20, uv0), s1 = texture(uSlope21, uv1), s2 = texture(uSlope22, uv2);
  float amp = clamp(vDepth / 6.0, 0.08, 1.0);
  vec2 slope = (g0.xy + g1.xy + g2.xy) * amp;
  vec2 jac = vec2(1.0) + (g0.zw + g1.zw + g2.zw) * amp;
  vec2 var = max(s0.xy - g0.xy * g0.xy, 0.0) + max(s1.xy - g1.xy * g1.xy, 0.0) + max(s2.xy - g2.xy * g2.xy, 0.0);
  // capillary detail: cascade 2 re-used at a higher frequency, rotated
  vec2 uvm = mat2(0.8, -0.6, 0.6, 0.8) * vXZ / (uL.z * 0.21);
  vec4 gm = texture(uDeriv2, uvm);
  vec4 sm = texture(uSlope22, uvm);
  float micro = clamp(uSubVar * 45.0, 0.25, 1.0) * 0.85;
  slope += gm.xy * micro * amp;
  var += max(sm.xy - gm.xy * gm.xy, 0.0) * micro * micro;
  // capillary ripples right next to the boat (fade out once below pixel size)
  vec2 uvc = mat2(0.36, 0.93, -0.93, 0.36) * vXZ / (uL.z * 0.065) + vec2(uTime * 0.05, 0.0);
  vec4 gc = texture(uDeriv2, uvc);
  float capFade = 1.0 - smoothstep(0.004, 0.03, length(fwidth(uvc * uL.z * 0.065 / 256.0)) );
  slope += gc.xy * micro * 0.45 * capFade * amp;
  // raindrop impacts: expanding rings close to the camera
  float rainSplash = 0.0;
  if (uRain > 0.01) {
    float rf = 1.0 - smoothstep(6.0, 40.0, dist);
    if (rf > 0.0) {
      vec3 rp = rainRipples(vXZ, uTime);
      slope += rp.xy * rf * (0.4 + 0.6 * uRain);
      rainSplash = rp.z * rf * uRain;
    }
    var += vec2(0.004 * uRain);
  }
  float footprint = length(fwidth(vXZ));
  var = var * amp + vec2(uSubVar) * mix(0.75, 1.0, smoothstep(0.01, 0.15, footprint));

  // wakes (turbulent foam + roughness)
  vec4 wake = vec4(0.0);
  vec2 wuv = (vWorld.xz - uWakeRect.xy) / uWakeRect.z;
  if (all(greaterThan(wuv, vec2(0.0))) && all(lessThan(wuv, vec2(1.0)))) wake = texture(uWake, wuv);
  float wakeEdge = smoothstep(0.0, 0.08, min(min(wuv.x, wuv.y), min(1.0 - wuv.x, 1.0 - wuv.y)));
  wake *= wakeEdge;
  // turbulent wake: chaotic near the hull, then a long smooth 'slick' that damps the ripples
  float slick = smoothstep(0.05, 0.6, wake.a) * (1.0 - smoothstep(0.4, 1.2, wake.r));
  slope = mix(slope, slope * 0.55, slick);
  var *= 1.0 - 0.6 * slick;
  slope += wake.gb * 0.6;
  var += vec2(clamp(wake.r, 0.0, 1.0) * 0.012);

  vec3 N = normalize(vec3(-slope.x / max(jac.x, 0.25), 1.0, -slope.y / max(jac.y, 0.25)));
  float NdV = dot(N, V);
  if (NdV < 0.02) { N = normalize(N + V * (0.02 - NdV)); NdV = 0.02; }

  vec3 L = uSunDir;
  float cloudSh = uCloudShadowOn > 0.5 ? cloudShadowAt(vWorld) : 1.0;
  // ship shadows (soft ellipses projected along the sun)
  float shipSh = 1.0;
  for (int i = 0; i < 8; i++) {
    if (i >= uShipShadowCount) break;
    vec2 c = uShipShadow[i].xy;
    if (abs(vWorld.x - c.x) + abs(vWorld.z - c.y) > uShipShadowDir[i].z * 2.2 + uShipShadow[i].z / max(L.y, 0.08) + 5.0) continue;
    vec2 off = -L.xz / max(L.y, 0.08) * uShipShadow[i].z;
    vec2 rel = vWorld.xz - (c + off * 0.5);
    vec2 fw = uShipShadowDir[i].xy;
    vec2 q = vec2(dot(rel, fw), dot(rel, vec2(-fw.y, fw.x)));
    vec2 ext = uShipShadowDir[i].zw + vec2(length(off) * 0.5, 0.0);
    float e = length(q / max(ext, vec2(0.5)));
    shipSh *= mix(1.0, 0.25, 1.0 - smoothstep(0.75, 1.05, e));
  }
  vec3 sunE = uSunColor * cloudSh * shipSh;

  // --- reflection of the sky ---
  vec3 R = reflect(-V, N);
  R.y = abs(R.y) * 0.8 + 0.004;
  R = normalize(R);
  float sigma = sqrt(var.x + var.y);
  float lod = clamp(log2(max(sigma * 2.0 * 1024.0 / (2.0 * PI), 1.0)), 0.0, uEnvMaxLod - 1.0);
  vec3 sky = envSample(R, lod);
  float sigmaV = sqrt(0.5 * (var.x + var.y));
  float F = clamp(meanFresnel(NdV, sigmaV), 0.02, 1.0);
  F = mix(0.02, 1.0, F);

  // --- sun glitter ---
  vec3 Ty = normalize(cross(N, vec3(1.0, 0.0, 0.0)));
  vec3 Tx = cross(Ty, N);
  float spec = reflectedSunRadiance(L, V, N, Tx, Ty, max(var, vec2(2e-4)));
  spec *= smoothstep(-0.02, 0.03, L.y);

  // --- light entering the water body ---
  vec3 Esky = envSample(vec3(0.0, 1.0, 0.0), uEnvMaxLod - 2.0) * PI;
  vec3 Ein = sunE * max(L.y, 0.0) + Esky;
  vec3 body = uWaterAlbedo * Ein / PI;
  // forward scattering through thin crests, seen against the light
  float h = vWorld.y - uSeaLevel;
  vec3 Lh = normalize(vec3(L.x, max(L.y, 0.0) * 0.4, L.z));
  float back = pow(clamp(dot(-V, Lh), 0.0, 1.0), 4.0);
  float crest = clamp(h * 0.55 + 0.25, 0.0, 1.6) * clamp(1.0 - N.y * 0.6, 0.0, 1.0) * 2.2;
  float side = pow(clamp(dot(N, Lh) * 0.5 + 0.5, 0.0, 1.0), 3.0) * 0.035;
  vec3 sss = uSSSColor * sunE * (back * crest + side) * clamp(L.y * 4.0 + 0.2, 0.0, 1.0) / PI;
  sss += uSSSColor * Esky * clamp(h * 0.25 + 0.15, 0.0, 0.6) * 0.15 / PI;

  // shallow water: sandy / green tint where the seabed is close
  float shallow = exp(-max(vDepth, 0.0) / 3.0);
  body = mix(body, vec3(0.12, 0.16, 0.12) * Ein / PI * 0.35, shallow * 0.7);

  vec3 col = (1.0 - F) * (body + sss) + F * sky + sunE * spec;

  // --- foam: whitecaps from the jacobian, wakes, shoreline ---
  vec4 d0 = texture(uDisp0, uv0), d1 = texture(uDisp1, uv1), d2 = texture(uDisp2, uv2);
  float jfoam = (d0.w * 0.7 + d1.w * 0.6 + d2.w * 0.25) * amp;
  vec2 fp = vXZ + vec2(d1.x, d1.z) * 1.0;
  bool anyFoam = jfoam > 0.03 || wake.r > 0.005 || vDepth < 3.0;
  float pat = anyFoam ? foamPattern(fp * uFoamScale) : 0.5;
  float patFine = anyFoam ? foamPattern(fp * uFoamScale * 4.3 + 11.0) : 0.5;
  float lace = anyFoam ? foamLace(fp * uFoamScale * 1.6) : 0.0;
  // fresh whitecaps are dense, older foam breaks into lace and streaks
  float whitecap = smoothstep(0.55, 1.1, jfoam) * smoothstep(0.25, 0.6, lace + jfoam * 0.35);
  float streak = smoothstep(0.12, 0.6, jfoam) * smoothstep(0.62, 0.85, lace) * 0.55;
  float wakeFoam = clamp(wake.r, 0.0, 1.0);
  float wf = smoothstep(0.08, 0.5, wakeFoam * 0.75 + patFine * 0.35 + pat * 0.15 - 0.1) * min(wakeFoam * 1.6, 1.0);
  // breaking on rocks and beaches
  float shore = 0.0;
  if (vDepth < 3.0 && vDepth > -2.0) {
    float wave = sin(uTime * 0.9 - vDepth * 2.2 + pat * 4.0) * 0.5 + 0.5;
    shore = smoothstep(3.0, 0.2, vDepth) * smoothstep(0.25, 0.95, wave * 0.6 + pat * 0.6);
    shore = max(shore, smoothstep(0.9, 0.0, vDepth) * smoothstep(0.35, 0.7, pat));
  }
  float foam = clamp(max(max(whitecap, streak), max(max(wf, shore), rainSplash * 0.6)), 0.0, 1.0);
  // foam is a rough, bright, slightly translucent layer
  vec3 foamCol = vec3(0.86, 0.9, 0.92) * (sunE * max(dot(N, L), 0.0) * 0.85 + Esky) / PI + uSSSColor * sunE * back * 0.25;
  col = mix(col, foamCol, foam * 0.92);

  col = applyAerial(col, vWorld - cameraPosition);
  gl_FragColor = vec4(min(col, vec3(30000.0)), 1.0);
}`;

export class OceanSurface {
  constructor(fft, sky) {
    this.fft = fft;
    const { geometry, q } = buildRadialGrid(512, 440, 80000, 0.2);
    const black = new THREE.DataTexture(new Float32Array([0, 0, 0, 0]), 1, 1, THREE.RGBAFormat, THREE.FloatType);
    black.needsUpdate = true;
    const zeroDem = new THREE.DataTexture(new Float32Array([-60]), 1, 1, THREE.RedFormat, THREE.FloatType);
    zeroDem.needsUpdate = true;
    this.uniforms = {
      ...sky.uniforms,
      uDisp0: { value: null }, uDisp1: { value: null }, uDisp2: { value: null },
      uDeriv0: { value: null }, uDeriv1: { value: null }, uDeriv2: { value: null },
      uSlope20: { value: null }, uSlope21: { value: null }, uSlope22: { value: null },
      uL: { value: new THREE.Vector3(...fft.lengths) },
      uCenter: { value: new THREE.Vector2() },
      uSeaLevel: { value: 0 },
      uCurv: { value: EARTH_CURV },
      uQ: { value: q },
      uS0: { value: 0.2 },
      uSubVar: { value: subgridSlopeVariance(fft.sea.windSpeed) },
      // Iroise / Rade de Brest: dark green-blue, moderately turbid
      uWaterAlbedo: { value: new THREE.Vector3(0.0035, 0.0125, 0.0165) },
      uSSSColor: { value: new THREE.Vector3(0.025, 0.12, 0.105) },
      uFoamScale: { value: 0.55 },
      uTime: { value: 0 },
      uWake: { value: black },
      uWakeRect: { value: new THREE.Vector3(-1e6, -1e6, 1) },
      uDem: { value: zeroDem },
      uDemRect: { value: new THREE.Vector4(0, 0, 1, 1) },
      uDemNear: { value: zeroDem },
      uDemNearRect: { value: new THREE.Vector4(-1e7, -1e7, 1, 1) },
      uDry: { value: new THREE.Vector4(1e7, 1e7, 1, 0) },
      uDryExt: { value: new THREE.Vector2(1, 1) },
      uHasDem: { value: 0 },
      uCloudShadowOn: { value: 1 },
      uShipShadow: { value: Array.from({ length: 8 }, () => new THREE.Vector3()) },
      uShipShadowDir: { value: Array.from({ length: 8 }, () => new THREE.Vector4()) },
      uShipShadowCount: { value: 0 },
    };
    this.material = new THREE.ShaderMaterial({
      uniforms: this.uniforms,
      vertexShader: oceanVS,
      fragmentShader: oceanFS,
      side: THREE.DoubleSide,
    });
    this.mesh = new THREE.Mesh(geometry, this.material);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = -10;
  }

  setWind(windSpeed) {
    this.uniforms.uSubVar.value = subgridSlopeVariance(windSpeed);
  }

  update(camera, time) {
    const u = this.uniforms;
    for (let i = 0; i < 3; i++) {
      const t = this.fft.tex(i);
      u['uDisp' + i].value = t.disp;
      u['uDeriv' + i].value = t.deriv;
      u['uSlope2' + i].value = t.slope2;
    }
    u.uCenter.value.set(camera.position.x, camera.position.z);
    u.uTime.value = time;
  }
}
