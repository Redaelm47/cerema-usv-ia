import * as THREE from 'three';
import { EARTH_CURV } from '../ocean/OceanSurface.js';

// Ground truth for perception: projects every vessel's oriented bounding box
// into the camera image (with Earth curvature, so hull-down ships are cropped
// at the sea horizon) and tests line of sight against the terrain.

const corners = [];
for (let i = 0; i < 8; i++) corners.push(new THREE.Vector3());

export function computeGroundTruth(camera, vessels, terrain, width, height, seaLevel = 0) {
  const out = [];
  const camPos = camera.position;
  const v = new THREE.Vector3();
  // apparent depression of the sea horizon (with refraction)
  const hEye = Math.max(camPos.y - seaLevel, 0.3);
  for (const s of vessels) {
    const g = s.group;
    const L = s.L, B = s.B, T = s.spec.T, air = s.spec.air ?? 10;
    const dx = s.pos.x - camPos.x, dz = s.pos.y - camPos.z;
    const dist = Math.hypot(dx, dz);
    if (dist > 20000) continue;
    g.updateMatrixWorld();
    let k = 0;
    for (const x of [-L / 2, L / 2]) for (const y of [0, air]) for (const z of [-B / 2, B / 2]) corners[k++].set(x, y, z).applyMatrix4(g.matrixWorld);
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity, behind = 0;
    for (const c of corners) {
      const d2 = (c.x - camPos.x) ** 2 + (c.z - camPos.z) ** 2;
      v.set(c.x, c.y - d2 * EARTH_CURV, c.z).project(camera);
      if (v.z > 1 || v.z < -1) { behind++; continue; }
      const px = (v.x * 0.5 + 0.5) * width, py = (1 - (v.y * 0.5 + 0.5)) * height;
      minX = Math.min(minX, px); maxX = Math.max(maxX, px); minY = Math.min(minY, py); maxY = Math.max(maxY, py);
    }
    if (behind === 8) continue;
    // hull-down: part below the geometric sea horizon is hidden
    const horizonDist = Math.sqrt(2 * hEye / (2 * EARTH_CURV)) ;
    const hidden = dist > horizonDist ? (dist - horizonDist) ** 2 * EARTH_CURV : 0;
    const visibleFrac = THREE.MathUtils.clamp(1 - hidden / Math.max(air, 1), 0, 1);
    if (visibleFrac <= 0.02) continue;
    if (visibleFrac < 1) maxY = minY + (maxY - minY) * visibleFrac;
    if (maxX < 0 || minX > width || maxY < 0 || minY > height) continue;
    // terrain occlusion along the line of sight to the top of the ship
    let occluded = false;
    if (terrain && terrain.ready) {
      const top = s.dof ? s.dof.heave.x + air * 0.7 : air * 0.7;
      const n = Math.min(60, Math.ceil(dist / 80));
      for (let i = 1; i < n; i++) {
        const t = i / n;
        const x = camPos.x + dx * t, z = camPos.z + dz * t;
        const yLine = camPos.y + (top - camPos.y) * t - (dist * t) ** 2 * EARTH_CURV;
        if (terrain.heightAt(x, z) > yLine) { occluded = true; break; }
      }
    }
    if (occluded) continue;
    const bx0 = Math.max(0, minX), by0 = Math.max(0, minY), bx1 = Math.min(width, maxX), by1 = Math.min(height, maxY);
    if (bx1 - bx0 < 2 || by1 - by0 < 2) continue;
    out.push({
      id: s.id, mmsi: s.mmsi, cls: s.spec.type, label: s.spec.label, name: s.spec.name,
      bbox: [bx0, by0, bx1, by1], distance: dist,
      bearing: ((Math.atan2(dx, -dz) * 180) / Math.PI + 360) % 360,
      length: L, truncated: minX < 0 || maxX > width || minY < 0 || maxY > height,
      hullDown: visibleFrac < 1,
    });
  }
  return out;
}
