import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { buildHull, deckHeightAt, halfBeamAt } from './hull.js';
import { makeShipMaterial, PAINT, patchExternalMaterial } from './shipMaterial.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

// Procedural vessels of the Rade de Brest: feeder container ship, bulk carrier,
// navy frigate, Breton trawler, island ferry, tug, sailing yachts, motorboats.
// Local frame: +x bow, +y up, waterline y = 0.

const rnd = (a, b) => a + Math.random() * (b - a);
const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];

class Builder {
  constructor() { this.parts = new Map(); this.extra = []; }
  add(mat, geo, x = 0, y = 0, z = 0, rx = 0, ry = 0, rz = 0) {
    let g = geo.index ? geo.toNonIndexed() : geo.clone();
    g.deleteAttribute('uv');
    for (const k of Object.keys(g.attributes)) if (k !== 'position' && k !== 'normal') g.deleteAttribute(k);
    if (!g.attributes.normal) g.computeVertexNormals();
    const m = new THREE.Matrix4().compose(new THREE.Vector3(x, y, z), new THREE.Quaternion().setFromEuler(new THREE.Euler(rx, ry, rz)), new THREE.Vector3(1, 1, 1));
    g.applyMatrix4(m);
    if (!this.parts.has(mat)) this.parts.set(mat, []);
    this.parts.get(mat).push(g);
    return g;
  }
  box(mat, w, h, d, x, y, z, ry = 0) { return this.add(mat, new THREE.BoxGeometry(w, h, d), x, y + h / 2, z, 0, ry, 0); }
  // box whose top is narrower (stealth / tapered superstructures)
  taper(mat, w, h, d, x, y, z, tx = 0.8, tz = 0.8) {
    const g = new THREE.BoxGeometry(w, h, d);
    const p = g.attributes.position;
    for (let i = 0; i < p.count; i++) if (p.getY(i) > 0) { p.setX(i, p.getX(i) * tx); p.setZ(i, p.getZ(i) * tz); }
    g.computeVertexNormals();
    return this.add(mat, g, x, y + h / 2, z);
  }
  cyl(mat, r0, r1, h, x, y, z, rx = 0, rz = 0, seg = 14) {
    return this.add(mat, new THREE.CylinderGeometry(r0, r1, h, seg), x, y, z, rx, 0, rz);
  }
  rod(mat, a, b, r = 0.08, seg = 6) {
    const va = new THREE.Vector3(...a), vb = new THREE.Vector3(...b);
    const len = va.distanceTo(vb);
    const g = new THREE.CylinderGeometry(r, r, len, seg);
    const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), vb.clone().sub(va).normalize());
    const m = new THREE.Matrix4().compose(va.clone().add(vb).multiplyScalar(0.5), q, new THREE.Vector3(1, 1, 1));
    const gg = g.toNonIndexed(); gg.deleteAttribute('uv'); gg.applyMatrix4(m);
    if (!this.parts.has(mat)) this.parts.set(mat, []);
    this.parts.get(mat).push(gg);
  }
  build() {
    const group = new THREE.Group();
    for (const [mat, geos] of this.parts) {
      const g = mergeGeometries(geos, false);
      g.computeBoundingSphere();
      const mesh = new THREE.Mesh(g, mat);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      group.add(mesh);
    }
    for (const e of this.extra) group.add(e);
    return group;
  }
}

function addHull(b, hd, mats) {
  b.add(mats.hull, hd.hull);
  b.add(mats.deck, hd.deck);
  b.add(mats.hull, hd.transom);
}

function nameDecal(text, { height = 1.2, color = '#f2f2ee', font = '600 120px "Helvetica Neue", Arial, sans-serif', outline = null } = {}) {
  const c = document.createElement('canvas');
  const ctx = c.getContext('2d');
  ctx.font = font;
  const w = Math.ceil(ctx.measureText(text).width) + 40;
  c.width = w; c.height = 160;
  ctx.font = font;
  ctx.textBaseline = 'middle';
  if (outline) { ctx.strokeStyle = outline; ctx.lineWidth = 10; ctx.strokeText(text, 20, 84); }
  ctx.fillStyle = color;
  ctx.fillText(text, 20, 84);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  const mat = makeShipMaterial({ color: 0xffffff, map: tex, roughness: 0.55, transparent: true, mode: PAINT.PLAIN, grime: 0.2 });
  mat.polygonOffset = true; mat.polygonOffsetFactor = -2; mat.depthWrite = false;
  const geo = new THREE.PlaneGeometry((height * w) / 160, height);
  return new THREE.Mesh(geo, mat);
}

function placeOnSide(mesh, hd, x, y, side) {
  const hb = halfBeamAt(hd, x) * 0.985 + 0.04;
  const m = mesh.clone();
  m.position.set(x, y, side * hb);
  m.rotation.y = side > 0 ? 0 : Math.PI;
  // follow the local hull angle in plan
  const hb2 = halfBeamAt(hd, x + 1) * 0.985;
  const ang = Math.atan2(hb2 - hb + 0.04, 1);
  m.rotation.y += side > 0 ? -ang : ang;
  return m;
}

function navLights(group, L, B, mastH, deckY) {
  const mk = (c, r) => new THREE.Mesh(new THREE.SphereGeometry(r, 8, 6), new THREE.MeshBasicMaterial({ color: new THREE.Color(c).multiplyScalar(60) }));
  const lights = new THREE.Group();
  const s = Math.max(0.12, L * 0.0025);
  const red = mk(0xff2010, s), green = mk(0x10ff40, s), w1 = mk(0xfff4dd, s), w2 = mk(0xfff4dd, s);
  red.position.set(L * 0.2, deckY + 1.5, -B / 2);
  green.position.set(L * 0.2, deckY + 1.5, B / 2);
  w1.position.set(L * 0.05, mastH, 0);
  w2.position.set(-L / 2 + 0.3, deckY + 1, 0);
  lights.add(red, green, w1, w2);
  lights.visible = false;
  group.add(lights);
  return lights;
}

const CONTAINER_COLORS = [0x1f4e8c, 0x1f4e8c, 0x0e3a63, 0xc8b400, 0xe1a800, 0x7a1d1a, 0xb33b24, 0x2f6b3a, 0x5f6b72, 0x8b8f92, 0xd9d6cf, 0xe06c1a, 0x24323f, 0x6a3a8e, 0x0d6f73, 0xa62c2c];

// ---------------------------------------------------------------------------

function containerShip() {
  const L = rnd(135, 175), B = L * 0.155, T = rnd(7, 8.8), D = T + rnd(4.5, 6);
  const hullCol = pick([0x1b2a44, 0x16202b, 0x6b1d1b, 0x23462f, 0x1d3f6e, 0x2a2d31]);
  const mats = {
    hull: makeShipMaterial({ color: hullCol, colorB: pick([0x7a201c, 0x60191a, 0x2a2a2a]), mode: PAINT.HULL, rust: rnd(0.25, 0.7), roughness: 0.55, bootTop: 0.3, side: THREE.DoubleSide }),
    deck: makeShipMaterial({ color: pick([0x5e2a22, 0x3f4d3a, 0x6b6e70]), mode: PAINT.DECK, roughness: 0.8, rust: 0.6 }),
    house: makeShipMaterial({ color: 0xe9e8e2, mode: PAINT.HOUSE, roughness: 0.55, levelH: 2.8, bridgeLevel: 5, grime: 0.55 }),
    metal: makeShipMaterial({ color: 0x9a9c9c, mode: PAINT.METAL, roughness: 0.5, metalness: 0.3 }),
    dark: makeShipMaterial({ color: 0x141414, roughness: 0.7 }),
    funnel: makeShipMaterial({ color: pick([0x1f4e8c, 0xd8d6cf, 0xc0392b, 0x1a1a1a]), roughness: 0.5, mode: PAINT.METAL }),
    cont: makeShipMaterial({ color: 0xffffff, mode: PAINT.CONTAINER, roughness: 0.65, metalness: 0.2, rust: 0.4 }),
    accent: makeShipMaterial({ color: 0xe8661c, roughness: 0.5 }),
  };
  const hd = buildHull({ L, B, D, T, sheerFwd: 2.5, sheerAft: 0.3, bowRake: 6, transom: 0.78, transomBottom: 0.35, parallel: 0.55, midFull: 7, flare: 0.5, camber: 0.3 });
  const b = new Builder();
  addHull(b, hd, mats);
  const deckAt = (x) => deckHeightAt(hd, x);
  // forecastle
  const fx = L / 2 - 14;
  b.box(mats.deck, 16, 2.6, B * 0.72, fx + 4, deckAt(fx) - 0.2, 0);
  b.cyl(mats.metal, 0.35, 0.45, 14, fx + 5, deckAt(fx) + 9, 0);
  b.box(mats.metal, 0.4, 0.4, 5, fx + 5, deckAt(fx) + 12, 0);
  // accommodation aft
  const ax = -L / 2 + 20;
  const ay = deckAt(ax);
  for (const m of [mats.house]) m.userData.paint.uDeckBase.value = ay;
  const levels = 5;
  b.box(mats.house, 14, 2.8 * levels, B * 0.72, ax, ay, 0);
  b.box(mats.house, 10, 2.8, B, ax + 1.5, ay + 2.8 * levels, 0); // bridge with wings
  b.box(mats.dark, 10.4, 0.25, B + 0.4, ax + 1.5, ay + 2.8 * (levels + 1), 0);
  b.cyl(mats.metal, 0.18, 0.25, 7, ax - 1, ay + 2.8 * (levels + 1) + 3.5, 0);
  b.box(mats.metal, 2.2, 0.15, 0.4, ax - 1, ay + 2.8 * (levels + 1) + 4.5, 0);
  // funnel
  b.taper(mats.funnel, 6, 7, 5, ax - 10, ay + 2, 0, 0.9, 0.85);
  b.box(mats.dark, 5.5, 1.4, 4.4, ax - 10, ay + 9, 0);
  // lifeboat
  b.add(mats.accent, new THREE.CapsuleGeometry(1.3, 5, 4, 10), ax - 7.5, ay + 6, B * 0.4, 0, 0, Math.PI / 2);
  // hatch covers + containers
  const inst = [];
  const x0 = ax + 9, x1 = fx - 4;
  const rows = Math.floor((B - 1.2) / 2.5);
  for (let x = x0; x < x1 - 12.5; x += 13.4) {
    const dy = deckAt(x + 6.5);
    b.box(mats.metal, 12.9, 1.1, B - 1.6, x + 6.5, dy, 0);
    const tiers = Math.floor(rnd(2, 6.9));
    for (let r = 0; r < rows; r++) {
      const z = -((rows - 1) * 2.5) / 2 + r * 2.5;
      const h = Math.max(0, tiers - (Math.random() < 0.25 ? Math.floor(rnd(1, 3)) : 0));
      for (let t = 0; t < h; t++) inst.push({ x: x + 6.5, y: dy + 1.1 + t * 2.6 + 1.3, z, c: pick(CONTAINER_COLORS) });
    }
  }
  const group = b.build();
  const cg = new THREE.BoxGeometry(12.19, 2.59, 2.44);
  const im = new THREE.InstancedMesh(cg, mats.cont, inst.length);
  const m4 = new THREE.Matrix4();
  inst.forEach((c, i) => {
    m4.makeTranslation(c.x, c.y, c.z);
    im.setMatrixAt(i, m4);
    im.setColorAt(i, new THREE.Color(c.c).multiplyScalar(rnd(0.75, 1.05)));
  });
  im.castShadow = im.receiveShadow = true;
  group.add(im);
  const name = pick(['IROISE TRADER', 'ATLANTIC FEEDER', 'CELTIC STAR', 'NORDIC BAY', 'ARMOR EXPRESS', 'MARIA SCHULTE']);
  const decal = nameDecal(name, { height: 1.4 });
  group.add(placeOnSide(decal, hd, L / 2 - 16, deckAt(L / 2 - 16) - 2.2, 1));
  group.add(placeOnSide(decal, hd, L / 2 - 16, deckAt(L / 2 - 16) - 2.2, -1));
  const lights = navLights(group, L, B, ay + 2.8 * (levels + 1) + 7, deckAt(0));
  return { group, L, B, T, type: 'cargo', label: 'Porte-conteneurs', name, cruise: rnd(5.5, 7.5), lights, air: ay + 2.8 * (levels + 1) + 7 };
}

function bulkCarrier() {
  const L = rnd(160, 190), B = L * 0.16, T = rnd(8, 10), D = T + rnd(5, 7);
  const mats = {
    hull: makeShipMaterial({ color: pick([0x1a1a1c, 0x232a35, 0x4d1515, 0x15303f]), colorB: 0x7d231d, mode: PAINT.HULL, rust: rnd(0.4, 0.85), roughness: 0.6, bootTop: rnd(0.5, 2.5), side: THREE.DoubleSide }),
    deck: makeShipMaterial({ color: 0x4c5a3d, mode: PAINT.DECK, roughness: 0.85, rust: 0.8 }),
    house: makeShipMaterial({ color: 0xe6e3da, mode: PAINT.HOUSE, roughness: 0.6, levelH: 2.8, bridgeLevel: 5, grime: 0.7 }),
    metal: makeShipMaterial({ color: pick([0xb9a24a, 0x7d8a6a, 0x9b9b95]), mode: PAINT.METAL, roughness: 0.55, metalness: 0.2, grime: 0.6 }),
    crane: makeShipMaterial({ color: pick([0xd4a017, 0xe2e0d8, 0x2c6e3f]), mode: PAINT.METAL, roughness: 0.5, grime: 0.6 }),
    dark: makeShipMaterial({ color: 0x151515, roughness: 0.7 }),
    accent: makeShipMaterial({ color: 0xe8661c, roughness: 0.5 }),
  };
  const hd = buildHull({ L, B, D, T, sheerFwd: 2.4, sheerAft: 0.4, bowRake: 5, transom: 0.8, transomBottom: 0.35, parallel: 0.6, midFull: 8, flare: 0.4 });
  const b = new Builder();
  addHull(b, hd, mats);
  const deckAt = (x) => deckHeightAt(hd, x);
  const ax = -L / 2 + 18, ay = deckAt(ax);
  mats.house.userData.paint.uDeckBase.value = ay;
  b.box(mats.house, 15, 2.8 * 5, B * 0.75, ax, ay, 0);
  b.box(mats.house, 10, 2.8, B, ax + 2, ay + 14, 0);
  b.box(mats.dark, 10.4, 0.25, B + 0.4, ax + 2, ay + 16.8, 0);
  b.taper(mats.house, 6, 7, 5, ax - 9, ay + 3, 0, 0.92, 0.88);
  b.box(mats.dark, 5.6, 1.6, 4.5, ax - 9, ay + 9.4, 0);
  b.cyl(mats.metal, 0.2, 0.3, 8, ax, ay + 21, 0);
  b.add(mats.accent, new THREE.CapsuleGeometry(1.3, 5, 4, 10), ax - 7.5, ay + 6, B * 0.42, 0, 0, Math.PI / 2);
  const fx = L / 2 - 12;
  b.box(mats.deck, 14, 2.5, B * 0.7, fx + 3, deckAt(fx) - 0.2, 0);
  b.cyl(mats.metal, 0.3, 0.4, 12, fx, deckAt(fx) + 8, 0);
  const nH = 5, x0 = ax + 12, span = fx - 6 - x0, hl = span / nH;
  for (let i = 0; i < nH; i++) {
    const x = x0 + hl * (i + 0.5);
    const dy = deckAt(x);
    b.taper(mats.metal, hl * 0.72, 1.6, B * 0.62, x, dy, 0, 0.98, 0.9);
    if (i < nH - 1) {
      const cx = x + hl / 2;
      b.cyl(mats.crane, 1.2, 1.4, 9, cx, dy + 4.5, 0);
      b.box(mats.crane, 3, 3, 3, cx, dy + 9, 0);
      const ang = rnd(-0.6, 0.6), elev = rnd(0.35, 0.75);
      const len = 24;
      const tip = [cx + Math.cos(ang) * Math.cos(elev) * len, dy + 11 + Math.sin(elev) * len, Math.sin(ang) * Math.cos(elev) * len];
      b.rod(mats.crane, [cx, dy + 10.5, 0], tip, 0.5, 8);
      b.rod(mats.dark, tip, [tip[0], tip[1] - 6, tip[2]], 0.05, 4);
    }
  }
  const group = b.build();
  const name = pick(['GOLDEN BRITTANY', 'STAR OF IROISE', 'BULK ARMORIQUE', 'NAVIOS LUNA', 'CAPE FINISTERRE']);
  const decal = nameDecal(name, { height: 1.5 });
  group.add(placeOnSide(decal, hd, L / 2 - 14, deckAt(L / 2 - 14) - 2.4, 1));
  group.add(placeOnSide(decal, hd, L / 2 - 14, deckAt(L / 2 - 14) - 2.4, -1));
  const lights = navLights(group, L, B, ay + 25, deckAt(0));
  return { group, L, B, T, type: 'cargo', label: 'Vraquier', name, cruise: rnd(5, 6.5), lights, air: ay + 25 };
}

function frigate() {
  const L = 142, B = 19.8, T = 5.2, D = T + 6.5;
  const grey = 0x7a8187;
  const mats = {
    hull: makeShipMaterial({ color: grey, colorB: 0x2a2c2e, mode: PAINT.HULL, rust: 0.12, grime: 0.35, roughness: 0.62, bootTop: 0.4, side: THREE.DoubleSide }),
    deck: makeShipMaterial({ color: 0x4d5257, mode: PAINT.DECK, roughness: 0.85, rust: 0.05 }),
    house: makeShipMaterial({ color: 0x80878d, mode: PAINT.HOUSE, roughness: 0.62, levelH: 3.0, bridgeLevel: 2, winW: 1.0, winSpacing: 1.5, grime: 0.3 }),
    metal: makeShipMaterial({ color: 0x8b9196, mode: PAINT.METAL, roughness: 0.55, grime: 0.3 }),
    dark: makeShipMaterial({ color: 0x24272a, roughness: 0.6 }),
  };
  const hd = buildHull({ L, B, D, T, sheerFwd: 2.8, sheerAft: 0.0, bowRake: 7, transom: 0.9, transomBottom: 0.05, parallel: 0.25, midFull: 3, bowFull: 1.15, flare: 0.75, camber: 0.2, stemFoot: 0.6 });
  const b = new Builder();
  addHull(b, hd, mats);
  const deckAt = (x) => deckHeightAt(hd, x);
  const y0 = deckAt(0);
  mats.house.userData.paint.uDeckBase.value = y0;
  // long stealth superstructure with sloped walls
  b.taper(mats.house, 70, 6, B * 0.86, -8, y0, 0, 0.97, 0.82);
  b.taper(mats.house, 16, 6, B * 0.7, 18, y0 + 0, 0, 0.9, 0.78);
  b.taper(mats.house, 12, 3.0, B * 0.66, 18, y0 + 6, 0, 0.85, 0.85); // bridge level
  // integrated mast (pyramidal tower with radar faces)
  b.taper(mats.house, 9, 18, 8, 8, y0 + 6, 0, 0.45, 0.45);
  b.box(mats.dark, 3.2, 3.2, 3.2, 8, y0 + 24, 0);
  b.cyl(mats.metal, 0.15, 0.25, 6, 8, y0 + 29, 0);
  // funnel / exhausts
  b.taper(mats.house, 10, 5, 7, -18, y0 + 6, 0, 0.7, 0.7);
  b.box(mats.dark, 4, 0.8, 4, -18, y0 + 11, 0);
  // hangar + helideck
  b.taper(mats.house, 16, 6.5, B * 0.78, -44, y0, 0, 0.98, 0.85);
  // gun turret + VLS
  b.taper(mats.metal, 4.5, 2.2, 4.2, 42, deckAt(42), 0, 0.7, 0.7);
  b.rod(mats.metal, [43.5, deckAt(42) + 1.3, 0], [49.5, deckAt(42) + 2.0, 0], 0.16, 8);
  b.box(mats.dark, 8, 0.4, 7, 30, deckAt(30), 0);
  const group = b.build();
  const num = nameDecal('D 650', { height: 3.2, color: '#f4f4f0', font: '700 120px "Arial Black", Arial, sans-serif', outline: '#202326' });
  group.add(placeOnSide(num, hd, L / 2 - 22, deckAt(L / 2 - 22) - 3.6, 1));
  group.add(placeOnSide(num, hd, L / 2 - 22, deckAt(L / 2 - 22) - 3.6, -1));
  const lights = navLights(group, L, B, y0 + 30, y0);
  return { group, L, B, T, type: 'military', label: 'Frégate', name: 'Frégate D 650', cruise: rnd(6, 8), lights, air: y0 + 31 };
}

function trawler() {
  const L = rnd(18, 26), B = L * 0.31, T = L * 0.12, D = T + L * 0.07;
  const scheme = pick([[0x1b3566, 0xd9d6cc], [0x8a1c14, 0xe6e3da], [0x14523a, 0xe6e3da], [0x253a52, 0xc9a227]]);
  const mats = {
    hull: makeShipMaterial({ color: scheme[0], colorB: 0x7a1e1a, mode: PAINT.HULL, rust: rnd(0.4, 0.9), grime: 0.7, roughness: 0.5, bootTop: 0.25, side: THREE.DoubleSide }),
    deck: makeShipMaterial({ color: 0x6b6f6e, mode: PAINT.DECK, roughness: 0.85, rust: 0.7 }),
    house: makeShipMaterial({ color: scheme[1], mode: PAINT.HOUSE, roughness: 0.5, levelH: 2.3, bridgeLevel: 0, winW: 0.9, winSpacing: 1.15, grime: 0.7 }),
    metal: makeShipMaterial({ color: pick([0xe06a1c, 0x1f5fa0, 0xd8d6cf]), mode: PAINT.METAL, roughness: 0.5, grime: 0.7 }),
    dark: makeShipMaterial({ color: 0x161616, roughness: 0.8 }),
    net: makeShipMaterial({ color: pick([0x2f7a3a, 0x1d4f8a, 0xb83a1c]), roughness: 0.95 }),
  };
  const hd = buildHull({ L, B, D, T, sheerFwd: L * 0.06, sheerAft: 0.3, bowRake: L * 0.06, transom: 0.7, transomBottom: 0.5, parallel: 0.15, midFull: 2.2, bowFull: 1.2, flare: 0.5, bulwark: 1.0, camber: 0.08 });
  const b = new Builder();
  addHull(b, hd, mats);
  const deckAt = (x) => deckHeightAt(hd, x);
  const wx = L * 0.14, wy = deckAt(wx);
  mats.house.userData.paint.uDeckBase.value = wy;
  b.box(mats.house, L * 0.26, 2.3, B * 0.62, wx, wy, 0);
  b.box(mats.house, L * 0.2, 0.15, B * 0.66, wx, wy + 2.3, 0);
  b.cyl(mats.metal, 0.12, 0.15, 6, wx + 0.5, wy + 5.3, 0);
  b.box(mats.dark, 1.8, 0.12, 0.25, wx + 0.5, wy + 4, 0);
  b.box(mats.metal, 0.6, 0.4, 0.6, wx - 1, wy + 2.6, 0.8);
  // gantry (A-frame) aft and net drum
  const gx = -L / 2 + 1.5, gy = deckAt(gx);
  b.rod(mats.metal, [gx, gy, -B * 0.4], [gx + 0.6, gy + 5, -B * 0.25], 0.18);
  b.rod(mats.metal, [gx, gy, B * 0.4], [gx + 0.6, gy + 5, B * 0.25], 0.18);
  b.rod(mats.metal, [gx + 0.6, gy + 5, -B * 0.28], [gx + 0.6, gy + 5, B * 0.28], 0.2);
  b.cyl(mats.net, 1.0, 1.0, B * 0.5, -L * 0.25, gy + 1.4, 0, Math.PI / 2, 0, 16);
  // foremast with derrick
  b.cyl(mats.metal, 0.12, 0.16, 7, L * 0.32, deckAt(L * 0.32) + 3.5, 0);
  b.rod(mats.metal, [L * 0.32, deckAt(L * 0.32) + 1.5, 0], [L * 0.05, deckAt(L * 0.05) + 4.5, 0], 0.08);
  // tyres as fenders
  for (let i = 0; i < 4; i++) {
    const x = -L * 0.25 + i * L * 0.15;
    for (const s of [-1, 1]) b.add(mats.dark, new THREE.TorusGeometry(0.35, 0.14, 6, 10), x, deckAt(x) - 1.0, s * (halfBeamAt(hd, x) + 0.1));
  }
  const group = b.build();
  const reg = pick(['BR', 'GV', 'CC', 'DZ', 'AD']) + ' ' + Math.floor(rnd(100000, 999999));
  const decal = nameDecal(reg, { height: 0.55, color: '#f0f0ea' });
  group.add(placeOnSide(decal, hd, L * 0.33, deckAt(L * 0.33) - 0.9, 1));
  group.add(placeOnSide(decal, hd, L * 0.33, deckAt(L * 0.33) - 0.9, -1));
  const lights = navLights(group, L, B, wy + 8, deckAt(0));
  return { group, L, B, T, type: 'fishing', label: 'Chalutier', name: reg, cruise: rnd(3, 5), lights, air: wy + 8.5 };
}

function ferry() {
  const L = rnd(40, 52), B = L * 0.22, T = 2.6, D = T + 2.6;
  const mats = {
    hull: makeShipMaterial({ color: 0xedece6, colorB: 0x1d2e5c, mode: PAINT.HULL, rust: 0.12, grime: 0.4, roughness: 0.45, bootTop: 0.9, side: THREE.DoubleSide }),
    deck: makeShipMaterial({ color: 0x55616b, mode: PAINT.DECK, roughness: 0.8, rust: 0.1 }),
    house: makeShipMaterial({ color: 0xf0efe9, mode: PAINT.HOUSE, roughness: 0.45, levelH: 2.6, bridgeLevel: 2, winW: 1.5, winSpacing: 2.0, grime: 0.35 }),
    stripe: makeShipMaterial({ color: 0x1d4f9a, roughness: 0.45 }),
    metal: makeShipMaterial({ color: 0xbcc0c2, mode: PAINT.METAL, roughness: 0.4 }),
    dark: makeShipMaterial({ color: 0x1a1a1a, roughness: 0.7 }),
    accent: makeShipMaterial({ color: 0xe8661c, roughness: 0.5 }),
  };
  const hd = buildHull({ L, B, D, T, sheerFwd: 1.4, sheerAft: 0.2, bowRake: 3, transom: 0.85, transomBottom: 0.2, parallel: 0.3, midFull: 3, flare: 0.4 });
  const b = new Builder();
  addHull(b, hd, mats);
  const deckAt = (x) => deckHeightAt(hd, x);
  const y0 = deckAt(0);
  mats.house.userData.paint.uDeckBase.value = y0;
  b.box(mats.house, L * 0.62, 2.6, B * 0.9, -L * 0.04, y0, 0);
  b.box(mats.house, L * 0.42, 2.6, B * 0.82, L * 0.02, y0 + 2.6, 0);
  b.box(mats.house, L * 0.14, 2.6, B * 0.6, L * 0.13, y0 + 5.2, 0);
  b.box(mats.stripe, L * 0.625, 0.4, B * 0.905, -L * 0.04, y0 + 0.1, 0);
  b.taper(mats.stripe, 2.5, 3, 2, -L * 0.18, y0 + 5.2, 0, 0.9, 0.9);
  b.box(mats.dark, 2.3, 0.5, 1.8, -L * 0.18, y0 + 8.2, 0);
  b.cyl(mats.metal, 0.1, 0.12, 4, L * 0.13, y0 + 9.8, 0);
  for (const s of [-1, 1]) b.add(mats.accent, new THREE.CylinderGeometry(0.7, 0.7, 1.6, 12), -L * 0.3, y0 + 3.4, s * B * 0.35);
  const group = b.build();
  const name = pick(['ENEZ EUSSA', 'FROMVEUR II', 'MOLENEZ', 'BRESTOA']);
  const decal = nameDecal(name, { height: 0.9, color: '#1d2e5c' });
  group.add(placeOnSide(decal, hd, L * 0.3, deckAt(L * 0.3) - 1.2, 1));
  group.add(placeOnSide(decal, hd, L * 0.3, deckAt(L * 0.3) - 1.2, -1));
  const lights = navLights(group, L, B, y0 + 12, y0);
  return { group, L, B, T, type: 'passenger', label: 'Navire à passagers', name, cruise: rnd(6.5, 8), lights, air: y0 + 12 };
}

function tug() {
  const L = rnd(26, 32), B = L * 0.36, T = 3.6, D = T + 2.2;
  const mats = {
    hull: makeShipMaterial({ color: pick([0x1a1a1a, 0x8b1a14, 0x173a63]), colorB: 0x7a1f1a, mode: PAINT.HULL, rust: 0.5, grime: 0.6, roughness: 0.55, bootTop: 0.3, side: THREE.DoubleSide }),
    deck: makeShipMaterial({ color: 0x5a5e60, mode: PAINT.DECK, roughness: 0.85, rust: 0.5 }),
    house: makeShipMaterial({ color: pick([0xe8e6dd, 0xc23b22]), mode: PAINT.HOUSE, roughness: 0.5, levelH: 2.5, bridgeLevel: 2, winW: 1.3, winSpacing: 1.6, grime: 0.6 }),
    dark: makeShipMaterial({ color: 0x111111, roughness: 0.9 }),
    metal: makeShipMaterial({ color: 0xd8d6cf, mode: PAINT.METAL, roughness: 0.5 }),
  };
  const hd = buildHull({ L, B, D, T, sheerFwd: 1.6, sheerAft: 0.2, bowRake: 1.5, transom: 0.8, transomBottom: 0.3, parallel: 0.1, midFull: 2.5, flare: 0.6, bulwark: 0.8 });
  const b = new Builder();
  addHull(b, hd, mats);
  const deckAt = (x) => deckHeightAt(hd, x);
  const wx = L * 0.12, wy = deckAt(wx);
  mats.house.userData.paint.uDeckBase.value = wy;
  b.box(mats.house, L * 0.34, 2.5, B * 0.7, wx, wy, 0);
  b.box(mats.house, L * 0.22, 2.5, B * 0.6, wx + 0.5, wy + 2.5, 0);
  b.taper(mats.house, L * 0.16, 2.5, B * 0.56, wx + 1, wy + 5, 0, 1.05, 1.05);
  b.cyl(mats.metal, 0.12, 0.15, 5, wx, wy + 10, 0);
  // thick rubber fenders round the bow
  b.add(mats.dark, new THREE.TorusGeometry(B * 0.45, 0.45, 8, 24, Math.PI), L / 2 - B * 0.45, deckAt(L / 2 - 1) - 0.6, 0, Math.PI / 2, 0, -Math.PI / 2);
  b.box(mats.dark, 1.2, 1.2, 1.2, -L * 0.3, deckAt(-L * 0.3), 0);
  const group = b.build();
  const lights = navLights(group, L, B, wy + 12, deckAt(0));
  return { group, L, B, T, type: 'tug', label: 'Remorqueur', name: pick(['ABEILLE IROISE', 'VB TREBERON', 'MERLIN']), cruise: rnd(4, 6), lights, air: wy + 12 };
}

function sailSurface(points, camber, segU = 10, segV = 14) {
  // points: [tack, head, clew] - triangle sail with camber along the chord
  const [a, h, c] = points.map((p) => new THREE.Vector3(...p));
  const pos = [];
  const idx = [];
  for (let j = 0; j <= segV; j++) {
    const v = j / segV;
    const luff = a.clone().lerp(h, v);
    const leech = c.clone().lerp(h, v);
    for (let i = 0; i <= segU; i++) {
      const u = i / segU;
      const p = luff.clone().lerp(leech, u);
      const chord = leech.distanceTo(luff);
      const bulge = Math.sin(Math.PI * Math.pow(u, 0.8)) * camber * chord * (1 - v * 0.6);
      p.z += bulge;
      pos.push(p.x, p.y, p.z);
    }
  }
  for (let j = 0; j < segV; j++) for (let i = 0; i < segU; i++) {
    const k = j * (segU + 1) + i;
    idx.push(k, k + 1, k + segU + 1, k + 1, k + segU + 2, k + segU + 1);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setIndex(idx);
  g.computeVertexNormals();
  return g;
}

function sailboat() {
  const L = rnd(8.5, 13), B = L * 0.33, T = 0.45, D = T + L * 0.1;
  const mats = {
    hull: makeShipMaterial({ color: pick([0xf2f2ee, 0xf2f2ee, 0xf2f2ee, 0x1c2c4c, 0xe9e2cf]), colorB: pick([0x1c2c4c, 0x2a2a2a, 0x7a1f1a]), mode: PAINT.HULL, rust: 0, grime: 0.15, roughness: 0.22, bootTop: 0.05, side: THREE.DoubleSide }),
    deck: makeShipMaterial({ color: 0xd9d7d0, mode: PAINT.DECK, roughness: 0.6, rust: 0 }),
    house: makeShipMaterial({ color: 0xf0efea, mode: PAINT.HOUSE, roughness: 0.3, levelH: 0.75, bridgeLevel: 0, winW: 0.9, winSpacing: 1.3, grime: 0.1 }),
    spar: makeShipMaterial({ color: 0xc9ccce, mode: PAINT.METAL, roughness: 0.35, metalness: 0.7, grime: 0.1 }),
    sail: makeShipMaterial({ color: pick([0xf3f1ea, 0xf3f1ea, 0xe8e4d8, 0xd8d4c8]), roughness: 0.75, side: THREE.DoubleSide, grime: 0.15 }),
    dark: makeShipMaterial({ color: 0x1a1a1a, roughness: 0.5 }),
  };
  const hd = buildHull({ L, B, D, T, sheerFwd: 0.25, sheerAft: 0.05, bowRake: L * 0.06, sternOverhang: L * 0.03, transom: 0.75, transomBottom: 0.1, parallel: 0.05, midFull: 1.6, bowFull: 1.2, flare: 0.15, camber: 0.06, stemFoot: 0.5 });
  const b = new Builder();
  addHull(b, hd, mats);
  const deckAt = (x) => deckHeightAt(hd, x);
  const y0 = deckAt(0);
  mats.house.userData.paint.uDeckBase.value = y0;
  b.taper(mats.house, L * 0.35, 0.6, B * 0.55, L * 0.03, y0, 0, 0.9, 0.85);
  const mastX = L * 0.12, mastH = L * 1.35;
  b.cyl(mats.spar, 0.07, 0.09, mastH, mastX, y0 + mastH / 2, 0, 0, 0, 8);
  const boomL = L * 0.42;
  b.rod(mats.spar, [mastX, y0 + 1.0, 0], [mastX - boomL, y0 + 1.1, 0], 0.06);
  b.rod(mats.dark, [mastX, y0 + mastH, 0], [L / 2 + L * 0.05, deckAt(L / 2 - 0.3) + 0.1, 0], 0.012, 4);
  b.rod(mats.dark, [mastX, y0 + mastH, 0], [-L / 2 + 0.3, deckAt(-L / 2 + 0.4) + 0.1, 0], 0.012, 4);
  for (const s of [-1, 1]) b.rod(mats.dark, [mastX, y0 + mastH * 0.9, 0], [mastX - 0.3, y0, s * B * 0.45], 0.01, 4);
  // sails (built on the centre plane, trimmed by rotating around the mast)
  const group = b.build();
  const sailMain = new THREE.Mesh(sailSurface([[0, 1.1, 0], [0, mastH - 0.3, 0], [-boomL + 0.2, 1.15, 0]], 0.09), mats.sail);
  const sailJib = new THREE.Mesh(sailSurface([[L / 2 + L * 0.03 - mastX, 0.4, 0], [0.2, mastH * 0.82, 0], [-L * 0.12, 0.7, 0]], 0.1), mats.sail);
  for (const s of [sailMain, sailJib]) { s.castShadow = true; s.receiveShadow = true; }
  const rig = new THREE.Group();
  rig.position.set(mastX, y0, 0);
  const mainPivot = new THREE.Group(); mainPivot.add(sailMain);
  const jibPivot = new THREE.Group(); jibPivot.add(sailJib);
  rig.add(mainPivot, jibPivot);
  group.add(rig);
  const lights = navLights(group, L, B, y0 + mastH, y0);
  return { group, L, B, T, type: 'sailboat', label: 'Voilier', name: pick(['Ar Vag', 'Penn Kalet', 'Morgane', 'Kenavo', 'Iroise', 'Sterenn', 'Avel Dro']), cruise: rnd(2.2, 3.5), lights, air: y0 + mastH, sails: { main: mainPivot, jib: jibPivot }, mastH };
}

function motorboat() {
  const L = rnd(5.5, 8.5), B = L * 0.38, T = 0.35, D = T + 0.75;
  const mats = {
    hull: makeShipMaterial({ color: pick([0xf2f2ee, 0xf2f2ee, 0x2b3a4a, 0xd5d0c4]), colorB: 0x1d2a3a, mode: PAINT.HULL, rust: 0, grime: 0.2, roughness: 0.25, bootTop: 0.1, side: THREE.DoubleSide }),
    deck: makeShipMaterial({ color: 0xcfcdc6, mode: PAINT.DECK, roughness: 0.7, rust: 0 }),
    house: makeShipMaterial({ color: 0xefeee9, mode: PAINT.HOUSE, roughness: 0.3, levelH: 1.3, bridgeLevel: 0, winW: 1.0, winSpacing: 1.1, grime: 0.15 }),
    dark: makeShipMaterial({ color: 0x151515, roughness: 0.45 }),
    metal: makeShipMaterial({ color: 0xbfc3c6, mode: PAINT.METAL, roughness: 0.3, metalness: 0.8 }),
  };
  const hd = buildHull({ L, B, D, T, sheerFwd: 0.3, sheerAft: 0.0, bowRake: L * 0.1, transom: 0.92, transomBottom: 0.05, parallel: 0.2, midFull: 1.4, bowFull: 1.1, flare: 0.3, deadrise: 1, camber: 0.05, stemFoot: 0.2, bulwark: 0.35 });
  const b = new Builder();
  addHull(b, hd, mats);
  const deckAt = (x) => deckHeightAt(hd, x);
  const y0 = deckAt(0);
  mats.house.userData.paint.uDeckBase.value = y0;
  if (Math.random() < 0.5) b.taper(mats.house, L * 0.3, 1.3, B * 0.7, L * 0.05, y0, 0, 0.8, 0.9);
  else b.box(mats.house, 0.8, 1.0, 0.9, 0, y0, 0);
  b.box(mats.dark, 0.5, 1.1, 0.45, -L / 2 - 0.2, deckAt(-L / 2 + 0.2) - 0.7, 0);
  b.rod(mats.metal, [L * 0.15, y0 + 1.3, -B * 0.25], [L * 0.15, y0 + 1.3, B * 0.25], 0.03);
  const group = b.build();
  const lights = navLights(group, L, B, y0 + 1.8, y0);
  return { group, L, B, T, type: 'motorboat', label: 'Vedette', name: pick(['Gwalarn', 'Mor Braz', 'Le Corsaire', 'Kerhorre']), cruise: rnd(5, 11), lights, air: y0 + 1.8 };
}

const BUILDERS = { container: containerShip, bulk: bulkCarrier, frigate, trawler, ferry, tug, sailboat, motorboat };

// ---------------------------------------------------------------------------
// Real 3D models (public/models/models.json), used instead of the procedural
// hull when one exists for a kind. Normalised to: +x bow, +y up, waterline y=0.

const MODEL_KINDS = { trawler: ['trawler'], sailboat: ['sailboat'], motorboat: ['motorboat'], cargo: ['container', 'bulk'], tug: ['tug'], ferry: ['ferry'], military: ['frigate'] };
const MODELS = {};
export const modelInfo = [];
const LABELS = { container: 'Porte-conteneurs', bulk: 'Vraquier', frigate: 'Frégate', trawler: 'Chalutier', ferry: 'Navire à passagers', tug: 'Remorqueur', sailboat: 'Voilier', motorboat: 'Vedette' };
const TYPES = { container: 'cargo', bulk: 'cargo', frigate: 'military', trawler: 'fishing', ferry: 'passenger', tug: 'tug', sailboat: 'sailboat', motorboat: 'motorboat' };
const CRUISE = { container: [5.5, 7.5], bulk: [5, 6.5], frigate: [6, 8], trawler: [3, 5], ferry: [6.5, 8], tug: [4, 6], sailboat: [2.2, 3.5], motorboat: [5, 11] };

export async function loadShipModels(base = '/models/') {
  let list;
  try {
    const r = await fetch(base + 'models.json');
    if (!r.ok) return 0;
    list = await r.json();
    if (!Array.isArray(list)) list = list.models || [];
  } catch { return 0; }
  const loader = new GLTFLoader();
  for (const m of list) {
    try {
      const gltf = await loader.loadAsync(base + m.file);
      const root = gltf.scene;
      root.updateMatrixWorld(true);
      const rawBox = new THREE.Box3().setFromObject(root);
      // orientation: bring the bow to +x and the deck up to +y
      const fix = new THREE.Group();
      fix.add(root);
      const up = m.upAxis || '+y', fwd = m.forwardAxis || '+x';
      if (up === '+z') root.rotation.x = -Math.PI / 2;
      if (up === '-z') root.rotation.x = Math.PI / 2;
      root.updateMatrixWorld(true);
      const yaw = { '+x': 0, '-x': Math.PI, '+z': Math.PI / 2, '-z': -Math.PI / 2 }[fwd] ?? 0;
      const holder = new THREE.Group();
      holder.add(fix);
      fix.rotation.y = yaw;
      holder.updateMatrixWorld(true);
      let box = new THREE.Box3().setFromObject(holder);
      const size = box.getSize(new THREE.Vector3());
      const scale = (m.lengthMetres || size.x) / Math.max(size.x, 1e-6);
      holder.scale.setScalar(scale);
      holder.updateMatrixWorld(true);
      box = new THREE.Box3().setFromObject(holder);
      const c = box.getCenter(new THREE.Vector3());
      const height = box.max.y - box.min.y;
      // waterline: given in file units, else a draft of ~12 % of the hull height
      let wl = box.min.y + height * 0.12;
      const rawMinUp = up === '+z' ? rawBox.min.z : up === '-z' ? -rawBox.max.z : rawBox.min.y;
      if (Number.isFinite(m.waterlineY)) wl = box.min.y + ((up === '-z' ? -m.waterlineY : m.waterlineY) - rawMinUp) * scale;
      holder.position.set(-c.x, -wl, -c.z);
      root.traverse((o) => {
        if (!o.isMesh) return;
        o.castShadow = o.receiveShadow = true;
        o.frustumCulled = true;
        const mats = Array.isArray(o.material) ? o.material : [o.material];
        mats.forEach((mt) => { if (mt.isMeshStandardMaterial || mt.isMeshPhysicalMaterial) { mt.envMapIntensity = 1; patchExternalMaterial(mt); } });
      });
      const final = box.getSize(new THREE.Vector3());
      const tpl = new THREE.Group();
      tpl.add(holder);
      const entry = { tpl, meta: m, L: final.x, B: final.z, T: wl - box.min.y, air: box.max.y - wl };
      for (const k of MODEL_KINDS[m.kind] || []) (MODELS[k] = MODELS[k] || []).push(entry);
      modelInfo.push({ kind: m.kind, name: m.name, author: m.author, licence: m.licence, source: m.source });
    } catch (e) { console.warn('model failed', m.file, e); }
  }
  return modelInfo.length;
}

// the simplest models are used less often
const MODEL_WEIGHT = { 'cargo-container-feeder.glb': 0.35, 'trawler-stern.glb': 0.4 };
function pickModel(list) {
  const w = list.map((e) => MODEL_WEIGHT[e.meta.file] ?? 1);
  let r = Math.random() * w.reduce((a, b) => a + b, 0);
  for (let i = 0; i < list.length; i++) { r -= w[i]; if (r <= 0) return list[i]; }
  return list[list.length - 1];
}

// French fishing registration (quartier maritime + 6 digits) painted on both sides of the bow, placed on
// the real hull surface by ray casting, so the OCR expert of the AI chain has something to read.
const QUARTIERS = ['BR', 'GV', 'CC', 'DZ', 'AD', 'LO', 'LS', 'CM'];
function hullDecalSpots(e) {
  if (e.decalSpots !== undefined) return e.decalSpots;
  const ray = new THREE.Raycaster();
  e.tpl.updateMatrixWorld(true);
  const spots = [];
  const x = e.L * 0.3, ys = [e.air * 0.16, e.air * 0.1, e.air * 0.22];
  for (const side of [1, -1]) {
    let hit = null;
    for (const y of ys) {
      ray.set(new THREE.Vector3(x, y, side * e.B * 2), new THREE.Vector3(0, 0, -side));
      const h = ray.intersectObject(e.tpl, true)[0];
      if (h && Math.abs(h.face.normal.y) < 0.8) { hit = h; break; }
    }
    if (!hit) continue;
    const n = hit.face.normal.clone().transformDirection(hit.object.matrixWorld);
    n.y = 0;
    if (n.lengthSq() < 1e-4 || Math.sign(n.z) !== side) n.set(0, 0, side);
    n.normalize();
    spots.push({ p: hit.point.clone(), n, side });
  }
  e.decalSpots = spots;
  return spots;
}

function fromModel(kind, e) {
  const group = e.tpl.clone(true);
  const lights = navLights(group, e.L, e.B, e.air * 0.95, e.air * 0.3);
  const names = { trawler: ['BR 521347', 'GV 384112', 'CC 902215'], sailboat: ['Ar Vag', 'Penn Kalet', 'Morgane', 'Sterenn'], motorboat: ['Gwalarn', 'Mor Braz'], container: ['IROISE TRADER', 'CELTIC STAR'], bulk: ['GOLDEN BRITTANY'], ferry: ['ENEZ EUSSA', 'FROMVEUR II'], tug: ['ABEILLE IROISE', 'VB TREBERON'], frigate: ['Frégate'] }[kind] || [kind];
  const cr = CRUISE[kind];
  let name = pick(names);
  if (kind === 'trawler') {
    name = `${pick(QUARTIERS)} ${Math.floor(rnd(100000, 999999))}`;
    const h = Math.max(0.45, Math.min(1.4, e.L * 0.045));
    for (const s of hullDecalSpots(e)) {
      // white with a dark outline: readable on a dark hull as on a light band, like real markings
      const d = nameDecal(name, { height: h, color: '#f4f4ee', font: '700 120px "Arial", sans-serif', outline: '#15171a' });
      d.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), s.n);
      d.position.copy(s.p).addScaledVector(s.n, 0.06);
      group.add(d);
    }
  }
  return { group, L: e.L, B: e.B, T: e.T, type: TYPES[kind], label: LABELS[kind], name, cruise: rnd(cr[0], cr[1]), lights, air: e.air, model: e.meta.name };
}

export function createShip(kind) {
  const useModel = MODELS[kind] && MODELS[kind].length && Math.random() < 0.85;
  const s = useModel ? fromModel(kind, pickModel(MODELS[kind])) : BUILDERS[kind]();
  s.kind = kind;
  s.group.traverse((o) => { if (o.isMesh) o.frustumCulled = true; });
  return s;
}
export const SHIP_KINDS = Object.keys(BUILDERS);
