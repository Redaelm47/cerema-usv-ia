// Directional wave spectrum (JONSWAP wind sea + narrow swell), sampled on the
// FFT grid of each cascade. Follows Tessendorf (2001) and Horvath (2015),
// "Empirical directional wave spectra for computer graphics".

const G = 9.81;

function mulberry32(seed) {
  return function () {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function gaussPair(rand) {
  let u = 0;
  while (u < 1e-12) u = rand();
  const v = rand();
  const r = Math.sqrt(-2 * Math.log(u));
  return [r * Math.cos(2 * Math.PI * v), r * Math.sin(2 * Math.PI * v)];
}

function jonswap(omega, p) {
  if (omega <= 1e-4) return 0;
  const sigma = omega <= p.omegaP ? 0.07 : 0.09;
  const r = Math.exp(-((omega - p.omegaP) ** 2) / (2 * sigma * sigma * p.omegaP * p.omegaP));
  return (p.alpha * G * G) / omega ** 5 * Math.exp(-1.25 * (p.omegaP / omega) ** 4) * p.gamma ** r;
}

// Normalisation of the cos^2s(theta/2) spreading function (fit, Horvath 2015)
function normFactor(s) {
  const s2 = s * s, s3 = s2 * s, s4 = s3 * s;
  if (s < 5) return -0.000564 * s4 + 0.00776 * s3 - 0.044 * s2 + 0.192 * s + 0.163;
  return -4.8e-8 * s4 + 1.07e-5 * s3 - 9.53e-4 * s2 + 5.9e-2 * s + 3.93e-1;
}

function spreading(omega, theta, p) {
  let s;
  if (omega <= p.omegaP) s = 6.97 * (omega / p.omegaP) ** 4.06;
  else s = 9.77 * (omega / p.omegaP) ** (-2.33 - 1.45 * (p.windSpeed * p.omegaP / G - 1.17));
  s += 16 * Math.tanh(p.omegaP / omega) * p.swellShape * p.swellShape;
  s = Math.min(Math.max(s, 0.01), 60);
  const c = Math.abs(Math.cos(theta * 0.5));
  return normFactor(s) * Math.pow(c, 2 * s);
}

function windSeaParams(windSpeed, fetchKm) {
  const U = Math.max(windSpeed, 0.5);
  const F = Math.max(fetchKm, 0.5) * 1000;
  return {
    windSpeed: U,
    alpha: 0.076 * Math.pow((U * U) / (F * G), 0.22),
    omegaP: 22 * Math.pow((G * G) / (U * F), 1 / 3),
    gamma: 3.3,
    swellShape: 0.15,
  };
}

// Swell: a narrow JONSWAP rescaled to a target significant height.
function swellParams(hs, periodS) {
  const omegaP = (2 * Math.PI) / periodS;
  const p = { alpha: 1, omegaP, gamma: 6, windSpeed: 8, swellShape: 1 };
  // integrate shape to scale variance to (Hs/4)^2
  let sum = 0;
  const dw = omegaP / 200;
  for (let w = dw; w < omegaP * 6; w += dw) sum += jonswap(w, p) * dw;
  p.alpha = sum > 0 ? (hs / 4) ** 2 / sum : 0;
  return p;
}

function angleDiff(a, b) {
  let d = a - b;
  while (d > Math.PI) d -= 2 * Math.PI;
  while (d < -Math.PI) d += 2 * Math.PI;
  return d;
}

/**
 * Builds h0 for one cascade: RGBA float texture data with
 * (Re h0(k), Im h0(k), Re conj(h0(-k)), Im conj(h0(-k))).
 * Grid in standard FFT order: index i -> n = i < N/2 ? i : i - N.
 */
export function buildInitialSpectrum(N, L, kLow, kHigh, sea, seed) {
  const rand = mulberry32(seed);
  const wind = windSeaParams(sea.windSpeed, sea.fetchKm);
  const swell = swellParams(sea.swellHeight, sea.swellPeriod);
  const windDir = sea.windDir; // direction waves travel towards (radians, from +x towards +z)
  const swellDir = sea.swellDir;
  const dk = (2 * Math.PI) / L;
  const h0 = new Float32Array(N * N * 2);
  const out = new Float32Array(N * N * 4);
  const shortCut = sea.shortWaveCut ?? 60;

  for (let j = 0; j < N; j++) {
    const nz = j < N / 2 ? j : j - N;
    for (let i = 0; i < N; i++) {
      const nx = i < N / 2 ? i : i - N;
      const idx = j * N + i;
      const [gr, gi] = gaussPair(rand);
      if (i === N / 2 || j === N / 2) { h0[idx * 2] = 0; h0[idx * 2 + 1] = 0; continue; }
      const kx = nx * dk, kz = nz * dk;
      const k = Math.hypot(kx, kz);
      if (k < 1e-6 || k < kLow || k >= kHigh) { h0[idx * 2] = 0; h0[idx * 2 + 1] = 0; continue; }
      const omega = Math.sqrt(G * k);
      const dOmegadk = G / (2 * omega);
      const theta = Math.atan2(kz, kx);
      let S = jonswap(omega, wind) * spreading(omega, angleDiff(theta, windDir), wind);
      if (swell.alpha > 0) {
        // swell: very directional
        const sd = angleDiff(theta, swellDir);
        const spread = Math.pow(Math.max(Math.cos(sd * 0.5), 0), 2 * 24) * normFactor(24);
        S += jonswap(omega, swell) * spread;
      }
      // (omega, theta) -> (kx, kz) Jacobian
      S *= dOmegadk / k;
      // damp very short waves to avoid aliasing / capillary noise
      S *= Math.exp(-(k / shortCut) * (k / shortCut));
      const amp = Math.sqrt(Math.max(S, 0)) * dk * 0.5;
      h0[idx * 2] = gr * amp;
      h0[idx * 2 + 1] = gi * amp;
    }
  }
  for (let j = 0; j < N; j++) {
    for (let i = 0; i < N; i++) {
      const idx = j * N + i;
      const mi = (N - i) % N, mj = (N - j) % N;
      const midx = mj * N + mi;
      out[idx * 4] = h0[idx * 2];
      out[idx * 4 + 1] = h0[idx * 2 + 1];
      out[idx * 4 + 2] = h0[midx * 2];
      out[idx * 4 + 3] = -h0[midx * 2 + 1];
    }
  }
  return out;
}

/** Significant wave height estimate of the wind sea (for UI/physics). */
export function estimateHs(sea) {
  const p = windSeaParams(sea.windSpeed, sea.fetchKm);
  let sum = 0;
  const dw = 0.005;
  for (let w = dw; w < 20; w += dw) sum += jonswap(w, p) * dw;
  return 4 * Math.sqrt(sum + (sea.swellHeight / 4) ** 2);
}

/** Total slope variance per axis not resolved by the cascades (Cox-Munk-ish). */
export function subgridSlopeVariance(windSpeed) {
  return 0.0012 + 0.0011 * windSpeed;
}
