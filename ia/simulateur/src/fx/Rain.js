import * as THREE from 'three';

// Pluie : gouttes en traînées autour de la caméra (flou de bougé d'une caméra réelle), poussées par le
// vent. Deux nuages de gouttes : un proche (moins de 7 m, grosses traînées floues car hors de la
// profondeur de champ) et un lointain (traits fins). Tout le mouvement est calculé dans le shader.

const COUNT = 24000;

export class Rain {
  constructor() {
    const quad = new THREE.InstancedBufferGeometry();
    quad.setAttribute('position', new THREE.Float32BufferAttribute([-0.5, 0, 0, 0.5, 0, 0, 0.5, 1, 0, -0.5, 1, 0], 3));
    quad.setIndex([0, 1, 2, 0, 2, 3]);
    const seeds = new Float32Array(COUNT * 4);
    for (let i = 0; i < seeds.length; i++) seeds[i] = Math.random();
    quad.setAttribute('aSeed', new THREE.InstancedBufferAttribute(seeds, 4));
    quad.instanceCount = COUNT;
    this.uniforms = {
      uTime: { value: 0 },
      uCam: { value: new THREE.Vector3() },
      uVel: { value: new THREE.Vector3(0, -8.5, 0) },
      uBox: { value: new THREE.Vector3(60, 30, 60) },
      uNearBox: { value: new THREE.Vector3(14, 9, 14) },
      uRain: { value: 0 },
      uLight: { value: new THREE.Vector3(1, 1, 1) },
      uStreak: { value: 0.045 },
      uPixel: { value: 0.0012 },
    };
    this.material = new THREE.ShaderMaterial({
      uniforms: this.uniforms,
      transparent: true,
      depthWrite: false,
      // the streak quads face the camera one way or the other depending on the wind: never cull them
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
      vertexShader: /* glsl */ `
        attribute vec4 aSeed;
        uniform float uTime;
        uniform vec3 uCam;
        uniform vec3 uVel;
        uniform vec3 uBox;
        uniform vec3 uNearBox;
        uniform float uRain;
        uniform float uStreak;
        uniform float uPixel;
        varying float vAlpha;
        varying float vU;
        varying float vV;
        varying float vWide;
        void main() {
          vAlpha = 0.0; vU = position.x; vV = position.y; vWide = 0.0;
          if (aSeed.w > uRain) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }
          bool near = fract(aSeed.w * 37.13 + aSeed.x * 3.1) < 0.45;
          vec3 box = near ? uNearBox : uBox;
          // each drop falls at its own speed; positions wrap in a box that follows the camera
          vec3 vel = uVel * (0.85 + 0.3 * aSeed.y);
          vec3 lo = uCam - box * vec3(0.5, 0.35, 0.5);
          vec3 p = mod(aSeed.xyz * box + vel * uTime - lo, box) + lo;
          vec3 tail = p - vel * uStreak * (0.8 + 0.4 * aSeed.z);
          vec3 toCam = cameraPosition - p;
          float dist = length(toCam);
          // apparent width: the drop itself (~2 mm) or the defocus disc of the small lens, at least a pixel
          float dropPx = 0.0021 / max(dist, 0.05) / uPixel;
          float blurPx = 0.0028 / max(dist, 0.05) / uPixel;
          float wPx = max(1.0, max(dropPx, blurPx));
          float width = wPx * dist * uPixel;
          // a soft profile across the streak only makes sense when it is several pixels wide
          // (on a thinner quad the pixel centre falls outside it and the varyings extrapolate)
          vWide = clamp((wPx - 1.5) * 0.5, 0.0, 1.0);
          vec3 dir = normalize(p - tail);
          vec3 side = normalize(cross(dir, toCam));
          vec3 wp = mix(p, tail, position.y) + side * position.x * width;
          // a wider (blurred) streak spreads the same light: keep the energy
          vAlpha = clamp(dropPx / wPx, 0.12, 1.0) * (0.55 + 0.45 * aSeed.z);
          float edge = min(min(p.x - lo.x, lo.x + box.x - p.x), min(p.z - lo.z, lo.z + box.z - p.z));
          // drops brushing past the lens (closer than ~0.6 m, head or tail) would be huge out-of-focus
          // smears crossing the whole frame: the lens shader shows them as drops on the dome instead
          float distTail = length(cameraPosition - tail);
          vAlpha *= smoothstep(0.0, box.x * 0.12, edge) * smoothstep(0.35, 0.9, min(dist, distTail));
          // near drops: their box ends where the far one takes over
          if (!near) vAlpha *= smoothstep(5.0, 8.0, dist);
          gl_Position = projectionMatrix * viewMatrix * vec4(wp, 1.0);
        }`,
      fragmentShader: /* glsl */ `
        uniform vec3 uLight;
        varying float vAlpha;
        varying float vU;
        varying float vV;
        varying float vWide;
        void main() {
          // soft across (wide, blurred streaks), brighter at the head of the streak
          float across = mix(1.0, 1.0 - smoothstep(0.2, 0.5, abs(vU)), vWide);
          float a = vAlpha * across * (0.55 + 0.45 * (1.0 - clamp(vV, 0.0, 1.0)));
          gl_FragColor = vec4(uLight * max(a, 0.0), 1.0);
        }`,
    });
    this.mesh = new THREE.Mesh(quad, this.material);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = 50;
    this.mesh.visible = false;
  }

  update(dt, camera, rain, windTo, windSpeed, skyRadiance, height) {
    const u = this.uniforms;
    u.uTime.value = (u.uTime.value + dt) % 10000;
    u.uCam.value.copy(camera.position);
    u.uRain.value = rain;
    // heavier rain falls a bit faster; the wind tilts it
    const fall = 6.5 + rain * 3;
    u.uVel.value.set(Math.sin(windTo) * windSpeed * 0.8, -fall, -Math.cos(windTo) * windSpeed * 0.8);
    // a drop is a tiny lens: it shows the bright sky above it, brighter than the sea behind
    u.uLight.value.copy(skyRadiance).multiplyScalar(1.9);
    u.uPixel.value = (2 * Math.tan((camera.fov * Math.PI) / 360)) / Math.max(height, 1);
    this.mesh.visible = rain > 0.01;
  }
}

// GLSL: impacts de gouttes sur la mer (anneaux qui s'élargissent), en pente à ajouter à la normale
export const rainRipplesGLSL = /* glsl */ `
uniform float uRain;
vec2 rr_hash(vec2 p) { vec3 p3 = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973)); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.xx + p3.yz) * p3.zy); }
vec3 rainRipples(vec2 p, float t) {
  vec2 g = vec2(0.0);
  float splash = 0.0;
  for (int layer = 0; layer < 3; layer++) {
    float s = layer == 0 ? 0.62 : (layer == 1 ? 0.37 : 0.21);
    vec2 q = p / s + float(layer) * 17.31;
    vec2 cell = floor(q);
    vec2 rnd = rr_hash(cell);
    if (rnd.x > 0.35 + uRain * 0.65) continue; // fewer impacts in light rain
    float period = 0.7 + rnd.y * 0.7;
    float life = fract(t / period + rnd.x * 7.0);
    vec2 c = cell + 0.25 + 0.5 * rr_hash(cell + 3.7);
    vec2 d = q - c;
    float r = length(d);
    float R = life * 0.42;
    float k = (r - R) / 0.055;
    float amp = (1.0 - life) * (1.0 - life) * (0.35 + 0.65 * rr_hash(cell + 9.1).x);
    float dr = -2.0 * k * exp(-k * k) * amp / 0.055;
    g += d / max(r, 1e-4) * dr * 0.012 / s;
    splash += exp(-r * r / 0.004) * smoothstep(0.12, 0.0, life);
  }
  return vec3(g, splash);
}
`;
