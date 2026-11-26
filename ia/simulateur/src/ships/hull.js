import * as THREE from 'three';

// Lofted ship hull. Local frame: +x forward (bow at +L/2), +y up, waterline at
// y = 0, keel at y = -T. Returns { hull, deck, transom } geometries.

const smooth = (a, b, x) => { const t = Math.min(Math.max((x - a) / (b - a), 0), 1); return t * t * (3 - 2 * t); };

export function buildHull(o) {
  const p = {
    L: 100, B: 16, D: 10, T: 6,
    sheerFwd: 1.5, sheerAft: 0.6,
    bowRake: 4, sternOverhang: 0, transom: 0.85, transomBottom: 0.4,
    parallel: 0.4, midFull: 6, bowFull: 1.3, flare: 0.35, bulwark: 0,
    stemFoot: 0.25, deadrise: 0, camber: 0.25, deckDrop: 0,
    stations: 56, pts: 16, ...o,
  };
  const S = p.stations, P = p.pts;
  const half = p.B / 2;
  const deckEdge = [];
  const pos = [];
  const sectionsPts = [];

  const plan = (u) => {
    // waterline half-breadth factor along the hull
    const aftEnd = 0.5 - p.parallel / 2, fwdStart = 0.5 + p.parallel / 2 - 0.05;
    let w = 1;
    if (u < aftEnd) w = p.transom + (1 - p.transom) * Math.sin((Math.PI / 2) * (u / aftEnd)) ** 0.8;
    if (u > fwdStart) { const t = (u - fwdStart) / (1 - fwdStart); w = Math.pow(Math.max(1 - t * t, 0), 0.62); }
    return w;
  };
  const fullness = (u) => {
    const fwd = smooth(0.55, 0.95, u), aft = 1 - smooth(0.0, 0.3, u);
    return Math.max(1, p.midFull * (1 - fwd) * (1 - aft * 0.4) + p.bowFull * fwd);
  };
  const sheer = (u) => p.sheerFwd * smooth(0.45, 1, u) ** 1.6 + p.sheerAft * (1 - smooth(0, 0.45, u)) ** 2;

  for (let i = 0; i < S; i++) {
    let u = i / (S - 1);
    u = 0.5 - 0.5 * Math.cos(u * Math.PI); // denser at the ends
    u = u * 0.92 + (i / (S - 1)) * 0.08;
    const x = -p.L / 2 + u * p.L;
    const w = plan(u);
    const n = fullness(u);
    const deckY = p.D - p.T + sheer(u) + p.bulwark;
    // keel line rises at the stern (transom) and at the forefoot
    const keelAft = -p.T + (p.T - (-p.transomBottom + p.T) * 0 ) * 0;
    let keelY = -p.T;
    keelY = THREE.MathUtils.lerp(-p.T * p.transomBottom, keelY, smooth(0, 0.14, u));
    keelY = THREE.MathUtils.lerp(keelY, -p.T * p.stemFoot, smooth(0.9, 1.0, u));
    void keelAft;
    const sec = [];
    for (let j = 0; j < P; j++) {
      const v = j / (P - 1);
      const y = keelY + (deckY - keelY) * v;
      // section shape: from V (bow) to box with round bilge (midship)
      const bilgeTop = Math.min(1, (0 - keelY) / (deckY - keelY) * 0.75 + 0.05);
      const vb = Math.min(v / Math.max(bilgeTop, 0.05), 1);
      const round = Math.pow(1 - Math.pow(1 - vb, n), 1 / n);
      const vee = Math.pow(v, 0.85);
      const fw = smooth(0.62, 0.98, u);
      let s = THREE.MathUtils.lerp(round, vee, fw);
      // deadrise for planing hulls
      s = Math.max(s, 0) * (1 - p.deadrise * (1 - vb) * 0.3);
      // flare above the waterline, strongest forward
      const vwl = (0 - keelY) / (deckY - keelY);
      const fl = 1 + p.flare * smooth(0.5, 1, u) * Math.max(0, v - vwl) ** 1.4;
      let hb = half * w * s * fl;
      if (u > 0.995) hb *= 0.15;
      // raked stem / overhangs
      let xx = x;
      xx += p.bowRake * Math.max(0, (y - keelY) / (deckY - keelY + 1e-6)) ** 1.3 * smooth(0.85, 1, u);
      xx -= p.sternOverhang * Math.max(0, (y - keelY) / (deckY - keelY + 1e-6)) * (1 - smooth(0, 0.12, u));
      sec.push([xx, y, hb]);
    }
    sectionsPts.push(sec);
    deckEdge.push(sec[P - 1]);
  }

  // hull skin: port (z<0) side from deck to keel, then starboard keel to deck
  const W = 2 * P - 1;
  for (let i = 0; i < S; i++) {
    const sec = sectionsPts[i];
    for (let j = P - 1; j >= 0; j--) pos.push(sec[j][0], sec[j][1], -sec[j][2]);
    for (let j = 1; j < P; j++) pos.push(sec[j][0], sec[j][1], sec[j][2]);
  }
  const idx = [];
  for (let i = 0; i < S - 1; i++) {
    for (let j = 0; j < W - 1; j++) {
      const a = i * W + j, b = (i + 1) * W + j;
      idx.push(a, b, a + 1, a + 1, b, b + 1);
    }
  }
  const hull = new THREE.BufferGeometry();
  hull.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  hull.setIndex(idx);
  hull.computeVertexNormals();

  // deck (slightly below the bulwark top), with camber
  const dpos = [], didx = [];
  for (let i = 0; i < S; i++) {
    const [x, y, hb] = deckEdge[i];
    const dy = y - p.bulwark - p.deckDrop;
    const inset = p.bulwark > 0 ? Math.min(0.25, hb * 0.1) : 0;
    const k = 5;
    for (let c = 0; c <= k; c++) {
      const z = -hb + inset + ((2 * (hb - inset)) * c) / k;
      const cam = p.camber * (1 - (z / Math.max(hb, 1e-3)) ** 2) * (hb / half);
      dpos.push(x, dy + cam, z);
    }
  }
  for (let i = 0; i < S - 1; i++) for (let c = 0; c < 5; c++) {
    const a = i * 6 + c, b = (i + 1) * 6 + c;
    didx.push(a, a + 1, b, a + 1, b + 1, b);
  }
  const deck = new THREE.BufferGeometry();
  deck.setAttribute('position', new THREE.Float32BufferAttribute(dpos, 3));
  deck.setIndex(didx);
  deck.computeVertexNormals();

  // transom (flat stern face)
  const sec0 = sectionsPts[0];
  const tpos = [], tidx = [];
  const cy = sec0.reduce((s, q) => s + q[1], 0) / P;
  tpos.push(sec0[0][0], cy, 0);
  for (let j = 0; j < P; j++) tpos.push(sec0[j][0], sec0[j][1], sec0[j][2]);
  for (let j = 0; j < P; j++) tpos.push(sec0[j][0], sec0[j][1], -sec0[j][2]);
  for (let j = 0; j < P - 1; j++) {
    tidx.push(0, 1 + j + 1, 1 + j);
    tidx.push(0, 1 + P + j, 1 + P + j + 1);
  }
  // top cap of transom
  const transom = new THREE.BufferGeometry();
  transom.setAttribute('position', new THREE.Float32BufferAttribute(tpos, 3));
  transom.setIndex(tidx);
  transom.computeVertexNormals();

  return { hull, deck, transom, deckEdge, params: p };
}

/** deck height (local y) at a given local x, from the deck edge list */
export function deckHeightAt(hullData, x) {
  const e = hullData.deckEdge;
  for (let i = 0; i < e.length - 1; i++) {
    if (x >= e[i][0] && x <= e[i + 1][0]) {
      const t = (x - e[i][0]) / (e[i + 1][0] - e[i][0] + 1e-9);
      return e[i][1] + (e[i + 1][1] - e[i][1]) * t - hullData.params.bulwark;
    }
  }
  return e[x < e[0][0] ? 0 : e.length - 1][1] - hullData.params.bulwark;
}

/** half beam at a local x (deck level) */
export function halfBeamAt(hullData, x) {
  const e = hullData.deckEdge;
  for (let i = 0; i < e.length - 1; i++) {
    if (x >= e[i][0] && x <= e[i + 1][0]) {
      const t = (x - e[i][0]) / (e[i + 1][0] - e[i][0] + 1e-9);
      return e[i][2] + (e[i + 1][2] - e[i][2]) * t;
    }
  }
  return 0;
}
