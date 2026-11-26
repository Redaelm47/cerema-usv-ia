import * as THREE from 'three';
import { FullScreenQuad } from 'three/addons/postprocessing/Pass.js';
import { atmoParsGLSL, lutVS, transmittanceFS, multiScatFS, skyViewFS } from './atmosphereGLSL.js';
import { noiseGenFS, cloudParsGLSL } from './cloudsGLSL.js';

const SUN_E = 20.0; // solar illuminance at the top of the atmosphere (scene units)

function rt(w, h, opts = {}) {
  return new THREE.WebGLRenderTarget(w, h, {
    type: THREE.HalfFloatType,
    format: THREE.RGBAFormat,
    depthBuffer: false,
    stencilBuffer: false,
    minFilter: THREE.LinearFilter,
    magFilter: THREE.LinearFilter,
    wrapS: THREE.ClampToEdgeWrapping,
    wrapT: THREE.ClampToEdgeWrapping,
    ...opts,
  });
}

// ---------- CPU mirror of the medium, for light colours -----------------------
const Rg = 6360, Rt = 6460;
function mediumExt(h, p) {
  h = Math.max(h, 0);
  const dR = Math.exp(-h / 8), dM = Math.exp(-h / 1.2) + p.haze * Math.exp(-h / p.hazeHeight);
  const dO = Math.max(0, 1 - Math.abs(h - 25) / 15);
  return [0, 1, 2].map((c) => p.rayleigh[c] * dR + (p.mieScat + p.mieAbs) * dM + p.ozone[c] * dO);
}
function sunTransmittanceCPU(altKm, sunDir, p) {
  const ro = new THREE.Vector3(0, Rg + altKm, 0);
  const rd = sunDir.clone().normalize();
  const b = ro.dot(rd), c = ro.lengthSq() - Rt * Rt;
  const tTop = -b + Math.sqrt(Math.max(b * b - c, 0));
  // planet occlusion (soft)
  const muH = -Math.sqrt(Math.max(1 - (Rg * Rg) / ro.lengthSq(), 0));
  const fade = THREE.MathUtils.smoothstep(rd.y, muH - 0.004, muH + 0.004);
  const steps = 96;
  const od = [0, 0, 0];
  const dt = tTop / steps;
  const pt = new THREE.Vector3();
  for (let i = 0; i < steps; i++) {
    pt.copy(rd).multiplyScalar((i + 0.5) * dt).add(ro);
    const e = mediumExt(pt.length() - Rg, p);
    od[0] += e[0] * dt; od[1] += e[1] * dt; od[2] += e[2] * dt;
  }
  return new THREE.Vector3(Math.exp(-od[0]) * fade, Math.exp(-od[1]) * fade, Math.exp(-od[2]) * fade);
}

export class SkySystem {
  constructor(renderer) {
    this.renderer = renderer;
    this.frame = 0;
    this.params = {
      rayleigh: [5.802e-3, 13.558e-3, 33.1e-3],
      mieScat: 3.996e-3,
      mieAbs: 4.4e-3,
      ozone: [0.65e-3, 1.881e-3, 0.085e-3],
      haze: 6,
      hazeHeight: 0.6,
    };

    this.transmittance = rt(256, 64);
    this.multiScat = rt(32, 32);
    this.skyView = rt(192, 108);
    this.skyView.texture.wrapS = THREE.ClampToEdgeWrapping;

    // shared uniforms (same objects referenced by every material that uses them)
    const U = (this.uniforms = {
      uTransmittanceLUT: { value: this.transmittance.texture },
      uMultiScatLUT: { value: this.multiScat.texture },
      uSkyViewLUT: { value: this.skyView.texture },
      uSunDir: { value: new THREE.Vector3(0, 0.3, -1).normalize() },
      uSunE: { value: new THREE.Vector3(SUN_E, SUN_E, SUN_E) },
      uRayleighScat: { value: new THREE.Vector3(...this.params.rayleigh) },
      uMieScat: { value: this.params.mieScat },
      uMieAbs: { value: this.params.mieAbs },
      uOzoneAbs: { value: new THREE.Vector3(...this.params.ozone) },
      uHaze: { value: this.params.haze },
      uHazeHeight: { value: this.params.hazeHeight },
      uCamAltKm: { value: 0.002 },
      uExtinctionSea: { value: new THREE.Vector3() },
      uFogDensity: { value: 0 },
      uFogColor: { value: new THREE.Vector3(0.97, 0.99, 1.0) },
      // clouds
      uCloudNoise: { value: null },
      uWeather: { value: null },
      uCoverage: { value: 0.55 },
      uCloudBottom: { value: 0.85 },
      uCloudTop: { value: 2.9 },
      uCloudDensity: { value: 45.0 },
      uWindOffset: { value: new THREE.Vector2() },
      uCirrus: { value: 0.4 },
      uCloudTime: { value: 0 },
      uCamXZ: { value: new THREE.Vector2() },
      // lighting derived on the CPU
      uSunColor: { value: new THREE.Vector3(1, 1, 1) },   // sun illuminance at sea level
      uEnvMap: { value: null },                           // equirect sky (no sun), mipmapped
      uEnvMaxLod: { value: 9 },
      uRain: { value: 0 },
      uCloudShadowMap: { value: null },
      uCloudShadowRect: { value: new THREE.Vector3(0, 0, 1) },
    });

    const raw = (fs, extra = {}) =>
      new THREE.RawShaderMaterial({
        glslVersion: THREE.GLSL3,
        vertexShader: lutVS,
        fragmentShader: fs,
        uniforms: { ...U, ...extra },
        depthTest: false,
        depthWrite: false,
      });

    this.quad = new FullScreenQuad();
    this.transMat = raw(transmittanceFS);
    this.msMat = raw(multiScatFS);
    this.skyViewMat = raw(skyViewFS);

    this._buildNoise();

    // ---- screen-space clouds with temporal accumulation ----
    this.cloudRT = [rt(4, 4), rt(4, 4)];
    this.cloudCur = 0;
    this.cloudMat = raw(
      /* glsl */ `
      precision highp float;
      precision highp sampler3D;
      ${atmoParsGLSL}
      ${cloudParsGLSL}
      uniform mat4 uInvProj;
      uniform mat4 uCamRot;
      uniform mat4 uPrevVP;
      uniform sampler2D uHistory;
      uniform float uFrame;
      uniform float uBlend;
      uniform vec2 uRes;
      uniform vec2 uHalfRes;
      uniform vec2 uPattern;
      uniform int uSteps;
      in vec2 vUv;
      out vec4 fragColor;
      float ign(vec2 p) { return fract(52.9829189 * fract(dot(p, vec2(0.06711056, 0.00583715)))); }
      void main() {
        // this texel samples one half-res pixel of its 2x2 block (rotating pattern)
        vec2 half_ = floor(gl_FragCoord.xy) * 2.0 + uPattern + 0.5;
        vec2 jit = vec2(fract(uFrame * 0.7548777), fract(uFrame * 0.5698403)) - 0.5;
        vec2 ndc = ((half_ + jit * 0.9) / uHalfRes) * 2.0 - 1.0;
        vec4 v = uInvProj * vec4(ndc, 1.0, 1.0);
        vec3 dir = normalize((uCamRot * vec4(normalize(v.xyz / v.w), 0.0)).xyz);
        float j = fract(ign(gl_FragCoord.xy + 5.588238 * mod(uFrame, 64.0)) + uFrame * 0.618034);
        vec3 ro = vec3(0.0, uCamAltKm, 0.0);
        vec4 c = vec4(0.0, 0.0, 0.0, 1.0);
        if (dir.y > -0.01) c = marchClouds(ro, dir, uSteps, 4, j, 170.0);
        fragColor = c;
      }`,
      {
        uInvProj: { value: new THREE.Matrix4() },
        uCamRot: { value: new THREE.Matrix4() },
        uPrevVP: { value: new THREE.Matrix4() },
        uHistory: { value: null },
        uFrame: { value: 0 },
        uBlend: { value: 1 },
        uRes: { value: new THREE.Vector2() },
        uHalfRes: { value: new THREE.Vector2(1, 1) },
        uPattern: { value: new THREE.Vector2() },
        uSteps: { value: 56 },
      }
    );
    this.cloudLow = rt(4, 4);
    this.cloudLow.texture.minFilter = this.cloudLow.texture.magFilter = THREE.LinearFilter;
    this.resolveMat = raw(
      /* glsl */ `
      precision highp float;
      uniform sampler2D uLow;
      uniform sampler2D uHistory;
      uniform mat4 uInvProj;
      uniform mat4 uCamRot;
      uniform mat4 uPrevVP;
      uniform vec2 uPattern;
      uniform float uValid;
      in vec2 vUv;
      out vec4 fragColor;
      void main() {
        ivec2 p = ivec2(gl_FragCoord.xy);
        vec2 ndc = vUv * 2.0 - 1.0;
        vec4 v = uInvProj * vec4(ndc, 1.0, 1.0);
        vec3 dir = normalize((uCamRot * vec4(normalize(v.xyz / v.w), 0.0)).xyz);
        bool fresh = (p.x % 2) == int(uPattern.x) && (p.y % 2) == int(uPattern.y);
        vec4 nw = fresh ? texelFetch(uLow, p / 2, 0) : texture(uLow, vUv);
        vec4 hist = nw;
        bool valid = false;
        vec4 pc = uPrevVP * vec4(dir, 0.0);
        if (uValid > 0.5 && pc.w > 0.0) {
          vec2 puv = pc.xy / pc.w * 0.5 + 0.5;
          if (all(greaterThan(puv, vec2(0.001))) && all(lessThan(puv, vec2(0.999)))) { hist = texture(uHistory, puv); valid = true; }
        }
        // clamp the history to the neighbourhood of fresh samples (limits ghosting)
        vec4 lo = nw, hi = nw;
        for (int j = -1; j <= 1; j++) for (int i = -1; i <= 1; i++) {
          vec4 s = texelFetch(uLow, clamp(p / 2 + ivec2(i, j), ivec2(0), textureSize(uLow, 0) - 1), 0);
          lo = min(lo, s); hi = max(hi, s);
        }
        vec4 hc = clamp(hist, lo - 0.08 * (hi - lo) - 0.002, hi + 0.08 * (hi - lo) + 0.002);
        hist = mix(hist, hc, 0.6);
        fragColor = !valid ? nw : (fresh ? mix(hist, nw, 0.35) : hist);
      }`,
      {
        uLow: { value: null }, uHistory: { value: null },
        uInvProj: { value: new THREE.Matrix4() }, uCamRot: { value: new THREE.Matrix4() }, uPrevVP: { value: new THREE.Matrix4() },
        uPattern: { value: new THREE.Vector2() }, uValid: { value: 0 },
      }
    );
    this.prevVP = new THREE.Matrix4();
    this.hasHistory = false;

    // ---- equirect environment (atmosphere + clouds, no sun disk) ----
    const envOpts = {
      type: THREE.HalfFloatType,
      generateMipmaps: true,
      minFilter: THREE.LinearMipmapLinearFilter,
      magFilter: THREE.LinearFilter,
      wrapS: THREE.RepeatWrapping,
      wrapT: THREE.ClampToEdgeWrapping,
    };
    this.envRT = rt(1024, 512, envOpts);
    this.envRT.texture.mapping = THREE.EquirectangularReflectionMapping;
    this.envRT.texture.colorSpace = THREE.LinearSRGBColorSpace;
    this.envBands = 4;
    U.uEnvMaxLod.value = Math.log2(1024);
    this.envMat = raw(
      /* glsl */ `
      precision highp float;
      precision highp sampler3D;
      ${atmoParsGLSL}
      ${cloudParsGLSL}
      uniform float uFrame;
      uniform float uBlend;
      in vec2 vUv;
      out vec4 fragColor;
      float ign(vec2 p) { return fract(52.9829189 * fract(dot(p, vec2(0.06711056, 0.00583715)))); }
      void main() {
        vec2 uv = gl_FragCoord.xy / vec2(1024.0, 512.0);
        float phi = (uv.x - 0.5) * 2.0 * PI;
        float el = (uv.y - 0.5) * PI;
        vec3 dir = vec3(cos(phi) * cos(el), sin(el), sin(phi) * cos(el));
        vec3 col;
        if (dir.y >= -0.002) {
          col = skyRadiance(dir);
          vec4 ci = cirrusLayer(dir);
          col = col * ci.a + ci.rgb;
          float j = fract(ign(gl_FragCoord.xy + 5.588238 * mod(uFrame, 64.0)) + uFrame * 0.618034);
          vec4 c = marchClouds(vec3(0.0, uCamAltKm, 0.0), dir, 12, 3, j, 150.0);
          col = col * c.a + c.rgb;
          col = applyFogToSky(col, dir);
        } else {
          vec3 hz = horizonRadiance(dir);
          col = hz * 0.12 + skyRadiance(vec3(0.0, 1.0, 0.0)) * 0.03;
        }
        fragColor = vec4(col, uBlend);
      }`,
      { uFrame: { value: 0 }, uBlend: { value: 1 } }
    );
    this.envMat.transparent = true;
    this.envMat.blending = THREE.NormalBlending;
    this.envMat.premultipliedAlpha = false;

    // ---- cloud shadow map (top-down, around the camera) ----
    this.shadowSize = 24000;
    this.cloudShadowRT = new THREE.WebGLRenderTarget(512, 512, { type: THREE.UnsignedByteType, depthBuffer: false, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter });
    U.uCloudShadowMap.value = this.cloudShadowRT.texture;
    this.cloudShadowMat = raw(
      /* glsl */ `
      precision highp float;
      precision highp sampler3D;
      ${atmoParsGLSL}
      ${cloudParsGLSL}
      uniform vec3 uRect;
      uniform vec3 uCamW;
      in vec2 vUv;
      out vec4 fragColor;
      void main() {
        vec2 xz = uRect.xy + vUv * uRect.z;
        float sh = cloudShadow(vec3(xz.x, 0.0, xz.y), uCamW);
        fragColor = vec4(sh, sh, sh, 1.0);
      }`,
      { uRect: { value: new THREE.Vector3() }, uCamW: { value: new THREE.Vector3() } }
    );
    this.envFrames = 0;

    // ---- background (sky dome) rendered as the first thing in the main pass ----
    this.background = this._makeBackground();

    // PMREM for standard materials
    this.pmrem = new THREE.PMREMGenerator(renderer);
    this.pmremRT = null;
    this.pmremTimer = 1e9;
    this.lutDirty = true;
    this.sunColor = new THREE.Vector3(1, 1, 1);
  }

  _buildNoise() {
    const r = this.renderer;
    const size = 128;
    const rt3d = new THREE.WebGL3DRenderTarget(size, size, size, {
      type: THREE.UnsignedByteType,
      format: THREE.RGBAFormat,
      depthBuffer: false,
    });
    const t = rt3d.texture;
    t.wrapS = t.wrapT = t.wrapR = THREE.RepeatWrapping;
    t.minFilter = t.magFilter = THREE.LinearFilter;
    t.generateMipmaps = false;
    const mat = new THREE.RawShaderMaterial({
      glslVersion: THREE.GLSL3,
      vertexShader: lutVS,
      fragmentShader: noiseGenFS,
      uniforms: { uSlice: { value: 0 }, uMode: { value: 0 }, uSeed: { value: 0.137 } },
      depthTest: false,
      depthWrite: false,
    });
    this.quad.material = mat;
    const prev = r.getRenderTarget();
    for (let z = 0; z < size; z++) {
      mat.uniforms.uSlice.value = (z + 0.5) / size;
      r.setRenderTarget(rt3d, z);
      this.quad.render(r);
    }
    const weather = new THREE.WebGLRenderTarget(512, 512, {
      type: THREE.UnsignedByteType,
      depthBuffer: false,
      wrapS: THREE.RepeatWrapping,
      wrapT: THREE.RepeatWrapping,
      minFilter: THREE.LinearMipmapLinearFilter,
      magFilter: THREE.LinearFilter,
      generateMipmaps: true,
    });
    mat.uniforms.uMode.value = 1;
    r.setRenderTarget(weather);
    this.quad.render(r);
    r.setRenderTarget(prev);
    mat.dispose();
    this.uniforms.uCloudNoise.value = t;
    this.uniforms.uWeather.value = weather.texture;
    this.noiseRT = rt3d;
    this.weatherRT = weather;
  }

  _makeBackground() {
    const U = this.uniforms;
    const mat = new THREE.ShaderMaterial({
      uniforms: {
        ...U,
        uClouds: { value: null },
        uInvProj: { value: new THREE.Matrix4() },
        uCamRot: { value: new THREE.Matrix4() },
        uSunDiskScale: { value: 1 },
      },
      vertexShader: /* glsl */ `
        varying vec2 vUv;
        void main() { vUv = uv; gl_Position = vec4(position.xy, 1.0, 1.0); }`,
      fragmentShader: /* glsl */ `
        precision highp sampler3D;
        ${atmoParsGLSL}
        ${cloudParsGLSL}
        uniform sampler2D uClouds;
        uniform mat4 uInvProj;
        uniform mat4 uCamRot;
        uniform float uSunDiskScale;
        varying vec2 vUv;
        void main() {
          vec2 ndc = vUv * 2.0 - 1.0;
          vec4 v = uInvProj * vec4(ndc, 1.0, 1.0);
          vec3 dir = normalize((uCamRot * vec4(normalize(v.xyz / v.w), 0.0)).xyz);
          vec3 col = skyRadiance(dir);
          // sun disk with limb darkening
          float cosA = dot(dir, uSunDir);
          float sunR = 0.004654 * uSunDiskScale;
          float cosR = cos(sunR);
          if (cosA > cosR - 0.00002) {
            float a = acos(clamp(cosA, -1.0, 1.0)) / sunR;
            float mu = sqrt(max(1.0 - a * a, 0.0));
            float limb = 1.0 - 0.6 * (1.0 - mu) - 0.2 * (1.0 - mu) * (1.0 - mu);
            vec3 Ts = getTransmittance(Rg + max(uCamAltKm, 0.001), dir.y);
            vec3 sunL = uSunE * Ts / (PI * sunR * sunR) * limb;
            float edge = smoothstep(cosR - 0.00002, cosR + 0.00002, cosA);
            col += min(sunL, vec3(40000.0)) * edge;
          }
          vec4 ci = cirrusLayer(dir);
          col = col * ci.a + ci.rgb;
          vec4 c = texture(uClouds, vUv);
          col = col * c.a + c.rgb;
          col = applyFogToSky(col, dir);
          gl_FragColor = vec4(col, 1.0);
        }`,
      depthTest: false,
      depthWrite: false,
    });
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute([-1, -1, 0, 3, -1, 0, -1, 3, 0], 3));
    geo.setAttribute('uv', new THREE.Float32BufferAttribute([0, 0, 2, 0, 0, 2], 2));
    const mesh = new THREE.Mesh(geo, mat);
    mesh.frustumCulled = false;
    mesh.renderOrder = -1000;
    return mesh;
  }

  setHaze(haze) {
    this.params.haze = haze;
    this.uniforms.uHaze.value = haze;
    this.lutDirty = true;
  }

  setSunDirection(dir) {
    this.uniforms.uSunDir.value.copy(dir).normalize();
    this.lutDirty = true;
  }

  /** sun illuminance at a given altitude (m), used for DirectionalLight */
  sunIlluminanceAt(altM = 0) {
    return sunTransmittanceCPU(altM / 1000, this.uniforms.uSunDir.value, this.params).multiplyScalar(SUN_E);
  }

  resize(w, h) {
    const cw = Math.max(2, Math.floor(w / 2) & ~1), ch = Math.max(2, Math.floor(h / 2) & ~1);
    for (const r of this.cloudRT) r.setSize(cw, ch);
    this.cloudLow.setSize(cw / 2, ch / 2);
    this.cloudMat.uniforms.uRes.value.set(cw / 2, ch / 2);
    this.cloudMat.uniforms.uHalfRes.value.set(cw, ch);
    this.hasHistory = false;
  }

  resetClouds() { this.hasHistory = false; }

  update(dt, camera, opts = {}) {
    const r = this.renderer;
    const U = this.uniforms;
    this.frame++;
    U.uCloudTime.value += dt;
    U.uCamAltKm.value = Math.max(camera.position.y, 1) / 1000;
    U.uCamXZ.value.set(camera.position.x / 1000, camera.position.z / 1000);
    const wind = opts.cloudWind || new THREE.Vector2(0.008, 0.002);
    U.uWindOffset.value.addScaledVector(wind, dt);

    // CPU-side derived quantities
    const p = this.params;
    const e0 = mediumExt(0, p);
    U.uExtinctionSea.value.set(e0[0] / 1000, e0[1] / 1000, e0[2] / 1000);
    this.sunColor.copy(this.sunIlluminanceAt(camera.position.y));
    // fog layer dims the direct sun
    const fd = U.uFogDensity.value;
    if (fd > 0) this.sunColor.multiplyScalar(Math.exp(-fd * 250 / Math.max(U.uSunDir.value.y, 0.04)));
    U.uSunColor.value.copy(this.sunColor);

    const prevRT = r.getRenderTarget();
    const prevAuto = r.autoClear;
    r.autoClear = false;

    if (this.lutDirty) {
      this.quad.material = this.transMat;
      r.setRenderTarget(this.transmittance);
      this.quad.render(r);
      this.quad.material = this.msMat;
      r.setRenderTarget(this.multiScat);
      this.quad.render(r);
      this.lutDirty = false;
      this.envFrames = 0;
    }
    // sky-view LUT every frame (camera altitude can change)
    this.quad.material = this.skyViewMat;
    r.setRenderTarget(this.skyView);
    this.quad.render(r);

    // screen clouds
    camera.updateMatrixWorld();
    const rot = new THREE.Matrix4().extractRotation(camera.matrixWorld);
    const cm = this.cloudMat.uniforms;
    cm.uInvProj.value.copy(camera.projectionMatrixInverse);
    cm.uCamRot.value.copy(rot);
    cm.uPrevVP.value.copy(this.prevVP);
    const src = this.cloudRT[this.cloudCur];
    const dst = this.cloudRT[1 - this.cloudCur];
    const pats = [[0, 0], [1, 1], [1, 0], [0, 1]];
    const pat = pats[this.frame % 4];
    cm.uFrame.value = this.frame;
    cm.uPattern.value.set(pat[0], pat[1]);
    cm.uSteps.value = opts.cloudSteps || 36;
    this.quad.material = this.cloudMat;
    r.setRenderTarget(this.cloudLow);
    this.quad.render(r);
    const rm = this.resolveMat.uniforms;
    rm.uLow.value = this.cloudLow.texture;
    rm.uHistory.value = src.texture;
    rm.uInvProj.value.copy(camera.projectionMatrixInverse);
    rm.uCamRot.value.copy(rot);
    rm.uPrevVP.value.copy(this.prevVP);
    rm.uPattern.value.set(pat[0], pat[1]);
    rm.uValid.value = this.hasHistory ? 1 : 0;
    this.quad.material = this.resolveMat;
    r.setRenderTarget(dst);
    this.quad.render(r);
    this.cloudCur = 1 - this.cloudCur;
    this.hasHistory = true;
    const viewRot = rot.clone().invert();
    this.prevVP.multiplyMatrices(camera.projectionMatrix, viewRot);

    // environment map: one horizontal band every other frame, blended in place
    const envTick = this.envFrames < this.envBands * 2 || this.frame % 2 === 0;
    const band = Math.floor(this.frame / (this.envFrames < this.envBands * 2 ? 1 : 2)) % this.envBands;
    const bh = 512 / this.envBands;
    this.envRT.scissor.set(0, band * bh, 1024, bh);
    this.envRT.scissorTest = true;
    this.envMat.uniforms.uFrame.value = this.frame;
    this.envMat.uniforms.uBlend.value = this.envFrames < this.envBands * 2 ? 1.0 : 0.25;
    if (envTick) {
      this.quad.material = this.envMat;
      r.setRenderTarget(this.envRT);
      this.quad.render(r);
      this.envFrames++;
    }
    this.envRT.scissorTest = false;
    U.uEnvMap.value = this.envRT.texture;

    // cloud shadows on the ground/sea, snapped to texels
    const texel = this.shadowSize / 512;
    const ox = Math.floor((camera.position.x - this.shadowSize / 2) / texel) * texel;
    const oz = Math.floor((camera.position.z - this.shadowSize / 2) / texel) * texel;
    if (this.frame % 4 === 0 || this.frame < 3) {
      U.uCloudShadowRect.value.set(ox, oz, this.shadowSize);
      this.cloudShadowMat.uniforms.uRect.value.set(ox, oz, this.shadowSize);
      this.cloudShadowMat.uniforms.uCamW.value.set(camera.position.x, 0, camera.position.z);
      this.quad.material = this.cloudShadowMat;
      r.setRenderTarget(this.cloudShadowRT);
      this.quad.render(r);
    }

    r.setRenderTarget(prevRT);
    r.autoClear = prevAuto;

    // background uniforms
    const bu = this.background.material.uniforms;
    bu.uClouds.value = dst.texture;
    bu.uInvProj.value.copy(camera.projectionMatrixInverse);
    bu.uCamRot.value.copy(rot);

    // PMREM for lit materials, refreshed periodically
    this.pmremTimer += dt;
    if (this.pmremTimer > (this.envFrames < 30 ? 0.25 : 2.0)) {
      this.pmremTimer = 0;
      this.pmremRT = this.pmrem.fromEquirectangular(this.envRT.texture, this.pmremRT);
      return this.pmremRT.texture;
    }
    return null;
  }
}
