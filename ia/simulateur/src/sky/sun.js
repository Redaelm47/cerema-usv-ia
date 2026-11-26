import * as THREE from 'three';

const RAD = Math.PI / 180;

/** Sun elevation/azimuth (degrees, azimuth from north, clockwise). */
export function solarPosition(utcMs, latDeg, lonDeg) {
  const d = (utcMs - 946728000000) / 86400000; // days since J2000.0
  const g = (357.529 + 0.98560028 * d) * RAD;
  const q = 280.459 + 0.98564736 * d;
  const L = (q + 1.915 * Math.sin(g) + 0.02 * Math.sin(2 * g)) * RAD;
  const e = (23.439 - 0.00000036 * d) * RAD;
  const ra = Math.atan2(Math.cos(e) * Math.sin(L), Math.cos(L));
  const dec = Math.asin(Math.sin(e) * Math.sin(L));
  const gmst = (18.697374558 + 24.06570982441908 * d) % 24;
  const lst = (gmst * 15 + lonDeg) * RAD;
  const ha = lst - ra;
  const lat = latDeg * RAD;
  const el = Math.asin(Math.sin(lat) * Math.sin(dec) + Math.cos(lat) * Math.cos(dec) * Math.cos(ha));
  const az = Math.atan2(-Math.sin(ha), Math.tan(dec) * Math.cos(lat) - Math.sin(lat) * Math.cos(ha));
  return { elevation: el / RAD, azimuth: ((az / RAD) + 360) % 360 };
}

/** Local time in Brest (Europe/Paris, DST approximated by month) -> UTC ms. */
export function brestTimeToUTC(year, month, day, hourLocal) {
  const dst = month >= 4 && month <= 10 ? 2 : 1;
  return Date.UTC(year, month - 1, day, 0, 0, 0) + (hourLocal - dst) * 3600000;
}

/** World direction (x east, y up, z south) from elevation/azimuth in degrees. */
export function sunDirection(elevationDeg, azimuthDeg, target = new THREE.Vector3()) {
  const el = elevationDeg * RAD, az = azimuthDeg * RAD;
  return target.set(Math.sin(az) * Math.cos(el), Math.sin(el), -Math.cos(az) * Math.cos(el)).normalize();
}
