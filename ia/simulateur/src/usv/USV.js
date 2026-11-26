import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { makeShipMaterial, PAINT } from '../ships/shipMaterial.js';
import { Vessel, wrapAngle } from '../ships/Vessel.js';

// Micro drone de surface du projet Cerema x IMT Atlantique (moins d'un mètre) :
// catamaran à deux flotteurs, caisson électronique (pas de panneau solaire),
// caméra IA (type IMX500) à l'avant du caisson, à ~30 cm au-dessus de l'eau,
// propulsion différentielle par deux propulseurs (pas de safran).

function part(geo, x, y, z, rx = 0, ry = 0, rz = 0, sx = 1, sy = 1, sz = 1) {
  const g = geo.index ? geo.toNonIndexed() : geo.clone();
  g.deleteAttribute('uv');
  g.applyMatrix4(new THREE.Matrix4().compose(new THREE.Vector3(x, y, z), new THREE.Quaternion().setFromEuler(new THREE.Euler(rx, ry, rz)), new THREE.Vector3(sx, sy, sz)));
  return g;
}

export function buildUSVModel() {
  const L = 0.92, B = 0.52, T = 0.07;
  const hullMat = makeShipMaterial({ color: 0xf2c230, roughness: 0.35, grime: 0.25, mode: PAINT.PLAIN });
  const deckMat = makeShipMaterial({ color: 0x2b2f33, roughness: 0.6, grime: 0.2 });
  const boxMat = makeShipMaterial({ color: 0xe9e8e3, roughness: 0.4, grime: 0.2 });
  const dark = makeShipMaterial({ color: 0x131517, roughness: 0.45, metalness: 0.2 });
  const glass = makeShipMaterial({ color: 0x0a0c0e, roughness: 0.05, metalness: 0.0 });
  const orange = makeShipMaterial({ color: 0xf06a1d, roughness: 0.45 });
  const parts = new Map();
  const add = (m, g) => { if (!parts.has(m)) parts.set(m, []); parts.get(m).push(g); };
  // two pontoons (capsules), waterline at y = 0
  const pz = 0.19, pr = 0.075;
  for (const s of [-1, 1]) {
    add(hullMat, part(new THREE.CapsuleGeometry(pr, L - 2 * pr, 6, 16), 0, pr - T, s * pz, 0, 0, Math.PI / 2));
    // slightly raised nose
    add(hullMat, part(new THREE.SphereGeometry(pr * 0.98, 14, 10), L / 2 - pr * 0.9, pr - T + 0.012, s * pz));
  }
  // cross beams and deck plate
  const deckY = 2 * pr - T + 0.012;
  add(deckMat, part(new THREE.BoxGeometry(0.62, 0.018, 0.5), -0.04, deckY, 0));
  // electronics box (no solar panel on the real drone)
  add(boxMat, part(new THREE.BoxGeometry(0.42, 0.11, 0.3), -0.06, deckY + 0.064, 0));
  // camera on a short post at the front of the box: dark housing + glass dome
  const camY = deckY + 0.33;
  add(dark, part(new THREE.CylinderGeometry(0.014, 0.018, camY - deckY - 0.1, 10), 0.15, (deckY + 0.12 + camY - 0.03) / 2, 0));
  add(dark, part(new THREE.BoxGeometry(0.09, 0.07, 0.09), 0.16, camY, 0));
  add(glass, part(new THREE.SphereGeometry(0.03, 16, 12, 0, Math.PI * 2, 0, Math.PI / 2), 0.205, camY, 0, 0, 0, -Math.PI / 2));
  // GNSS puck, antenna mast with light
  add(dark, part(new THREE.CylinderGeometry(0.035, 0.04, 0.02, 16), -0.16, deckY + 0.135, 0.08));
  add(dark, part(new THREE.CylinderGeometry(0.005, 0.006, 0.32, 6), -0.22, deckY + 0.28, -0.08));
  add(orange, part(new THREE.SphereGeometry(0.018, 10, 8), -0.22, deckY + 0.45, -0.08));
  // two thrusters under the stern of each pontoon
  for (const s of [-1, 1]) {
    add(dark, part(new THREE.CylinderGeometry(0.028, 0.028, 0.09, 12), -L / 2 + 0.06, -T - 0.02, s * pz, 0, 0, Math.PI / 2));
    add(dark, part(new THREE.BoxGeometry(0.02, 0.06, 0.012), -L / 2 + 0.07, -T + 0.02, s * pz));
  }
  const group = new THREE.Group();
  for (const [m, gs] of parts) {
    const mesh = new THREE.Mesh(mergeGeometries(gs, false), m);
    mesh.castShadow = mesh.receiveShadow = true;
    group.add(mesh);
  }
  // camera mount: optical centre just behind the glass dome
  const mount = new THREE.Object3D();
  mount.position.set(0.22, camY, 0);
  group.add(mount);
  const lights = new THREE.Group();
  const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.012, 8, 6), new THREE.MeshBasicMaterial({ color: new THREE.Color(0xfff4dd).multiplyScalar(60) }));
  lamp.position.set(-0.22, deckY + 0.47, -0.08);
  lights.add(lamp); lights.visible = false;
  group.add(lights);
  return { group, L, B, T, type: 'usv', label: 'Drone de surface', name: 'USV-IA', cruise: 0, mount, lights, deckY, camY, air: deckY + 0.47 };
}

export class USV extends Vessel {
  constructor(sampler) {
    super(buildUSVModel(), sampler);
    this.throttle = 0;   // -0.5 .. 1
    this.rudder = 0;     // -1 .. 1 (différentiel des propulseurs, positif = tribord)
    this.maxSpeed = 5 / 1.944; // m/s : 5 nœuds, la vitesse maximale retenue pour le drone
    this.u = 0;          // vitesse d'avance
    this.r = 0;          // vitesse de lacet
    this.mode = 'manual'; // manual | heading | waypoint | approach | external
    this.cmdHeading = 0;
    this.cmdSpeed = 0;
    this.goal = null;
    this.target = null;
    this.standoff = 40;
    this.lod = 0;
    // a light float rides every wave
    this.dof.heave.w = (Math.PI * 2) / 0.55; this.dof.heave.z = 0.55;
    this.dof.pitch.w = (Math.PI * 2) / 0.5; this.dof.pitch.z = 0.45;
    this.dof.roll.w = (Math.PI * 2) / 0.6; this.dof.roll.z = 0.4;
    this.grounded = false;
    this.splash = 0;     // 0..1, water hitting the front of the drone this frame
    this._prevBowRel = 0;
  }

  steer() {}

  autopilot() {
    let wantH = null, wantU = null;
    if (this.mode === 'heading' || this.mode === 'external') { wantH = this.cmdHeading; wantU = this.cmdSpeed; }
    if (this.mode === 'waypoint' && this.goal) {
      const dx = this.goal.x - this.pos.x, dz = this.goal.z - this.pos.y;
      const d = Math.hypot(dx, dz);
      wantH = Math.atan2(dx, -dz);
      wantU = Math.min(this.cmdSpeed || this.maxSpeed, d * 0.1);
      if (d < 3) { this.mode = 'heading'; this.cmdSpeed = 0; this.cmdHeading = this.heading; }
    }
    if (this.mode === 'approach' && this.target) {
      const t = this.target;
      const tf = t.forward;
      const side = new THREE.Vector2(-tf.y, tf.x);
      // rejoindre le travers du navire à la distance de garde
      const aim = new THREE.Vector2(t.pos.x, t.pos.y).addScaledVector(side, this.standoff + t.B / 2).addScaledVector(tf, Math.min(20, t.speed * 4));
      const dx = aim.x - this.pos.x, dz = aim.y - this.pos.y;
      const d = Math.hypot(dx, dz);
      wantH = Math.atan2(dx, -dz);
      wantU = THREE.MathUtils.clamp(d * 0.08, 0, this.maxSpeed);
    }
    if (wantH !== null) {
      const err = wrapAngle(wantH - this.heading);
      this.rudder = THREE.MathUtils.clamp(err * 1.8 - this.r * 0.8, -1, 1);
    }
    if (wantU !== null) {
      this.throttle = THREE.MathUtils.clamp(wantU / this.maxSpeed + (wantU - this.u) * 0.5, -0.5, 1);
    }
  }

  update(dt, terrain) {
    if (this.mode !== 'manual') this.autopilot(dt);
    // surge: thrust - linear and quadratic drag, top speed ~maxSpeed
    const thrust = this.throttle * 1.6;
    const drag = 0.15 * this.u + ((1.6 - 0.15 * this.maxSpeed) / (this.maxSpeed * this.maxSpeed)) * this.u * Math.abs(this.u);
    this.u += (thrust - drag) * dt;
    // differential thrust turns the drone even when stopped
    const rTarget = this.rudder * (0.55 + Math.abs(this.u) * 0.2);
    this.r += (rTarget - this.r) * Math.min(1, dt * 3.5);
    this.heading = wrapAngle(this.heading + this.r * dt);
    this.speed = this.u;
    this.turnRate = this.r;
    const f = this.forward;
    const nx = this.pos.x + f.x * this.u * dt, nz = this.pos.y + f.y * this.u * dt;
    const h = terrain ? terrain.heightAt(nx, nz) : -50;
    this.grounded = h > -0.15;
    if (this.grounded) this.u *= 0.3; else this.pos.set(nx, nz);
    this.targetSpeed = this.u;
    this.externalMotion = true;
    super.update(dt);
    // a small bow-up trim under thrust
    this.group.rotation.z += THREE.MathUtils.clamp(this.u * 0.015, -0.01, 0.03);
    // water climbing over the bow (spray onto the camera dome)
    if (this.sampler && this.slot >= 0) {
      const bowWater = this.sampler.height(this.slot);
      const lift = Math.sin(this.dof.pitch.x) * this.L * 0.38;
      const bowDeck = this.group.position.y + this.spec.deckY + lift;
      const camH = this.group.position.y + this.spec.camY + lift * 0.6;
      const rel = bowWater - bowDeck;
      const rising = (rel - this._prevBowRel) / Math.max(dt, 1e-3);
      this._prevBowRel = rel;
      // spray when green water reaches the bow deck, a full wash only if it climbs to the dome
      const spray = THREE.MathUtils.clamp(rel * 5 + Math.max(rising, 0) * 0.08 * (rel > -0.05 ? 1 : 0), 0, 0.8);
      const wash = bowWater > camH - 0.04 ? 1 : 0;
      this.splash = Math.max(spray, wash);
    }
  }
}
