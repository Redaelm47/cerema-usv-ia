// Physically based atmosphere (Hillaire 2020, "A Scalable and Production Ready
// Sky and Atmosphere Rendering Technique"): transmittance LUT, multiple
// scattering LUT, sky-view LUT. Units: km for the atmosphere, metres in world.

export const atmoParsGLSL = /* glsl */ `
#ifndef PI
#define PI 3.141592653589793
#endif
const float Rg = 6360.0;
const float Rt = 6460.0;
uniform sampler2D uTransmittanceLUT;
uniform sampler2D uMultiScatLUT;
uniform sampler2D uSkyViewLUT;
uniform vec3 uSunDir;          // world, y up
uniform vec3 uSunE;            // solar illuminance at top of atmosphere
uniform vec3 uRayleighScat;    // 1/km
uniform float uMieScat;        // 1/km
uniform float uMieAbs;         // 1/km
uniform vec3 uOzoneAbs;        // 1/km
uniform float uHaze;           // low-level aerosol multiplier
uniform float uHazeHeight;     // km
uniform float uCamAltKm;
uniform vec3 uExtinctionSea;   // 1/m, sea-level extinction for aerial perspective
uniform float uFogDensity;     // extra marine fog (1/m)
uniform vec3 uFogColor;

struct Medium { vec3 scatR; float scatM; vec3 ext; };

Medium sampleMedium(float h) {
  h = max(h, 0.0);
  float dR = exp(-h / 8.0);
  float dM = exp(-h / 1.2) + uHaze * exp(-h / uHazeHeight);
  float dO = max(0.0, 1.0 - abs(h - 25.0) / 15.0);
  Medium m;
  m.scatR = uRayleighScat * dR;
  m.scatM = uMieScat * dM;
  m.ext = m.scatR + vec3((uMieScat + uMieAbs) * dM) + uOzoneAbs * dO;
  return m;
}

// nearest positive intersection distance with sphere centred at origin, -1 if none
float raySphere(vec3 ro, vec3 rd, float R) {
  float b = dot(ro, rd);
  float c = dot(ro, ro) - R * R;
  float d = b * b - c;
  if (d < 0.0) return -1.0;
  d = sqrt(d);
  float t0 = -b - d, t1 = -b + d;
  if (t0 > 0.0) return t0;
  if (t1 > 0.0) return t1;
  return -1.0;
}

float rayleighPhase(float c) { return 3.0 / (16.0 * PI) * (1.0 + c * c); }
float cornetteShanks(float g, float c) {
  float g2 = g * g;
  float k = 3.0 / (8.0 * PI) * (1.0 - g2) / (2.0 + g2);
  return k * (1.0 + c * c) / pow(max(1.0 + g2 - 2.0 * g * c, 1e-4), 1.5);
}
float hgPhase(float g, float c) {
  float g2 = g * g;
  return (1.0 - g2) / (4.0 * PI * pow(max(1.0 + g2 - 2.0 * g * c, 1e-4), 1.5));
}

vec2 transmittanceUV(float r, float mu) {
  float H = sqrt(Rt * Rt - Rg * Rg);
  float rho = sqrt(max(r * r - Rg * Rg, 0.0));
  float disc = r * r * (mu * mu - 1.0) + Rt * Rt;
  float d = max(0.0, -r * mu + sqrt(max(disc, 0.0)));
  float dMin = Rt - r, dMax = rho + H;
  float xMu = (d - dMin) / max(dMax - dMin, 1e-4);
  float xR = rho / H;
  // half texel remap (256 x 64)
  return vec2(0.5 / 256.0 + xMu * (1.0 - 1.0 / 256.0), 0.5 / 64.0 + xR * (1.0 - 1.0 / 64.0));
}

vec3 getTransmittance(float r, float mu) {
  return texture(uTransmittanceLUT, transmittanceUV(r, mu)).rgb;
}

// transmittance to the sun from a point, 0 when the planet blocks it
vec3 sunTransmittance(vec3 p, vec3 sunDir) {
  float r = length(p);
  float mu = dot(p / r, sunDir);
  float muHorizon = -sqrt(max(1.0 - (Rg * Rg) / (r * r), 0.0));
  float fade = smoothstep(muHorizon - 0.004, muHorizon + 0.004, mu);
  return getTransmittance(r, mu) * fade;
}

vec3 getMultiScat(float r, float mu) {
  vec2 uv = vec2(clamp(mu * 0.5 + 0.5, 0.0, 1.0), clamp((r - Rg) / (Rt - Rg), 0.0, 1.0));
  uv = 0.5 / 32.0 + uv * (31.0 / 32.0);
  return texture(uMultiScatLUT, uv).rgb;
}

vec2 skyViewUV(vec3 dir) {
  float r = Rg + max(uCamAltKm, 0.001);
  float vHorizon = sqrt(max(r * r - Rg * Rg, 0.0));
  float beta = acos(clamp(vHorizon / r, -1.0, 1.0));
  float zha = PI - beta;
  float vz = acos(clamp(dir.y, -1.0, 1.0));
  float v;
  if (vz < zha) {
    float c = 1.0 - sqrt(max(1.0 - vz / zha, 0.0));
    v = c * 0.5;
  } else {
    v = sqrt(clamp((vz - zha) / beta, 0.0, 1.0)) * 0.5 + 0.5;
  }
  vec2 d2 = dir.xz; vec2 s2 = uSunDir.xz;
  float ld = length(d2), ls = length(s2);
  float cphi = (ld > 1e-5 && ls > 1e-5) ? dot(d2, s2) / (ld * ls) : 1.0;
  float phi = acos(clamp(cphi, -1.0, 1.0));
  float u = sqrt(phi / PI);
  return vec2(0.5 / 192.0 + u * (1.0 - 1.0 / 192.0), 0.5 / 108.0 + v * (1.0 - 1.0 / 108.0));
}

// sky radiance (no sun disk) in a world direction, as seen from the camera
vec3 skyRadiance(vec3 dir) {
  return texture(uSkyViewLUT, skyViewUV(dir)).rgb;
}

// radiance of the sky just above the horizon in this azimuth: the colour distant
// objects fade into.
vec3 horizonRadiance(vec3 dir) {
  vec3 d = normalize(vec3(dir.x, 0.0, dir.z) + vec3(0.0, 0.012, 0.0));
  return skyRadiance(d);
}

// Aerial perspective for an object at world-space offset 'toPoint' (metres) from
// the camera. Homogeneous low-level approximation, consistent with the sky LUT.
// marine fog: whiter than clear-air haze, lit by the diffuse daylight
vec3 fogRadiance(vec3 dir) {
  vec3 hz = horizonRadiance(dir);
  float l = dot(hz, vec3(0.2126, 0.7152, 0.0722));
  return mix(vec3(l), hz, 0.3) * 1.08 * uFogColor;
}

vec3 applyAerial(vec3 color, vec3 toPoint) {
  float d = length(toPoint);
  vec3 dir = toPoint / max(d, 1e-3);
  vec3 T = exp(-(uExtinctionSea + uFogDensity) * d);
  vec3 inscatter = horizonRadiance(dir);
  float fogW = uFogDensity / (uFogDensity + dot(uExtinctionSea, vec3(0.333)) + 1e-9);
  inscatter = mix(inscatter, fogRadiance(dir), fogW);
  return color * T + inscatter * (1.0 - T);
}

// sky seen through a fog layer ~250 m thick
vec3 applyFogToSky(vec3 col, vec3 dir) {
  if (uFogDensity <= 0.0) return col;
  float T = exp(-uFogDensity * 250.0 / (max(dir.y, 0.0) + 0.004));
  return col * T + fogRadiance(dir) * (1.0 - T);
}
`;

// ---- LUT generation shaders --------------------------------------------------

export const lutVS = /* glsl */ `
precision highp float;
in vec3 position;
in vec2 uv;
out vec2 vUv;
void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`;

export const transmittanceFS = /* glsl */ `
precision highp float;
${atmoParsGLSL}
in vec2 vUv;
out vec4 fragColor;
void main() {
  vec2 uv = (gl_FragCoord.xy - 0.5) / vec2(255.0, 63.0);
  float H = sqrt(Rt * Rt - Rg * Rg);
  float rho = H * uv.y;
  float r = sqrt(rho * rho + Rg * Rg);
  float dMin = Rt - r, dMax = rho + H;
  float d = dMin + uv.x * (dMax - dMin);
  float mu = d == 0.0 ? 1.0 : (H * H - rho * rho - d * d) / (2.0 * r * d);
  mu = clamp(mu, -1.0, 1.0);
  vec3 ro = vec3(0.0, r, 0.0);
  vec3 rd = vec3(sqrt(max(1.0 - mu * mu, 0.0)), mu, 0.0);
  float tMax = raySphere(ro, rd, Rt);
  vec3 od = vec3(0.0);
  const int STEPS = 48;
  float dt = tMax / float(STEPS);
  for (int i = 0; i < STEPS; i++) {
    vec3 p = ro + rd * (float(i) + 0.5) * dt;
    od += sampleMedium(length(p) - Rg).ext * dt;
  }
  fragColor = vec4(exp(-od), 1.0);
}`;

export const multiScatFS = /* glsl */ `
precision highp float;
${atmoParsGLSL}
in vec2 vUv;
out vec4 fragColor;
void main() {
  vec2 uv = (gl_FragCoord.xy - 0.5) / 31.0;
  float sunMu = uv.x * 2.0 - 1.0;
  float h = max(uv.y * (Rt - Rg), 0.0005);
  vec3 ro = vec3(0.0, Rg + h, 0.0);
  vec3 sunDir = vec3(0.0, sunMu, sqrt(max(1.0 - sunMu * sunMu, 0.0)));
  const int SQ = 8;
  const int STEPS = 20;
  vec3 lum = vec3(0.0), fms = vec3(0.0);
  float iso = 1.0 / (4.0 * PI);
  for (int i = 0; i < SQ; i++) {
    for (int j = 0; j < SQ; j++) {
      float theta = 2.0 * PI * (float(i) + 0.5) / float(SQ);
      float phi = acos(1.0 - 2.0 * (float(j) + 0.5) / float(SQ));
      vec3 rd = vec3(cos(theta) * sin(phi), cos(phi), sin(theta) * sin(phi));
      float tG = raySphere(ro, rd, Rg);
      float tT = raySphere(ro, rd, Rt);
      float tMax = tG > 0.0 ? tG : tT;
      float dt = tMax / float(STEPS);
      vec3 T = vec3(1.0), L = vec3(0.0), F = vec3(0.0);
      for (int s = 0; s < STEPS; s++) {
        vec3 p = ro + rd * (float(s) + 0.5) * dt;
        Medium m = sampleMedium(length(p) - Rg);
        vec3 scat = m.scatR + vec3(m.scatM);
        vec3 stepT = exp(-m.ext * dt);
        vec3 Ts = sunTransmittance(p, sunDir);
        vec3 S = scat * iso * Ts;
        vec3 ext = max(m.ext, vec3(1e-7));
        L += T * (S - S * stepT) / ext;
        F += T * (scat - scat * stepT) / ext;
        T *= stepT;
      }
      if (tG > 0.0) {
        vec3 p = ro + rd * tG;
        vec3 up = normalize(p);
        vec3 Ts = sunTransmittance(p, sunDir);
        L += T * Ts * max(dot(up, sunDir), 0.0) * 0.06 / PI;
      }
      lum += L / float(SQ * SQ);
      fms += F / float(SQ * SQ);
    }
  }
  vec3 psi = lum / max(1.0 - fms, vec3(1e-3));
  fragColor = vec4(psi, 1.0);
}`;

export const skyViewFS = /* glsl */ `
precision highp float;
${atmoParsGLSL}
in vec2 vUv;
out vec4 fragColor;
void main() {
  vec2 uv = (gl_FragCoord.xy - 0.5) / vec2(191.0, 107.0);
  float r = Rg + max(uCamAltKm, 0.001);
  float vHorizon = sqrt(max(r * r - Rg * Rg, 0.0));
  float beta = acos(clamp(vHorizon / r, -1.0, 1.0));
  float zha = PI - beta;
  float vz;
  if (uv.y < 0.5) {
    float c = 1.0 - 2.0 * uv.y;
    c = 1.0 - c * c;
    vz = zha * c;
  } else {
    float c = uv.y * 2.0 - 1.0;
    vz = zha + beta * c * c;
  }
  float phi = PI * uv.x * uv.x;
  vec3 dir = vec3(cos(phi) * sin(vz), cos(vz), sin(phi) * sin(vz));
  float sy = uSunDir.y;
  vec3 sun = vec3(sqrt(max(1.0 - sy * sy, 0.0)), sy, 0.0);
  vec3 ro = vec3(0.0, r, 0.0);
  float tG = raySphere(ro, dir, Rg);
  float tT = raySphere(ro, dir, Rt);
  float tMax = tG > 0.0 ? tG : tT;
  float cosT = dot(dir, sun);
  float pR = rayleighPhase(cosT);
  float pM = cornetteShanks(0.8, cosT);
  const int STEPS = 40;
  vec3 T = vec3(1.0), L = vec3(0.0);
  float tPrev = 0.0;
  for (int i = 0; i < STEPS; i++) {
    float f = (float(i) + 0.5) / float(STEPS);
    float t = tMax * f * f;           // denser sampling near the viewer
    float tn = tMax * ((float(i) + 1.0) / float(STEPS)) * ((float(i) + 1.0) / float(STEPS));
    float dt = tn - tPrev; tPrev = tn;
    vec3 p = ro + dir * t;
    float rp = length(p);
    Medium m = sampleMedium(rp - Rg);
    vec3 up = p / rp;
    float smu = dot(up, sun);
    vec3 Ts = sunTransmittance(p, sun);
    vec3 ms = getMultiScat(rp, smu);
    vec3 S = (m.scatR * pR + m.scatM * pM) * Ts + (m.scatR + vec3(m.scatM)) * ms;
    vec3 stepT = exp(-m.ext * dt);
    L += T * (S - S * stepT) / max(m.ext, vec3(1e-7));
    T *= stepT;
  }
  fragColor = vec4(L * uSunE, 1.0);
}`;
