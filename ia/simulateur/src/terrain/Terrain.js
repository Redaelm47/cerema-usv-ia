import * as THREE from 'three';
import { atmoParsGLSL } from '../sky/atmosphereGLSL.js';
import { cloudParsGLSL } from '../sky/cloudsGLSL.js';
import { EARTH_CURV } from '../ocean/OceanSurface.js';

// Real terrain of the Goulet / Rade de Brest from IGN data (LiDAR surface model
// near the coast, RGE ALTI further away) draped with IGN orthophotos.
// Rendering: instanced chunk grid with distance LODs and skirts; heights,
// normals and albedo are fetched per pixel from the DEM/ortho textures.

const CHUNK = 500;
const LODS = [128, 64, 32, 16, 8];
const LOD_DIST = [900, 2000, 4500, 9000, 1e9];

function gridGeometry(n) {
  const pos = [], skirt = [], idx = [];
  const row = n + 1;
  for (let j = 0; j <= n; j++) for (let i = 0; i <= n; i++) { pos.push(i / n, 0, j / n); skirt.push(0); }
  for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) {
    const a = j * row + i;
    idx.push(a, a + row, a + 1, a + 1, a + row, a + row + 1);
  }
  // skirts along the 4 borders
  const border = [];
  for (let i = 0; i <= n; i++) border.push(i);                       // north edge (j=0)
  for (let j = 0; j <= n; j++) border.push(j * row + n);             // east
  for (let i = n; i >= 0; i--) border.push(n * row + i);             // south
  for (let j = n; j >= 0; j--) border.push(j * row);                 // west
  const base = pos.length / 3;
  border.forEach((b) => { pos.push(pos[b * 3], 0, pos[b * 3 + 2]); skirt.push(1); });
  for (let k = 0; k < border.length - 1; k++) {
    const a = border[k], b = border[k + 1], sa = base + k, sb = base + k + 1;
    idx.push(a, sa, b, b, sa, sb);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('aSkirt', new THREE.Float32BufferAttribute(skirt, 1));
  g.setIndex(idx);
  return g;
}

const terrainVS = /* glsl */ `
attribute vec3 aChunk;
attribute float aSkirt;
uniform sampler2D uDemFar;
uniform sampler2D uDemNear;
uniform vec4 uFarRect;
uniform vec4 uNearRect;
uniform float uCurv;
varying vec3 vWorld;
varying vec2 vXZ;

float demH(vec2 xz) {
  vec2 fu = (xz - uFarRect.xy) / uFarRect.zw;
  float h = textureLod(uDemFar, fu, 0.0).r;
  vec2 nu = (xz - uNearRect.xy) / uNearRect.zw;
  float e = min(min(nu.x, nu.y), min(1.0 - nu.x, 1.0 - nu.y));
  if (e > 0.0) h = mix(h, textureLod(uDemNear, nu, 0.0).r, smoothstep(0.0, 0.015, e));
  return h;
}

void main() {
  vec2 xz = aChunk.xy + position.xz * aChunk.z;
  float h = demH(xz);
  h -= aSkirt * (12.0 + aChunk.z * 0.01);
  vec3 wp = vec3(xz.x, h, xz.y);
  vWorld = wp;
  vXZ = xz;
  vec2 dc = wp.xz - cameraPosition.xz;
  wp.y -= dot(dc, dc) * uCurv;
  gl_Position = projectionMatrix * viewMatrix * vec4(wp, 1.0);
}`;

const terrainFS = /* glsl */ `
precision highp sampler3D;
${atmoParsGLSL}
${cloudParsGLSL}
uniform sampler2D uDemFar;
uniform sampler2D uDemNear;
uniform sampler2D uOrthoFar;
uniform sampler2D uOrthoNear;
uniform vec4 uFarRect;
uniform vec4 uNearRect;
uniform vec2 uFarTexel;
uniform vec2 uNearTexel;
uniform vec3 uSunColor;
uniform sampler2D uEnvMap;
uniform float uEnvMaxLod;
uniform float uSeaLevel;
uniform float uCloudShadowOn;
uniform float uRain;
varying vec3 vWorld;
varying vec2 vXZ;

vec2 equirectUV(vec3 d) { return vec2(atan(d.z, d.x) * (0.5 / PI) + 0.5, asin(clamp(d.y, -1.0, 1.0)) / PI + 0.5); }
float th(vec2 p) { vec3 p3 = fract(vec3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }
float tn(vec2 p) { vec2 i = floor(p), f = fract(p); vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(th(i), th(i + vec2(1, 0)), u.x), mix(th(i + vec2(0, 1)), th(i + vec2(1, 1)), u.x), u.y); }
float tfbm(vec2 p) { float s = 0.0, a = 0.5; for (int i = 0; i < 5; i++) { s += a * tn(p); p = p * 2.07 + 1.3; a *= 0.5; } return s; }

vec3 demNormal(sampler2D dem, vec2 uv, vec2 texel, vec2 metres) {
  float hl = texture(dem, uv - vec2(texel.x, 0.0)).r, hr = texture(dem, uv + vec2(texel.x, 0.0)).r;
  float hd = texture(dem, uv - vec2(0.0, texel.y)).r, hu = texture(dem, uv + vec2(0.0, texel.y)).r;
  // v grows southwards (+z)
  return normalize(vec3(-(hr - hl) / (2.0 * metres.x), 1.0, -(hu - hd) / (2.0 * metres.y)));
}

void main() {
  vec2 fu = (vXZ - uFarRect.xy) / uFarRect.zw;
  vec2 nu = (vXZ - uNearRect.xy) / uNearRect.zw;
  float e = min(min(nu.x, nu.y), min(1.0 - nu.x, 1.0 - nu.y));
  float wN = e > 0.0 ? smoothstep(0.0, 0.015, e) : 0.0;
  vec3 N = demNormal(uDemFar, fu, uFarTexel, uFarTexel * uFarRect.zw);
  vec3 albedo = texture(uOrthoFar, fu).rgb;
  if (wN > 0.0) {
    vec3 Nn = demNormal(uDemNear, nu, uNearTexel, uNearTexel * uNearRect.zw);
    N = normalize(mix(N, Nn, wN));
    albedo = mix(albedo, texture(uOrthoNear, nu).rgb, wN);
  }
  float hA = vWorld.y - uSeaLevel;
  // orthophotos carry their own shading: flatten it a little before relighting
  float lum = dot(albedo, vec3(0.299, 0.587, 0.114));
  albedo = mix(albedo, albedo / max(lum, 0.02) * mix(lum, 0.22, 0.35), 0.35);
  albedo *= 0.85;
  // steep faces: granite cliffs (orthophotos smear on vertical faces)
  float steep = 1.0 - N.y;
  float n1 = tfbm(vWorld.xz * 0.35 + vWorld.y * 0.2), n2 = tfbm(vec2(vWorld.x + vWorld.z, vWorld.y) * 1.3);
  vec3 granite = mix(vec3(0.30, 0.27, 0.24), vec3(0.46, 0.41, 0.36), n1) * (0.75 + 0.45 * n2);
  granite = mix(granite, vec3(0.42, 0.40, 0.18), smoothstep(0.55, 0.75, n2) * 0.35 * step(0.0, hA - 6.0));
  float rock = smoothstep(0.38, 0.62, steep + (n1 - 0.5) * 0.25);
  albedo = mix(albedo, granite, rock);
  // intertidal band: dark wet rock, wrack and barnacles
  float tidal = smoothstep(3.2, 0.3, hA);
  vec3 wet = mix(vec3(0.05, 0.045, 0.03), vec3(0.16, 0.13, 0.07), n2) ;
  albedo = mix(albedo, wet, tidal * 0.85);
  albedo *= 1.0 - 0.28 * uRain; // wet ground is darker

  vec3 L = uSunDir;
  float sh = uCloudShadowOn > 0.5 ? cloudShadowAt(vWorld) : 1.0;
  vec3 V = normalize(cameraPosition - vWorld);
  vec3 sky = textureLod(uEnvMap, equirectUV(normalize(N + vec3(0.0, 0.6, 0.0))), uEnvMaxLod - 2.0).rgb * PI;
  float ao = 0.55 + 0.45 * N.y;
  vec3 col = albedo / PI * (uSunColor * max(dot(N, L), 0.0) * sh + sky * ao);
  // wet sheen near the waterline
  vec3 H = normalize(L + V);
  col += uSunColor * sh * tidal * 0.08 * pow(max(dot(N, H), 0.0), 60.0);
  col = applyAerial(col, vWorld - cameraPosition);
  gl_FragColor = vec4(col, 1.0);
}`;

export class Terrain {
  constructor(sky) {
    this.sky = sky;
    this.group = new THREE.Group();
    this.ready = false;
  }

  async load(base = '/data/', renderer = null) {
    this.floatLinear = !!renderer && renderer.extensions.has('OES_texture_float_linear');
    const meta = await (await fetch(base + 'terrain.json')).json();
    this.meta = meta;
    const layerOf = (name) => {
      const ls = meta.layers || meta;
      return ls[name] || ls[name.replace('dem_', '')] || Object.values(ls).find((l) => l.file && l.file.includes(name));
    };
    const far = layerOf('dem_far'), near = layerOf('dem_near');
    const ofar = layerOf('ortho_far'), onear = layerOf('ortho_near');
    const loadDem = async (l) => {
      const buf = await (await fetch(base + l.file)).arrayBuffer();
      const i16 = new Int16Array(buf);
      const f32 = new Float32Array(i16.length);
      for (let i = 0; i < i16.length; i++) f32[i] = i16[i] / 10;
      let t;
      if (this.floatLinear) {
        t = new THREE.DataTexture(f32, l.width, l.height, THREE.RedFormat, THREE.FloatType);
      } else {
        const half = new Uint16Array(f32.length);
        for (let i = 0; i < f32.length; i++) half[i] = THREE.DataUtils.toHalfFloat(f32[i]);
        t = new THREE.DataTexture(half, l.width, l.height, THREE.RedFormat, THREE.HalfFloatType);
      }
      t.minFilter = THREE.LinearFilter; t.magFilter = THREE.LinearFilter;
      t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping;
      t.needsUpdate = true;
      const ex = l.extent || l.extents || l;
      const rect = new THREE.Vector4(ex.xWest, -ex.nNorth, ex.xEast - ex.xWest, ex.nNorth - ex.nSouth);
      return { tex: t, data: f32, w: l.width, h: l.height, rect };
    };
    const loadOrtho = (l) => new Promise((res, rej) => {
      new THREE.TextureLoader().load(base + l.file, (t) => {
        t.colorSpace = THREE.SRGBColorSpace;
        t.flipY = false;
        t.anisotropy = 8;
        t.generateMipmaps = true;
        t.minFilter = THREE.LinearMipmapLinearFilter;
        t.needsUpdate = true;
        res(t);
      }, undefined, rej);
    });
    const [dFar, dNear, oFar, oNear] = await Promise.all([loadDem(far), loadDem(near), loadOrtho(ofar), loadOrtho(onear)]);
    this.far = dFar; this.near = dNear;
    // the orthophotos also serve as the satellite layer of the map (same extents as the DEMs)
    this.ortho = { far: { img: oFar.image, rect: dFar.rect }, near: { img: oNear.image, rect: dNear.rect } };
    this.uniforms = {
      ...this.sky.uniforms,
      uDemFar: { value: dFar.tex }, uDemNear: { value: dNear.tex },
      uOrthoFar: { value: oFar }, uOrthoNear: { value: oNear },
      uFarRect: { value: dFar.rect }, uNearRect: { value: dNear.rect },
      uFarTexel: { value: new THREE.Vector2(1 / dFar.w, 1 / dFar.h) },
      uNearTexel: { value: new THREE.Vector2(1 / dNear.w, 1 / dNear.h) },
      uCurv: { value: EARTH_CURV },
      uSeaLevel: { value: 0 },
      uCloudShadowOn: { value: 1 },
    };
    this.material = new THREE.ShaderMaterial({ uniforms: this.uniforms, vertexShader: terrainVS, fragmentShader: terrainFS, side: THREE.DoubleSide });
    this._buildChunks();
    this.ready = true;
    return this;
  }

  /** height (m) at world x,z, near DEM preferred */
  heightAt(x, z) {
    const sample = (d) => {
      const u = (x - d.rect.x) / d.rect.z, v = (z - d.rect.y) / d.rect.w;
      if (u < 0 || v < 0 || u >= 1 || v >= 1) return null;
      const fx = u * d.w - 0.5, fy = v * d.h - 0.5;
      const ix = Math.max(0, Math.min(d.w - 2, Math.floor(fx))), iy = Math.max(0, Math.min(d.h - 2, Math.floor(fy)));
      const tx = Math.min(Math.max(fx - ix, 0), 1), ty = Math.min(Math.max(fy - iy, 0), 1);
      const a = d.data[iy * d.w + ix], b = d.data[iy * d.w + ix + 1], c = d.data[(iy + 1) * d.w + ix], e = d.data[(iy + 1) * d.w + ix + 1];
      return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + e * tx) * ty;
    };
    const n = this.near && sample(this.near);
    if (n !== null && n !== undefined) return n;
    const f = this.far && sample(this.far);
    return f ?? -50;
  }

  _buildChunks() {
    const r = this.far.rect;
    const nx = Math.ceil(r.z / CHUNK), nz = Math.ceil(r.w / CHUNK);
    this.chunks = [];
    for (let j = 0; j < nz; j++) for (let i = 0; i < nx; i++) {
      const x0 = r.x + i * CHUNK, z0 = r.y + j * CHUNK;
      let maxH = -1e9, minH = 1e9;
      for (let b = 0; b <= 12; b++) for (let a = 0; a <= 12; a++) {
        const h = this.heightAt(x0 + (a / 12) * CHUNK, z0 + (b / 12) * CHUNK);
        maxH = Math.max(maxH, h); minH = Math.min(minH, h);
      }
      if (maxH < -4) continue;
      this.chunks.push({ x0, z0, box: new THREE.Box3(new THREE.Vector3(x0, minH - 15, z0), new THREE.Vector3(x0 + CHUNK, maxH + 30, z0 + CHUNK)) });
    }
    this.meshes = LODS.map((n) => {
      const g = gridGeometry(n);
      const attr = new THREE.InstancedBufferAttribute(new Float32Array(this.chunks.length * 3), 3);
      attr.setUsage(THREE.DynamicDrawUsage);
      g.setAttribute('aChunk', attr);
      g.instanceCount = 0;
      const ig = new THREE.InstancedBufferGeometry().copy(g);
      ig.instanceCount = 0;
      const m = new THREE.Mesh(ig, this.material);
      m.frustumCulled = false;
      m.renderOrder = -5;
      this.group.add(m);
      return m;
    });
    this._frustum = new THREE.Frustum();
    this._m = new THREE.Matrix4();
  }

  update(camera, seaLevel) {
    if (!this.ready) return;
    this.uniforms.uSeaLevel.value = seaLevel;
    this._m.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
    this._frustum.setFromProjectionMatrix(this._m);
    const counts = LODS.map(() => 0);
    const arrs = this.meshes.map((m) => m.geometry.attributes.aChunk.array);
    const cx = camera.position.x, cz = camera.position.z;
    for (const c of this.chunks) {
      if (!this._frustum.intersectsBox(c.box)) continue;
      const dx = Math.max(c.x0 - cx, 0, cx - (c.x0 + CHUNK));
      const dz = Math.max(c.z0 - cz, 0, cz - (c.z0 + CHUNK));
      const d = Math.hypot(dx, dz, Math.max(0, camera.position.y - c.box.max.y));
      let l = 0;
      while (d > LOD_DIST[l]) l++;
      const k = counts[l]++;
      arrs[l][k * 3] = c.x0; arrs[l][k * 3 + 1] = c.z0; arrs[l][k * 3 + 2] = CHUNK;
    }
    this.meshes.forEach((m, i) => {
      m.geometry.instanceCount = counts[i];
      m.geometry.attributes.aChunk.needsUpdate = true;
    });
  }
}
