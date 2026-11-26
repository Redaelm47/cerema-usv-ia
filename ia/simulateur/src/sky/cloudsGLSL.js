// Volumetric cumulus layer (Schneider, "The real-time volumetric cloudscapes of
// Horizon Zero Dawn") + thin cirrus sheet. Distances in km, Earth curvature kept.

export const noiseGenFS = /* glsl */ `
precision highp float;
uniform float uSlice;      // normalised z of the layer being written
uniform float uMode;       // 0 = 3D shape/detail noise, 1 = 2D weather map
uniform float uSeed;
in vec2 vUv;
out vec4 fragColor;

vec3 hash33(vec3 p) {
  p = fract(p * vec3(0.1031, 0.1030, 0.0973) + uSeed);
  p += dot(p, p.yxz + 33.33);
  return fract((p.xxy + p.yxx) * p.zyx);
}
float worley(vec3 p, float period) {
  vec3 id = floor(p), f = fract(p);
  float md = 1.0;
  for (int x = -1; x <= 1; x++)
  for (int y = -1; y <= 1; y++)
  for (int z = -1; z <= 1; z++) {
    vec3 o = vec3(x, y, z);
    vec3 h = hash33(mod(id + o, period));
    vec3 d = o + h - f;
    md = min(md, dot(d, d));
  }
  return sqrt(md);
}
float gnoise(vec3 p, float period) {
  vec3 i = floor(p), f = fract(p);
  vec3 u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
  float n = 0.0;
  float v[8];
  for (int c = 0; c < 8; c++) {
    vec3 o = vec3(float(c & 1), float((c >> 1) & 1), float((c >> 2) & 1));
    vec3 g = hash33(mod(i + o, period)) * 2.0 - 1.0;
    v[c] = dot(normalize(g + 1e-4), f - o);
  }
  float x00 = mix(v[0], v[1], u.x), x10 = mix(v[2], v[3], u.x);
  float x01 = mix(v[4], v[5], u.x), x11 = mix(v[6], v[7], u.x);
  return mix(mix(x00, x10, u.y), mix(x01, x11, u.y), u.z);
}
float perlinFbm(vec3 p, float period, int oct) {
  float a = 0.5, s = 0.0, n = 0.0;
  for (int i = 0; i < 8; i++) {
    if (i >= oct) break;
    s += a * gnoise(p, period);
    n += a; a *= 0.5; p *= 2.0; period *= 2.0;
  }
  return s / n;
}
float worleyFbm(vec3 p, float period) {
  return (1.0 - worley(p, period)) * 0.625 + (1.0 - worley(p * 2.0, period * 2.0)) * 0.25 + (1.0 - worley(p * 4.0, period * 4.0)) * 0.125;
}
float remap(float v, float a, float b, float c, float d) { return c + (v - a) / (b - a) * (d - c); }

void main() {
  if (uMode < 0.5) {
    vec3 p = vec3(vUv, uSlice);
    float pf = perlinFbm(p * 4.0, 4.0, 6) * 0.5 + 0.5;
    pf = clamp(abs(pf * 2.0 - 1.0) * -1.0 + 1.0, 0.0, 1.0) * 0.35 + pf * 0.65; // billowy
    float w1 = worleyFbm(p * 4.0, 4.0);
    float pw = clamp(remap(pf, w1 - 1.0, 1.0, 0.0, 1.0), 0.0, 1.0);
    float g = worleyFbm(p * 6.0, 6.0);
    float b = worleyFbm(p * 12.0, 12.0);
    float a = worleyFbm(p * 24.0, 24.0);
    fragColor = vec4(pw, g, b, a);
  } else {
    vec3 p = vec3(vUv, 0.37);
    float cov = clamp(perlinFbm(p * vec3(5.0, 5.0, 1.0), 5.0, 6) * 2.4 + 0.5, 0.0, 1.0);
    float cells = worleyFbm(p * vec3(11.0, 11.0, 1.0), 11.0);
    float c = clamp(cov * 0.7 + (cells - 0.45) * 0.9, 0.0, 1.0);
    float typ = clamp(perlinFbm(p * vec3(3.0, 3.0, 1.0) + 7.3, 3.0, 4) * 2.6 + 0.5, 0.0, 1.0);
    float cirrus = clamp(perlinFbm(p * vec3(6.0, 6.0, 1.0) + 2.1, 6.0, 6) * 2.4 + 0.5, 0.0, 1.0);
    fragColor = vec4(c, typ, cirrus, 1.0);
  }
}`;

export const cloudParsGLSL = /* glsl */ `
uniform highp sampler3D uCloudNoise;
uniform sampler2D uWeather;
uniform float uCoverage;      // 0..1
uniform float uCloudBottom;   // km
uniform float uCloudTop;      // km
uniform float uCloudDensity;  // extinction scale (1/km)
uniform vec2 uWindOffset;     // km
uniform float uCirrus;        // 0..1
uniform float uCloudTime;
uniform vec2 uCamXZ;         // camera position (km) so clouds stay fixed in the world

float cRemap(float v, float a, float b, float c, float d) { return c + (v - a) / (b - a) * (d - c); }

// p: km, world frame with origin at sea level below the camera (x east, y up, z south)
float cloudAltitude(vec3 p) { return length(p + vec3(0.0, Rg, 0.0)) - Rg; }

float cloudDensity(vec3 p, float alt, bool detail) {
  float hf = (alt - uCloudBottom) / (uCloudTop - uCloudBottom);
  if (hf <= 0.0 || hf >= 1.0) return 0.0;
  vec2 wp = p.xz + uCamXZ + uWindOffset;
  vec4 w = textureLod(uWeather, wp / 30.0, 0.0);
  vec4 w2 = textureLod(uWeather, wp / 9.0 + 0.37, 0.0);
  float covRaw = w.r * 0.65 + w2.r * 0.35;
  float cov = clamp(cRemap(covRaw, 1.0 - uCoverage * 1.05, 1.0, 0.0, 1.0), 0.0, 1.0);
  cov = max(cov, smoothstep(0.75, 1.0, uCoverage) * 0.6);
  if (cov <= 0.01) return 0.0;
  // cumulus profile: flat base, rounded towers whose height varies per cell
  float topH = mix(0.25, 1.0, clamp(w.g * 0.7 + w2.g * 0.6 - 0.15, 0.0, 1.0));
  float hp = smoothstep(0.0, 0.05, hf) * smoothstep(topH, topH * 0.3, hf);
  vec3 q = p + vec3(uWindOffset.x + uCamXZ.x, 0.0, uWindOffset.y + uCamXZ.y);
  vec4 n = textureLod(uCloudNoise, q / 2.6 + vec3(0.0, uCloudTime * 0.0012, 0.0), 0.0);
  float wf = n.g * 0.625 + n.b * 0.25 + n.a * 0.125;
  float base = cRemap(n.r, wf - 1.0, 1.0, 0.0, 1.0);
  base = clamp(cRemap(base * hp, 1.0 - cov, 1.0, 0.0, 1.0), 0.0, 1.0) * cov * mix(0.6, 1.3, hf);
  if (base <= 0.0) return 0.0;
  if (detail) {
    vec4 d = textureLod(uCloudNoise, q / 0.7 + vec3(uCloudTime * 0.004, uCloudTime * 0.003, 0.0), 0.0);
    float df = d.g * 0.625 + d.b * 0.25 + d.a * 0.125;
    // wispy at the base, billowy towards the top
    float dm = mix(df, 1.0 - df, clamp(hf * 3.0, 0.0, 1.0));
    base = clamp(cRemap(base, dm * 0.55, 1.0, 0.0, 1.0), 0.0, 1.0);
  }
  return base;
}

vec2 slabIntersect(vec3 ro, vec3 rd) {
  // ro is relative to sea level point below camera; spheres centred at (0,-Rg,0)
  vec3 o = ro + vec3(0.0, Rg, 0.0);
  float tb = raySphere(o, rd, Rg + uCloudBottom);
  float tt = raySphere(o, rd, Rg + uCloudTop);
  float alt = length(o) - Rg;
  if (alt < uCloudBottom) {
    if (raySphere(o, rd, Rg) > 0.0) return vec2(-1.0);
    return vec2(tb, tt);
  } else if (alt < uCloudTop) {
    float tg = raySphere(o, rd, Rg + uCloudBottom);
    return vec2(0.0, tg > 0.0 ? tg : tt);
  }
  return vec2(-1.0);
}

float hgDual(float c) {
  return mix(hgPhase(0.75, c), hgPhase(-0.25, c), 0.25) ;
}

// Returns premultiplied radiance (rgb) and transmittance (a) of the cloud layer.
vec4 marchClouds(vec3 ro, vec3 rd, int steps, int lightSteps, float jitter, float maxDist) {
  vec2 seg = slabIntersect(ro, rd);
  if (seg.x < 0.0 || seg.y <= seg.x) return vec4(0.0, 0.0, 0.0, 1.0);
  float t0 = seg.x, t1 = min(seg.y, maxDist);
  if (t1 <= t0) return vec4(0.0, 0.0, 0.0, 1.0);
  float segLen = t1 - t0;
  float stepsF = float(steps) * mix(0.6, 1.8, smoothstep(1.5, 25.0, segLen));
  float dt = segLen / stepsF;
  float cosT = dot(rd, uSunDir);
  float ph = hgDual(cosT);
  vec3 sunE = uSunE;
  vec3 skyUp = skyRadiance(vec3(0.0, 1.0, 0.0)) * PI;
  vec3 skyHz = horizonRadiance(rd) * PI;
  vec3 L = vec3(0.0);
  float T = 1.0;
  float tSum = 0.0, wSum = 0.0;
  float sigma = uCloudDensity;
  float t = t0 + dt * jitter;
  bool inCloud = false;
  int empty = 0;
  float noBack = t0;
  for (int i = 0; i < 160; i++) {
    if (t > t1 || T < 0.015) break;
    vec3 p = ro + rd * t;
    float alt = cloudAltitude(p);
    if (!inCloud) {
      // cheap coarse search for the next cloud
      if (cloudDensity(p, alt, false) > 0.0) { inCloud = true; t = max(noBack, t - dt * 2.0); empty = 0; continue; }
      t += dt * 3.0;
      continue;
    }
    float d = cloudDensity(p, alt, true);
    if (d > 0.002) {
      empty = 0;
      // light march towards the sun (cone-ish, growing steps)
      float od = 0.0;
      float ls = 0.07;
      vec3 lp = p;
      for (int j = 0; j < 8; j++) {
        if (j >= lightSteps) break;
        lp += uSunDir * ls;
        float la = cloudAltitude(lp);
        od += cloudDensity(lp, la, j < 1) * ls;
        ls *= 2.0;
      }
      od *= sigma * 0.3; // light paths: in-scattering keeps cloud interiors bright
      vec3 Tsun = sunTransmittance((p + vec3(0.0, Rg, 0.0)), uSunDir);
      // multiple scattering approximation (Wrenninge)
      float ms = 0.0;
      float a = 1.0, b = 1.0, c = 1.0;
      for (int o = 0; o < 4; o++) {
        ms += a * exp(-b * od) * mix(hgDual(cosT * c), 1.0 / (4.0 * PI), 1.0 - c);
        a *= 0.55; b *= 0.45; c *= 0.6;
      }
      float powder = 1.0 - exp(-d * sigma * 0.18);
      powder = mix(1.0, powder, 0.55);
      float hf = clamp((alt - uCloudBottom) / (uCloudTop - uCloudBottom), 0.0, 1.0);
      vec3 amb = mix(skyHz * 0.35, skyUp * 0.9, hf) * (0.55 + 0.45 * hf);
      vec3 S = sunE * Tsun * ms * powder * 1.15 + amb / (4.0 * PI) * 1.6;
      float ext = d * sigma;
      float stepT = exp(-ext * dt);
      L += T * S * (1.0 - stepT);
      tSum += t * T * (1.0 - stepT); wSum += T * (1.0 - stepT);
      T *= stepT;
    } else if (++empty > 5) {
      inCloud = false;
      noBack = t + dt;
    }
    t += dt;
  }
  // aerial perspective between viewer and cloud
  float dMean = wSum > 0.0 ? tSum / wSum : t0;
  vec3 pm = ro + rd * dMean + vec3(0.0, Rg, 0.0);
  vec3 o = ro + vec3(0.0, Rg, 0.0);
  float mu0 = dot(normalize(o), rd);
  vec3 Tall = getTransmittance(length(o), mu0);
  vec3 Tbeyond = getTransmittance(length(pm), dot(normalize(pm), rd));
  vec3 Tair = clamp(Tall / max(Tbeyond, vec3(1e-4)), 0.0, 1.0);
  vec3 sky = skyRadiance(rd);
  vec3 frac = clamp((1.0 - Tair) / max(1.0 - Tall, vec3(1e-3)), 0.0, 1.0);
  float cover = 1.0 - T;
  L = L * Tair + sky * frac * cover;
  return vec4(L, T);
}

// Thin cirrus sheet at ~8 km (cheap 2D layer)
vec4 cirrusLayer(vec3 rd) {
  if (uCirrus <= 0.001 || rd.y <= 0.0) return vec4(0.0, 0.0, 0.0, 1.0);
  vec3 o = vec3(0.0, Rg, 0.0);
  float t = raySphere(o, rd, Rg + 8.0);
  vec3 p = rd * t;
  vec2 uv = (p.xz + uCamXZ + uWindOffset * 2.0) / vec2(160.0, 38.0);
  vec4 w = textureLod(uWeather, uv, 1.0);
  vec4 w2 = textureLod(uWeather, uv * 3.7 + 0.31, 1.0);
  float c = clamp((w.b * 0.7 + w2.b * 0.3) - (1.0 - uCirrus * 0.75), 0.0, 1.0) * 2.2;
  c *= smoothstep(0.0, 0.12, rd.y);
  float a = clamp(c, 0.0, 0.85);
  float cosT = dot(rd, uSunDir);
  vec3 Ts = getTransmittance(Rg + 8.0, max(uSunDir.y, -0.1));
  vec3 L = uSunE * Ts * (hgPhase(0.6, cosT) * 0.9 + 0.08) * 0.35 + skyRadiance(vec3(0.0, 1.0, 0.0)) * 0.6;
  vec3 sky = skyRadiance(rd);
  // haze between viewer and cirrus
  float fade = smoothstep(0.0, 0.25, rd.y);
  L = mix(sky, L, fade);
  return vec4(L * a, 1.0 - a);
}

uniform sampler2D uCloudShadowMap;
uniform vec3 uCloudShadowRect;
float cloudShadowAt(vec3 worldPos) {
  vec2 uv = (worldPos.xz - uCloudShadowRect.xy) / uCloudShadowRect.z;
  if (any(lessThan(uv, vec2(0.0))) || any(greaterThan(uv, vec2(1.0)))) return 1.0;
  return texture(uCloudShadowMap, uv).r;
}

// Shadow of the cumulus layer on a point at sea/ground level (world metres)
float cloudShadow(vec3 worldPos, vec3 camPos) {
  vec3 p = vec3(worldPos.x - camPos.x, 0.0, worldPos.z - camPos.z) * 0.001;
  vec3 sd = normalize(uSunDir + vec3(0.0, 0.03, 0.0));
  float od = 0.0;
  for (int i = 0; i < 3; i++) {
    float h = mix(uCloudBottom, uCloudTop, (float(i) + 0.5) / 3.0 * 0.6 + 0.05);
    vec3 q = p + sd * (h / max(sd.y, 0.05));
    q.y = h;
    od += cloudDensity(q, h, false);
  }
  return exp(-od * uCloudDensity * (uCloudTop - uCloudBottom) * 0.2);
}
`;
