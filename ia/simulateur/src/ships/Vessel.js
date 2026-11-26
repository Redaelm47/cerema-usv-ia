import * as THREE from 'three';

// Seakeeping: each hull samples the simulated sea at 5 points and follows the
// fitted plane through a damped oscillator per degree of freedom, tuned by size
// (big ships filter short waves and move slowly, small boats ride every wave).

const TAU = Math.PI * 2;
let NEXT_ID = 1;

export function wrapAngle(a) { while (a > Math.PI) a -= TAU; while (a < -Math.PI) a += TAU; return a; }

export class Vessel {
  constructor(spec, sampler) {
    this.id = NEXT_ID++;
    this.spec = spec;
    this.group = new THREE.Group();
    this.group.add(spec.group);
    this.L = spec.L; this.B = spec.B;
    this.pos = new THREE.Vector2();      // x, z (world)
    this.heading = 0;                     // compass radians (0 = north)
    this.speed = 0;                       // m/s through water
    this.targetSpeed = spec.cruise;
    this.turnRate = 0;
    this.maxTurn = THREE.MathUtils.degToRad(Math.min(9, 120 / spec.L + 0.4));
    this.accel = Math.max(0.02, 2.5 / spec.L);
    this.route = [];
    this.wp = 0;
    this.loop = false;
    this.done = false;
    this.mmsi = 227000000 + Math.floor(Math.random() * 999999);
    // seakeeping state
    const sL = Math.sqrt(spec.L), sB = Math.sqrt(spec.B);
    this.dof = {
      heave: { x: 0, v: 0, w: TAU / Math.max(1.2, 0.62 * sL), z: 0.35 },
      pitch: { x: 0, v: 0, w: TAU / Math.max(1.1, 0.55 * sL), z: 0.3 },
      roll: { x: 0, v: 0, w: TAU / Math.max(1.6, 2.2 * sB), z: 0.12 },
    };
    this.heel = 0; // steady heel (sailing, turning)
    this.sampler = sampler;
    this.slot = sampler ? sampler.alloc(5) : -1;
    this.lod = Math.max(0, Math.log2(Math.max(spec.L * 0.18, 0.3)) + 0.5);
    this.prevStern = null;
    this.prevBow = null;
    this.waterY = 0;
  }

  get forward() { return new THREE.Vector2(Math.sin(this.heading), -Math.cos(this.heading)); }

  place(x, z, heading) {
    this.pos.set(x, z);
    this.heading = heading;
    this.speed = this.targetSpeed;
    this.prevStern = null;
  }

  setRoute(points, loop = false) { this.route = points; this.wp = 0; this.loop = loop; this.done = false; }

  steer(dt) {
    if (!this.route.length) return;
    const t = this.route[this.wp];
    const dx = t.x - this.pos.x, dz = t.z - this.pos.y;
    const d = Math.hypot(dx, dz);
    if (d < Math.max(40, this.L * 1.2)) {
      this.wp++;
      if (this.wp >= this.route.length) {
        if (this.loop) this.wp = 0; else { this.wp = this.route.length - 1; this.done = true; }
      }
    }
    const want = Math.atan2(dx, -dz);
    const err = wrapAngle(want - this.heading);
    const desired = THREE.MathUtils.clamp(err * 0.6, -this.maxTurn, this.maxTurn);
    this.turnRate += (desired - this.turnRate) * Math.min(1, dt * (0.4 + 6 / this.L));
  }

  update(dt, sea) {
    const f = this.forward;
    if (!this.externalMotion) {
      this.steer(dt);
      this.heading = wrapAngle(this.heading + this.turnRate * dt);
      this.speed += THREE.MathUtils.clamp(this.targetSpeed - this.speed, -this.accel * dt, this.accel * dt);
      f.copy(this.forward);
      this.pos.addScaledVector(f, this.speed * dt);
    }

    // sea surface samples: bow, stern, port, starboard, centre
    const L = this.L * 0.38, B = this.B * 0.42;
    const r = new THREE.Vector2(-f.y, f.x); // starboard
    const s = this.sampler;
    let hb = 0, hs = 0, hp = 0, hst = 0, hc = 0;
    if (s && this.slot >= 0) {
      const pts = [
        [this.pos.x + f.x * L, this.pos.y + f.y * L],
        [this.pos.x - f.x * L, this.pos.y - f.y * L],
        [this.pos.x - r.x * B, this.pos.y - r.y * B],
        [this.pos.x + r.x * B, this.pos.y + r.y * B],
        [this.pos.x, this.pos.y],
      ];
      pts.forEach((p, i) => s.setPoint(this.slot + i, p[0], p[1], this.lod));
      hb = s.height(this.slot); hs = s.height(this.slot + 1); hp = s.height(this.slot + 2); hst = s.height(this.slot + 3); hc = s.height(this.slot + 4);
    }
    const heaveT = (hb + hs + hp + hst + hc * 2) / 6;
    const pitchT = Math.atan2(hb - hs, 2 * L);
    const rollT = Math.atan2(hp - hst, 2 * B) + this.heel - this.turnRate * this.speed * 0.02 * (this.spec.type === 'motorboat' ? -2 : 1);
    this.waterY = heaveT;
    const spring = (d, target) => {
      const a = d.w * d.w * (target - d.x) - 2 * d.z * d.w * d.v;
      d.v += a * dt;
      d.x += d.v * dt;
    };
    spring(this.dof.heave, heaveT);
    spring(this.dof.pitch, pitchT);
    spring(this.dof.roll, rollT);

    // planing boats trim bow-up with speed
    const trim = this.spec.type === 'motorboat' ? THREE.MathUtils.clamp((this.speed - 3) * 0.012, 0, 0.09) : 0;
    const g = this.group;
    g.position.set(this.pos.x, this.dof.heave.x + (this.spec.type === 'motorboat' ? Math.min(this.speed * 0.02, 0.18) : 0), this.pos.y);
    g.rotation.set(this.dof.roll.x, Math.PI / 2 - this.heading, this.dof.pitch.x + trim, 'YZX');
  }

  /** wake emitters for this frame */
  wakeEmitters(out) {
    const f = this.forward;
    const stern = new THREE.Vector2(this.pos.x - f.x * this.L * 0.48, this.pos.y - f.y * this.L * 0.48);
    const bow = new THREE.Vector2(this.pos.x + f.x * this.L * 0.45, this.pos.y + f.y * this.L * 0.45);
    if (this.prevStern && this.speed > 0.3) {
      const planing = this.spec.type === 'motorboat' ? 2.4 : 1;
      const size = Math.min(1, this.L / 8); // a small float barely makes foam
      out.push({ a: [this.prevStern.x, this.prevStern.y], b: [stern.x, stern.y], halfWidth: Math.max(this.B * 0.55, 0.3), foam: (0.12 * this.speed * planing + 0.2) * size, disturb: 0.25 * this.speed * size });
      const r = new THREE.Vector2(-f.y, f.x);
      const bw = Math.min(0.06 * this.speed * this.speed, 1.2) * planing * size;
      if (bw > 0.05) {
        for (const sgn of [-1, 1]) {
          const side = bow.clone().addScaledVector(r, sgn * this.B * 0.3);
          const back = side.clone().addScaledVector(f, -this.L * 0.25).addScaledVector(r, sgn * this.B * 0.35);
          out.push({ a: [side.x, side.y], b: [back.x, back.y], halfWidth: Math.max(Math.min(0.8, this.B * 0.6), this.B * 0.12), foam: bw, disturb: bw * 0.6 });
        }
      }
    }
    this.prevStern = stern;
  }
}
