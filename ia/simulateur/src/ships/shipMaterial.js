import * as THREE from 'three';
import { atmoParsGLSL } from '../sky/atmosphereGLSL.js';
import { EARTH_CURV } from '../ocean/OceanSurface.js';

// Standard PBR materials extended with: Earth curvature (hull-down ships at
// range), aerial perspective consistent with the sky, and procedural weathering
// (boot-top, rust streaks, grime, windows, corrugation) in object space.

export const PAINT = { PLAIN: 0, HULL: 1, HOUSE: 2, DECK: 3, CONTAINER: 4, METAL: 5, SAIL: 6 };

let SKY_UNIFORMS = null;
export function setSkyUniforms(u) { SKY_UNIFORMS = u; }

const noiseGLSL = /* glsl */ `
float sh_hash(vec2 p) { vec3 p3 = fract(vec3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }
float sh_noise(vec2 p) {
  vec2 i = floor(p), f = fract(p); vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(sh_hash(i), sh_hash(i + vec2(1, 0)), u.x), mix(sh_hash(i + vec2(0, 1)), sh_hash(i + vec2(1, 1)), u.x), u.y);
}
float sh_fbm(vec2 p) { float s = 0.0, a = 0.5; for (int i = 0; i < 5; i++) { s += a * sh_noise(p); p *= 2.03; a *= 0.5; } return s; }
`;

export function makeShipMaterial(opts = {}) {
  const {
    color = 0xffffff, colorB = 0x7a1f1a, roughness = 0.6, metalness = 0.1,
    mode = PAINT.PLAIN, waterline = 0, bootTop = 0.6, rust = 0.4, grime = 0.4,
    levelH = 2.8, deckBase = 0, bridgeLevel = 99, winW = 1.1, winSpacing = 2.2, seed = Math.random() * 100,
    side = THREE.FrontSide, map = null, transparent = false, opacity = 1,
  } = opts;
  const mat = new THREE.MeshStandardMaterial({ color, roughness, metalness, side, map, transparent, opacity, envMapIntensity: 1 });
  const uniforms = {
    uMode: { value: mode },
    uColB: { value: new THREE.Color(colorB) },
    uWaterline: { value: waterline },
    uBootTop: { value: bootTop },
    uRust: { value: rust },
    uGrime: { value: grime },
    uLevelH: { value: levelH },
    uDeckBase: { value: deckBase },
    uBridgeLevel: { value: bridgeLevel },
    uWinW: { value: winW },
    uWinSpacing: { value: winSpacing },
    uSeed: { value: seed },
    uCurv: { value: EARTH_CURV },
  };
  mat.userData.paint = uniforms;
  mat.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, SKY_UNIFORMS || {}, uniforms);
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', `#include <common>
        varying vec3 vLocal;
        varying vec3 vLocalN;
        varying vec3 vWPosA;
        uniform float uCurv;`)
      .replace('#include <begin_vertex>', `#include <begin_vertex>
        vLocal = position; vLocalN = normal;`)
      .replace('#include <project_vertex>', `
        vec4 mvPosition = vec4( transformed, 1.0 );
        #ifdef USE_INSTANCING
          mvPosition = instanceMatrix * mvPosition;
        #endif
        vec4 wpC = modelMatrix * mvPosition;
        vWPosA = wpC.xyz;
        vec2 dcC = wpC.xz - cameraPosition.xz;
        wpC.y -= dot(dcC, dcC) * uCurv;
        mvPosition = viewMatrix * wpC;
        gl_Position = projectionMatrix * mvPosition;`);
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>
        ${atmoParsGLSL}
        ${noiseGLSL}
        varying vec3 vLocal;
        varying vec3 vLocalN;
        varying vec3 vWPosA;
        uniform float uMode; uniform vec3 uColB; uniform float uWaterline; uniform float uBootTop;
        uniform float uRust; uniform float uGrime; uniform float uLevelH; uniform float uDeckBase;
        uniform float uBridgeLevel; uniform float uWinW; uniform float uWinSpacing; uniform float uSeed;
        float glassMask = 0.0;`)
      .replace('#include <color_fragment>', `#include <color_fragment>
        {
          vec3 lp = vLocal + uSeed;
          vec3 an = abs(vLocalN);
          float grimeN = sh_fbm(vec2(lp.x * 0.35 + lp.z * 0.35, lp.y * 1.6));
          if (uMode == 1.0) {
            // hull: topside paint, boot-top / antifouling, rust streaks, algae line
            float yWL = vLocal.y - uWaterline;
            vec3 top = diffuseColor.rgb;
            float boot = smoothstep(uBootTop + 0.04, uBootTop - 0.04, yWL);
            vec3 c = mix(top, uColB, boot);
            float streak = sh_fbm(vec2(lp.x * 2.3 + lp.z * 2.3, lp.y * 0.08));
            float spots = smoothstep(0.62, 0.8, sh_fbm(vec2(lp.x * 0.9 + lp.z, lp.y * 0.5) * 1.3));
            float rustAmt = uRust * (smoothstep(0.55, 0.85, streak) * 0.8 + spots * 0.6);
            rustAmt *= smoothstep(-0.2, 1.5, yWL);
            c = mix(c, vec3(0.33, 0.14, 0.06) * (0.7 + 0.6 * grimeN), clamp(rustAmt, 0.0, 0.85));
            float algae = smoothstep(0.35, 0.0, abs(yWL - 0.15)) * 0.6;
            c = mix(c, vec3(0.12, 0.14, 0.07), algae * uGrime);
            c *= mix(1.0, 0.75 + 0.35 * grimeN, uGrime);
            diffuseColor.rgb = c;
          } else if (uMode == 2.0) {
            // deckhouse: rows of windows on vertical faces, grime streaks below them
            float lvl = floor((vLocal.y - uDeckBase) / uLevelH);
            float yl = mod(vLocal.y - uDeckBase, uLevelH) / uLevelH;
            float t = an.z > an.x ? vLocal.x : vLocal.z;
            bool vertical = an.y < 0.4;
            float isBridge = step(uBridgeLevel - 0.5, lvl) * step(lvl, uBridgeLevel + 0.5);
            float wW = mix(uWinW, uWinSpacing * 0.86, isBridge);
            float sill = mix(0.42, 0.36, isBridge), head = mix(0.78, 0.86, isBridge);
            float inRow = step(sill, yl) * step(yl, head);
            float inCol = step(abs(mod(t, uWinSpacing) - uWinSpacing * 0.5), wW * 0.5);
            float lit = sh_hash(vec2(floor(t / uWinSpacing), lvl) + uSeed);
            if (vertical && inRow * inCol > 0.5 && lvl >= 0.0) {
              glassMask = 1.0;
              diffuseColor.rgb = vec3(0.015, 0.02, 0.025) * (0.6 + lit * 0.8);
            } else {
              float under = smoothstep(0.42, 0.1, yl) * smoothstep(0.4, 0.8, sh_fbm(vec2(t * 3.0, yl * 2.0)));
              diffuseColor.rgb *= 1.0 - under * 0.25 * uGrime;
              diffuseColor.rgb *= mix(1.0, 0.82 + 0.25 * grimeN, uGrime);
            }
          } else if (uMode == 3.0) {
            float wear = sh_fbm(lp.xz * 0.6);
            diffuseColor.rgb *= 0.75 + 0.4 * wear;
            diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.3, 0.16, 0.08), smoothstep(0.65, 0.85, wear) * uRust);
          } else if (uMode == 4.0) {
            float d = sh_fbm(vec2(lp.x * 0.7, lp.y * 3.0) + lp.z);
            diffuseColor.rgb *= 0.8 + 0.3 * d;
            diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.3, 0.15, 0.08), smoothstep(0.7, 0.9, d) * uRust);
          } else if (uMode == 5.0 || uMode == 0.0) {
            diffuseColor.rgb *= mix(1.0, 0.8 + 0.3 * grimeN, uGrime);
          }
        }`)
      .replace('#include <roughnessmap_fragment>', `#include <roughnessmap_fragment>
        if (glassMask > 0.5) roughnessFactor = 0.04;`)
      .replace('#include <metalnessmap_fragment>', `#include <metalnessmap_fragment>
        if (glassMask > 0.5) metalnessFactor = 0.0;`)
      .replace('#include <normal_fragment_maps>', `#include <normal_fragment_maps>
        if (uMode == 4.0) {
          // corrugated container walls
          vec3 an2 = abs(vLocalN);
          if (an2.y < 0.5) {
            float t2 = an2.z > an2.x ? vLocal.x : vLocal.z;
            float c = cos(t2 * 6.2831 / 0.28);
            vec3 tg = normalize(cross(normal, vec3(0.0, 1.0, 0.0)) + 1e-5);
            normal = normalize(normal + tg * c * 0.22);
          }
        }`)
      .replace('#include <fog_fragment>', `
        gl_FragColor.rgb = applyAerial(gl_FragColor.rgb, vWPosA - cameraPosition);`);
  };
  mat.customProgramCacheKey = () => 'ship-paint-v1';
  return mat;
}

/** Simple emissive material (navigation lights, lamps), with aerial perspective */
export function makeLightMaterial(color, intensity = 40) {
  const mat = new THREE.MeshBasicMaterial({ color: new THREE.Color(color).multiplyScalar(intensity) });
  return mat;
}

/** Curvature + aerial perspective for materials coming from glTF models */
export function patchExternalMaterial(mat) {
  if (mat.userData.patched) return mat;
  mat.userData.patched = true;
  // untextured models look too clean: add streaks of grime and salt in world space
  const uniforms = { uCurv: { value: EARTH_CURV }, uGrimeExt: { value: mat.map ? 0 : 1 } };
  mat.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, SKY_UNIFORMS || {}, uniforms);
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', `#include <common>
        varying vec3 vWPosA;
        uniform float uCurv;`)
      .replace('#include <project_vertex>', `
        vec4 mvPosition = vec4( transformed, 1.0 );
        #ifdef USE_INSTANCING
          mvPosition = instanceMatrix * mvPosition;
        #endif
        vec4 wpC = modelMatrix * mvPosition;
        vWPosA = wpC.xyz;
        vec2 dcC = wpC.xz - cameraPosition.xz;
        wpC.y -= dot(dcC, dcC) * uCurv;
        mvPosition = viewMatrix * wpC;
        gl_Position = projectionMatrix * mvPosition;`);
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>
        ${atmoParsGLSL}
        ${noiseGLSL}
        uniform float uGrimeExt;
        varying vec3 vWPosA;`)
      .replace('#include <color_fragment>', `#include <color_fragment>
        if (uGrimeExt > 0.5) {
          vec3 wp = vWPosA * 0.6;
          float streak = sh_fbm(vec2(wp.x + wp.z, wp.y * 0.12) * 2.2);
          float blot = sh_fbm(wp.xz * 0.35 + wp.y * 0.4);
          diffuseColor.rgb *= 0.78 + 0.3 * blot;
          diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.32, 0.17, 0.08), smoothstep(0.62, 0.85, streak) * 0.35);
        }`)
      .replace('#include <fog_fragment>', `
        gl_FragColor.rgb = applyAerial(gl_FragColor.rgb, vWPosA - cameraPosition);`);
  };
  mat.customProgramCacheKey = () => 'ext-ship-v2-' + (mat.map ? 't' : 'u');
  mat.needsUpdate = true;
  return mat;
}
