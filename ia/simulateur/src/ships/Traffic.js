import * as THREE from 'three';
import { createShip } from './ShipFactory.js';
import { Vessel } from './Vessel.js';

// Maritime traffic of the Goulet de Brest: merchant ships and the navy follow
// the deep-water lanes in and out of the Rade, fishing boats work the approaches,
// yachts sail around, small craft go about their business.

const rnd = (a, b) => a + Math.random() * (b - a);

function normPts(points) {
  return points.map((p) => (Array.isArray(p) ? { x: p[0], z: -p[1] } : { x: p.x, z: p.z ?? -(p.n ?? p.y) }));
}

export class Traffic {
  constructor(scene, sampler, terrain, placesData) {
    this.scene = scene;
    this.sampler = sampler;
    this.terrain = terrain;
    this.vessels = [];
    this.density = 0.6;
    this.lanes = [];
    const lanes = placesData?.lanes || placesData?.shipping_lanes || [];
    for (const l of lanes) {
      const pts = normPts(l.points || l.waypoints || l);
      if (pts.length >= 2) this.lanes.push({ name: l.name || 'lane', pts });
    }
    if (!this.lanes.length) {
      // fallback: straight lane past the origin
      this.lanes.push({ name: 'default', pts: [{ x: -9000, z: 300 }, { x: 0, z: -200 }, { x: 9000, z: -600 }] });
    }
    this.timer = 0;
    this.maxRange = 16000;
    this.auto = true; // automatic traffic; ships added by the operator (role 'user') are never removed by it
  }

  isWater(x, z, minDepth = 4) {
    if (!this.terrain || !this.terrain.ready) return true;
    return this.terrain.heightAt(x, z) < -minDepth;
  }

  randomWaterPoint(cx, cz, rMin, rMax, minDepth = 4) {
    for (let i = 0; i < 40; i++) {
      const a = Math.random() * Math.PI * 2, r = rnd(rMin, rMax);
      const x = cx + Math.cos(a) * r, z = cz + Math.sin(a) * r;
      if (this.isWater(x, z, minDepth)) return { x, z };
    }
    return null;
  }

  clearPath(a, b, minDepth = 3) {
    const n = Math.ceil(Math.hypot(b.x - a.x, b.z - a.z) / 60);
    for (let i = 1; i < n; i++) {
      const t = i / n;
      if (!this.isWater(a.x + (b.x - a.x) * t, a.z + (b.z - a.z) * t, minDepth)) return false;
    }
    return true;
  }

  add(kind) {
    const v = new Vessel(createShip(kind), this.sampler);
    this.scene.add(v.group);
    this.vessels.push(v);
    return v;
  }

  remove(v) {
    this.scene.remove(v.group);
    if (this.sampler) this.sampler.release(v.slot, 5);
    if (!v.spec.model) v.group.traverse((o) => { if (o.isMesh) { o.geometry.dispose(); } });
    this.vessels.splice(this.vessels.indexOf(v), 1);
  }

  spawnLaneShip(cam, kind, anywhere) {
    const lane = this.lanes[Math.floor(Math.random() * this.lanes.length)];
    const inbound = Math.random() < 0.5;
    const pts = inbound ? lane.pts.slice() : lane.pts.slice().reverse();
    // lateral offset: keep to starboard of the lane axis
    const off = rnd(40, 160);
    const shifted = pts.map((p, i) => {
      const q = pts[Math.min(i + 1, pts.length - 1)], o = pts[Math.max(i - 1, 0)];
      const dx = q.x - o.x, dz = q.z - o.z, l = Math.hypot(dx, dz) || 1;
      return { x: p.x + (-dz / l) * -off, z: p.z + (dx / l) * -off };
    });
    let startIdx = 0, sx = shifted[0].x, sz = shifted[0].z;
    if (anywhere) {
      // random position along the lane
      const seg = Math.floor(Math.random() * (shifted.length - 1));
      const t = Math.random();
      sx = shifted[seg].x + (shifted[seg + 1].x - shifted[seg].x) * t;
      sz = shifted[seg].z + (shifted[seg + 1].z - shifted[seg].z) * t;
      startIdx = seg + 1;
    }
    if (Math.hypot(sx - cam.x, sz - cam.z) > this.maxRange) return null;
    if (!this.isWater(sx, sz, 6)) return null;
    for (const o of this.vessels) if (Math.hypot(o.pos.x - sx, o.pos.y - sz) < 400) return null;
    const v = this.add(kind);
    const nxt = shifted[Math.min(startIdx, shifted.length - 1)];
    v.place(sx, sz, Math.atan2(nxt.x - sx, -(nxt.z - sz)));
    v.setRoute(shifted.slice(startIdx));
    v.role = 'lane';
    return v;
  }

  spawnWanderer(cam, kind, anywhere) {
    const minD = kind === 'sailboat' || kind === 'motorboat' ? 2.5 : 6;
    const p = this.randomWaterPoint(cam.x, cam.z, anywhere ? 150 : 2500, anywhere ? 5000 : 6000, minD);
    if (!p) return null;
    const v = this.add(kind);
    const route = [];
    let cur = p;
    for (let i = 0; i < 6; i++) {
      const q = this.randomWaterPoint(cur.x, cur.z, 400, 1800, minD);
      if (q && this.clearPath(cur, q, minD)) { route.push(q); cur = q; }
    }
    if (!route.length) route.push(p);
    v.place(p.x, p.z, Math.atan2(route[0].x - p.x, -(route[0].z - p.z)));
    v.setRoute(route, true);
    v.role = 'wander';
    if (kind === 'trawler') v.targetSpeed = rnd(1.5, 3.5);
    return v;
  }

  populate(cam) {
    const autoCount = () => this.vessels.filter((v) => v.role !== 'user').length;
    for (let i = 0; i < 60 && autoCount() < this.targetCount(); i++) this.tick(cam, true);
  }

  targetCount() { return Math.round(4 + this.density * 18); }

  /** a ship placed by the operator on the map: straight course, or its own route */
  addUser(kind, x, z, heading, speed) {
    const v = this.add(kind);
    v.role = 'user';
    v.userSpeed = speed;
    v.targetSpeed = speed;
    v.place(x, z, heading);
    v.setRoute([]);
    v.halted = false;
    return v;
  }

  /** removes the automatic traffic (keeps the operator's ships) */
  clearAuto() { for (const v of this.vessels.slice()) if (v.role !== 'user') this.remove(v); }

  /** after a teleport: forget the ships left far behind and fill the new area */
  recentre(cam) {
    for (const v of this.vessels.slice()) if (v.role !== 'user' && Math.hypot(v.pos.x - cam.x, v.pos.y - cam.z) > 9000) this.remove(v);
    if (this.auto) this.populate(cam);
  }

  tick(cam, anywhere = false) {
    if (!this.auto) return;
    const counts = {};
    for (const v of this.vessels) if (v.role !== 'user') counts[v.spec.kind] = (counts[v.spec.kind] || 0) + 1;
    const d = this.density;
    const want = {
      container: Math.round(d * 1.5), bulk: Math.round(d * 1.2), frigate: d > 0.3 ? 1 : 0, ferry: d > 0.2 ? 1 : 0,
      tug: d > 0.5 ? 1 : 0, trawler: Math.round(1 + d * 3), sailboat: Math.round(2 + d * 8), motorboat: Math.round(1 + d * 4),
    };
    const lane = { container: 1, bulk: 1, frigate: 1, ferry: 1, tug: 1 };
    for (const k of Object.keys(want)) {
      if ((counts[k] || 0) < want[k]) {
        if (lane[k]) this.spawnLaneShip(cam, k, anywhere);
        else this.spawnWanderer(cam, k, anywhere);
        return;
      }
    }
  }

  update(dt, cam, sunElevation) {
    this.timer += dt;
    if (this.timer > 2) { this.timer = 0; this.tick(cam, false); }
    const night = sunElevation < 2;
    for (const v of this.vessels.slice()) {
      // avoid running aground: wanderers pick a new leg when land is ahead
      if (v.role === 'wander' && this.terrain?.ready) {
        const f = v.forward;
        const ahead = { x: v.pos.x + f.x * (v.L * 2 + 40), z: v.pos.y + f.y * (v.L * 2 + 40) };
        if (!this.isWater(ahead.x, ahead.z, 1.5)) {
          const q = this.randomWaterPoint(v.pos.x, v.pos.y, 300, 1200, 3);
          if (q) v.setRoute([q], false);
        }
      }
      if (v.role === 'user') this.steerUser(v);
      if (v.spec.type === 'sailboat') this.trimSails(v);
      if (v.spec.lights) v.spec.lights.visible = night;
      if (v.role === 'user') continue;
      const far = Math.hypot(v.pos.x - cam.x, v.pos.y - cam.z) > this.maxRange + 2000;
      if (far || (v.done && v.role === 'lane')) this.remove(v);
    }
  }

  steerUser(v) {
    // follows its route (or holds its course), slows down and stops before running aground
    let want = v.userSpeed;
    if (v.route.length && v.done && !v.loop) want = 0;
    v.halted = false;
    if (this.terrain?.ready && v.speed > 0.05) {
      const f = v.forward;
      const look = v.L * 1.5 + v.speed * 25;
      const ahead = { x: v.pos.x + f.x * look, z: v.pos.y + f.y * look };
      const draft = Math.max(1, (v.spec.T || 2) + 0.5);
      if (!this.isWater(ahead.x, ahead.z, draft)) { want = 0; v.halted = true; }
    }
    v.targetSpeed = want;
  }

  trimSails(v) {
    // wind from the west-south-west: boom eases out as the boat bears away
    const windFrom = this.windFrom ?? THREE.MathUtils.degToRad(250);
    let rel = v.heading - windFrom;
    while (rel > Math.PI) rel -= Math.PI * 2;
    while (rel < -Math.PI) rel += Math.PI * 2;
    const ang = Math.abs(rel);
    const ease = THREE.MathUtils.clamp((ang - 0.6) / 2.4, 0.05, 1) * 1.25;
    const side = rel > 0 ? 1 : -1;
    if (v.spec.sails) {
      v.spec.sails.main.rotation.y = side * ease;
      v.spec.sails.jib.rotation.y = side * ease * 0.6;
    }
    v.heel = side * -THREE.MathUtils.clamp(0.35 - ease * 0.2, 0.05, 0.32) * (this.windStrength ?? 1);
    // sailing boats slow down close-hauled
    const base = v.role === 'user' ? v.targetSpeed : v.spec.cruise;
    v.targetSpeed = base * THREE.MathUtils.clamp(0.4 + ang / 2.2, 0.4, 1.15);
  }
}
