import * as THREE from 'three';
import { OceanFFT } from './ocean/OceanFFT.js';
import { OceanSurface } from './ocean/OceanSurface.js';
import { OceanSampler } from './ocean/OceanSampler.js';
import { estimateHs } from './ocean/spectrum.js';
import { SkySystem } from './sky/SkySystem.js';
import { solarPosition, brestTimeToUTC, sunDirection } from './sky/sun.js';
import { CameraFX } from './post/CameraFX.js';
import { WakeSystem } from './fx/Wake.js';
import { setSkyUniforms } from './ships/shipMaterial.js';
import { Traffic } from './ships/Traffic.js';
import { loadShipModels } from './ships/ShipFactory.js';
import { USV } from './usv/USV.js';
import { Terrain } from './terrain/Terrain.js';
import { computeGroundTruth } from './sim/GroundTruth.js';
import { Bridge } from './bridge/Bridge.js';
import { HUD } from './ui/HUD.js';
import { MapView } from './ui/MapView.js';
import { LensDrops } from './fx/LensDrops.js';
import { Rain } from './fx/Rain.js';

const params = new URLSearchParams(location.search);
const DEG = Math.PI / 180;

class App {
  constructor() {
    this.canvas = document.getElementById('view');
    const r = (this.renderer = new THREE.WebGLRenderer({ canvas: this.canvas, antialias: false, powerPreference: 'high-performance' }));
    r.toneMapping = THREE.NoToneMapping;
    r.shadowMap.enabled = true;
    r.shadowMap.type = THREE.PCFShadowMap;
    r.shadowMap.autoUpdate = false;
    r.debug.onShaderError = (gl, program, vsh, fsh) => {
      console.error('Shader program error: ' + gl.getProgramInfoLog(program));
      for (const sh of [vsh, fsh]) {
        const log = gl.getShaderInfoLog(sh);
        if (!log) continue;
        const src = gl.getShaderSource(sh).split('\n');
        const m = /ERROR: \d+:(\d+)/.exec(log);
        const ln = m ? +m[1] : 0;
        console.error(log + '\n' + src.slice(Math.max(0, ln - 6), ln + 3).map((l, i) => `${ln - 5 + i}: ${l}`).join('\n'));
      }
    };
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(70, 16 / 9, 0.05, 120000);

    this.settings = {
      weather: 'Nuageux', hour: +(params.get('hour') ?? 19.6), month: +(params.get('month') ?? 6),
      wind: 6, windDir: 250, swell: 0.45, clouds: 0.55, haze: 0.35, tide: 0, rain: 0, fog: 0,
      traffic: 0.6, fov: +(params.get('fov') ?? 50), ev: 0, stabilize: false, lens: true, drops: params.get('drops') !== '0', autoDemo: params.get('demo') === '1',
    };
    this.weatherPresets = {
      Clair: { clouds: 0.32, haze: 0.2, wind: 6, swell: 0.6, cirrus: 0.35 },
      Pluie: { clouds: 1.0, haze: 0.68, wind: 9, swell: 0.8, cirrus: 0, rain: 0.55, fog: 0.3 },
      Grain: { clouds: 1.0, haze: 0.78, wind: 15, swell: 1.5, cirrus: 0, rain: 1.0, fog: 0.5 },
      Nuageux: { clouds: 0.58, haze: 0.35, wind: 6, swell: 0.45, cirrus: 0.4 },
      Couvert: { clouds: 0.97, haze: 0.55, wind: 11, swell: 1.0, cirrus: 0 },
      Brume: { clouds: 0.75, haze: 0.97, wind: 3.5, swell: 0.4, cirrus: 0, fog: 0.35 },
      'Coup de vent': { clouds: 0.85, haze: 0.5, wind: 17, swell: 2.2, cirrus: 0.1 },
      Couchant: { clouds: 0.42, haze: 0.45, wind: 6, swell: 0.6, cirrus: 0.6, hour: 21.45, month: 6 },
    };
    const w0 = params.get('weather');
    if (w0 && this.weatherPresets[w0]) {
      const p = this.weatherPresets[w0];
      Object.assign(this.settings, { weather: w0, clouds: p.clouds, haze: p.haze, wind: p.wind, swell: p.swell, rain: p.rain ?? 0, fog: p.fog ?? 0 });
      if (p.hour && !params.get('hour')) this.settings.hour = p.hour;
    }

    this.fft = new OceanFFT(r, this.seaParams());
    this.sky = new SkySystem(r);
    setSkyUniforms(this.sky.uniforms);
    this.ocean = new OceanSurface(this.fft, this.sky);
    this.fx = new CameraFX(r);
    this.sampler = new OceanSampler(r, this.fft);
    this.wake = new WakeSystem(r);
    this.terrain = new Terrain(this.sky);
    this.rain = new Rain();
    this.scene.add(this.sky.background, this.ocean.mesh, this.terrain.group, this.rain.mesh);

    this.sunLight = new THREE.DirectionalLight(0xffffff, 1);
    this.sunLight.castShadow = true;
    this.sunLight.shadow.mapSize.set(1536, 1536);
    const sc = this.sunLight.shadow.camera;
    sc.left = -90; sc.right = 90; sc.top = 90; sc.bottom = -90; sc.near = 1; sc.far = 1600;
    this.sunLight.shadow.bias = -0.0003;
    this.sunLight.shadow.normalBias = 0.04;
    this.scene.add(this.sunLight, this.sunLight.target);

    this.usv = new USV(this.sampler);
    this.scene.add(this.usv.group);
    this.view = params.get('view') || 'onboard';
    this.gimbal = { yaw: (+(params.get('pan') ?? 0)) * DEG, pitch: -0.035 };
    this.orbit = { yaw: 0.6, pitch: 0.28, dist: 3.2 };
    this.free = { yaw: 0, pitch: 0, pos: new THREE.Vector3() };
    this.keys = new Set();
    this.time = 0;
    this.simSeconds = 0;
    this.lastGT = [];
    this.detections = [];
    this.bridge = new Bridge(params.get('ws') || 'ws://127.0.0.1:8765');
    this.bridge.onCommand = (m) => this.onCommand(m);
    this.renderSize = { w: 1, h: 1 };
    this.demo = { target: null, since: 0, done: new Set() };
    this.seaHs = 0;
    this.drops = new LensDrops();
    this.pad = { active: false, prevButtons: [] };
  }

  seaParams() {
    const s = this.settings;
    // compass "wind from" -> direction the waves travel to, as an angle from +x towards +z
    const to = (s.windDir + 180) * DEG;
    const theta = Math.atan2(-Math.cos(to), Math.sin(to));
    const swellTo = (262 + 180) * DEG;
    // fetch: long from the Iroise sea (west), short from the Rade (east)
    const fromW = Math.cos((s.windDir - 260) * DEG);
    const fetchKm = 15 + 40 * Math.max(fromW, 0);
    return {
      windSpeed: s.wind, fetchKm, windDir: theta, swellHeight: s.swell, swellPeriod: 9 + s.swell * 2,
      swellDir: Math.atan2(-Math.cos(swellTo), Math.sin(swellTo)), choppiness: 0.95,
    };
  }

  async init(progress) {
    const tick = () => new Promise((r) => setTimeout(r, 30));
    progress(0.1, 'Océan');
    await tick();
    this.applySea(true);
    this.applyAtmosphere();
    this.updateSun();
    progress(0.3, 'Relief LiDAR et orthophotos IGN');
    let places = null;
    try {
      await this.terrain.load('/data/', this.renderer);
      places = await fetch('/data/places.json').then((r) => (r.ok ? r.json() : null)).catch(() => null);
    } catch (e) { console.warn('terrain not loaded', e); }
    this.places = places;
    this.meta = this.terrain.meta;
    progress(0.7, 'Modèles de navires');
    await tick();
    if (params.get('models') !== '0') this.modelCount = await loadShipModels('/models/');
    progress(0.8, 'Trafic maritime');
    await tick();
    if (this.terrain.ready) {
      const ou = this.ocean.uniforms;
      ou.uDem.value = this.terrain.far.tex;
      ou.uDemRect.value.copy(this.terrain.far.rect);
      ou.uDemNear.value = this.terrain.near.tex;
      ou.uDemNearRect.value.copy(this.terrain.near.rect);
      ou.uHasDem.value = 1;
    }
    const start = this.findStart();
    this.usv.place(start.x, start.z, (+(params.get('hdg') ?? 255)) * DEG);
    this.usv.u = 1.0;
    this.usv.mode = 'heading'; this.usv.cmdHeading = this.usv.heading; this.usv.cmdSpeed = +(params.get('speed') ?? 1.2);
    this.traffic = new Traffic(this.scene, this.sampler, this.terrain, places);
    this.traffic.density = this.settings.traffic;
    this.applySea(true);
    if (params.get('ships') !== '0') this.traffic.populate({ x: start.x, z: start.z });
    this.hud = new HUD(this);
    this.map = new MapView(this);
    if (params.get('map') === '1') this.map.toggle(true);
    this.bindInput();
    this.resize();
    addEventListener('resize', () => this.resize());
    this.applyCamera();
    if (params.get('gt') === '1') this.hud.toggleGT();
    if (params.get('ui') === '0') this.hud.toggleHidden();
    this.bridge.onStatus = () => this.resize();
    if (params.get('bridge') === '1') this.bridge.enable(true);
    if (params.get('scenario')) await this.loadScenario(params.get('scenario'));
    progress(0.9, 'Compilation des shaders');
    await tick();
    this.updateCamera(0.016);
    await this.renderer.compileAsync(this.scene, this.camera).catch(() => {});
    progress(1, 'Prêt');
  }

  placeList() {
    const pl = this.places?.places || this.places?.landmarks;
    if (!pl) return [];
    const arr = Array.isArray(pl) ? pl : Object.entries(pl).map(([name, v]) => ({ name, ...v }));
    return arr.map((p) => ({ name: p.name, x: p.x ?? p.local?.x, z: -(p.n ?? p.local?.n ?? p.y ?? 0) }));
  }

  findStart() {
    const ox = +(params.get('x') ?? NaN), oz = +(params.get('z') ?? NaN);
    let c;
    if (Number.isFinite(ox) && Number.isFinite(oz)) c = { x: ox, z: oz };
    else {
      const pl = this.placeList();
      const a = pl.find((p) => /mengant/i.test(p.name)), b = pl.find((p) => /espagnols/i.test(p.name));
      // in the deep channel of the Goulet, between Fort du Mengant and Pointe des Espagnols
      c = a && b ? { x: (a.x + b.x) / 2 - 500, z: (a.z + b.z) / 2 } : { x: -1500, z: 0 };
    }
    if (this.terrain.ready) {
      let best = c, tries = 0;
      while (this.terrain.heightAt(best.x, best.z) > -10 && tries++ < 400) best = { x: c.x + (Math.random() - 0.5) * 60 * tries ** 0.5, z: c.z + (Math.random() - 0.5) * 60 * tries ** 0.5 };
      c = best;
    }
    return c;
  }

  // ---------------------------------------------------------------- settings
  applySea(now = false) {
    clearTimeout(this._seaT);
    const go = () => {
      const p = this.seaParams();
      this.fft.setSea(p);
      this.ocean.setWind(p.windSpeed);
      this.seaHs = estimateHs(p);
      if (this.traffic) {
        this.traffic.windFrom = this.settings.windDir * DEG;
        this.traffic.windStrength = THREE.MathUtils.clamp(this.settings.wind / 9, 0.3, 1.4);
      }
    };
    if (now) go(); else this._seaT = setTimeout(go, 120);
  }

  applyAtmosphere() {
    const s = this.settings, U = this.sky.uniforms;
    U.uCoverage.value = s.clouds;
    this.sky.setHaze(1.5 + s.haze * 12);
    // rain curtains cut the visibility to a few kilometres and darken the cloud base
    U.uFogDensity.value = Math.max(0, s.haze - 0.6) ** 2 * 0.011 + s.rain * s.rain * 0.0006;
    U.uRain.value = s.rain;
    U.uCloudDensity.value = 45 + s.rain * 35;
    U.uCirrus.value = this.weatherPresets[s.weather]?.cirrus ?? 0.3;
  }

  applyWeather(name) {
    const p = this.weatherPresets[name];
    Object.assign(this.settings, { weather: name, clouds: p.clouds, haze: p.haze, wind: p.wind, swell: p.swell, rain: p.rain ?? 0, fog: p.fog ?? 0 });
    if (p.hour) this.settings.hour = p.hour;
    if (p.month) this.settings.month = p.month;
    this.applyAtmosphere();
    this.applySea();
    this.updateSun();
  }

  applyTide() { this.ocean.uniforms.uSeaLevel.value = this.settings.tide; }

  applyCamera() {
    const s = this.settings;
    this.fx.exposureBias = s.ev;
    const f = this.fx.finalMat.uniforms;
    f.uGrain.value = s.lens ? 0.14 : 0;
    f.uCA.value = s.lens ? 0.0035 : 0;
    f.uDistort.value = s.lens ? 0.06 : 0;
    f.uVignette.value = s.lens ? 0.55 : 0.2;
  }

  updateSun() {
    const s = this.settings;
    const p = solarPosition(brestTimeToUTC(2026, s.month, 15, s.hour), 48.345, -4.56);
    this.sunPos = p;
    this.sky.setSunDirection(sunDirection(p.elevation, p.azimuth));
  }

  simClock() {
    const h = this.settings.hour * 3600 + this.simSeconds;
    return { h: Math.floor(h / 3600) % 24, m: Math.floor(h / 60) % 60, s: Math.floor(h) % 60 };
  }

  scales() {
    const o = this.meta?.origin || { lat0: 48.345, lon0: -4.56 };
    const lat0 = o.lat0 ?? o.lat, lon0 = o.lon0 ?? o.lon, phi = lat0 * DEG;
    const mx = this.meta?.scale?.mx ?? (111412.84 * Math.cos(phi) - 93.5 * Math.cos(3 * phi) + 0.118 * Math.cos(5 * phi));
    const my = this.meta?.scale?.my ?? (111132.92 - 559.82 * Math.cos(2 * phi) + 1.175 * Math.cos(4 * phi));
    return { lat0, lon0, mx, my };
  }
  toLatLon(x, z) { const s = this.scales(); return { lat: s.lat0 - z / s.my, lon: s.lon0 + x / s.mx }; }
  fromLatLon(lat, lon) { const s = this.scales(); return { x: (lon - s.lon0) * s.mx, z: -(lat - s.lat0) * s.my }; }

  // ---------------------------------------------------------------- control
  /** l'opérateur prend la main (ou la rend au pilote automatique) */
  setManual(on) {
    const u = this.usv;
    this.operatorOverride = on; // tant que l'opérateur a la main, le pipeline ne pilote plus
    if (on) {
      if (u.mode !== 'manual') this._prevMode = u.mode;
      u.mode = 'manual'; u.target = null;
      this.hud?.alert('Pilotage manuel', 'Z S gaz · Q D cap · manette', 2500);
    } else if (u.resumeMission()) {
      this.hud?.alert('Pilote automatique', 'reprise de la route', 2500);
    } else {
      u.mode = 'heading'; u.cmdHeading = u.heading; u.cmdSpeed = Math.max(0, u.u);
      this.hud?.alert('Pilote automatique', 'maintien du cap et de la vitesse', 2500);
    }
  }

  pollGamepad(dt) {
    const pads = navigator.getGamepads ? navigator.getGamepads() : [];
    const gp = [...pads].find((p) => p && p.connected);
    if (!gp) return false;
    const dz = (v) => (Math.abs(v) < 0.12 ? 0 : (v - Math.sign(v) * 0.12) / 0.88);
    const thr = -dz(gp.axes[1] ?? 0);
    const yaw = dz(gp.axes[2] ?? 0) || dz(gp.axes[0] ?? 0);
    const rt = gp.buttons[7]?.value ?? 0, lt = gp.buttons[6]?.value ?? 0;
    const pressed = (i) => gp.buttons[i]?.pressed && !this.pad.prevButtons[i];
    if (pressed(0)) this.setManual(this.usv.mode !== 'manual');
    if (pressed(1)) { this.usv.mode = 'heading'; this.usv.target = null; this.usv.cmdHeading = this.usv.heading; this.usv.cmdSpeed = 0; }
    if (pressed(3)) this.setView(this.view === 'onboard' ? 'chase' : 'onboard');
    this.pad.prevButtons = gp.buttons.map((b) => b.pressed);
    const moving = Math.abs(thr) > 0 || Math.abs(yaw) > 0 || rt > 0.05 || lt > 0.05;
    if (moving && this.usv.mode !== 'manual') this.setManual(true);
    if (this.usv.mode === 'manual' && (moving || this.pad.active)) {
      const t = rt > 0.05 || lt > 0.05 ? rt - lt * 0.5 : thr;
      this.usv.throttle = THREE.MathUtils.clamp(t, -0.5, 1);
      this.usv.rudder = THREE.MathUtils.clamp(yaw, -1, 1);
    }
    this.pad.active = moving;
    // right stick vertical tilts the camera when using the left stick for the yaw
    if (gp.axes.length > 3 && !dz(gp.axes[2] ?? 0)) this.gimbal.pitch = THREE.MathUtils.clamp(this.gimbal.pitch - dz(gp.axes[3] ?? 0) * dt * 0.8, -0.6, 0.5);
    return true;
  }

  /** moves the drone instantly (map), keeping or setting its heading */
  teleport(x, z, heading = null) {
    const u = this.usv;
    const dx = x - u.pos.x, dz = z - u.pos.y;
    const h = heading ?? u.heading;
    u.pos.set(x, z);
    u.heading = h; u.u = 0; u.r = 0; u.speed = 0; u.turnRate = 0; u.throttle = 0; u.rudder = 0;
    u.prevStern = null; u.grounded = false;
    for (const d of Object.values(u.dof)) { d.x = 0; d.v = 0; }
    if (u.mode !== 'manual' && u.mode !== 'heading' && u.mode !== 'mission') { u.mode = 'heading'; u.target = null; }
    u.cmdHeading = h;
    this.free.pos.x += dx; this.free.pos.z += dz;
    this._chaseInit = false;
    this.drops.drops.length = 0;
    this.demo.target = null;
    this.traffic.recentre({ x, z });
  }

  /** Scénario rejouable : public/scenarios/<nom>.json (météo, heure, drone et sa route, navires). */
  async loadScenario(name) {
    const sc = await fetch(`/scenarios/${encodeURIComponent(name)}.json`).then((r) => (r.ok ? r.json() : null)).catch(() => null);
    if (!sc) { console.warn(`scénario introuvable : ${name}`); return null; }
    const s = this.settings;
    if (sc.weather && this.weatherPresets[sc.weather]) this.applyWeather(sc.weather);
    for (const k of ['hour', 'month', 'wind', 'windDir', 'swell', 'clouds', 'haze', 'rain', 'fog', 'tide']) if (sc[k] !== undefined) s[k] = sc[k];
    this.applyAtmosphere(); this.applySea(); this.updateSun(); this.applyTide();
    if (sc.auto_traffic === false) { this.traffic.auto = false; this.traffic.clearAuto(); }
    const d = sc.drone || {};
    if (d.lat !== undefined) { const p = this.fromLatLon(d.lat, d.lon); this.teleport(p.x, p.z, (d.heading_deg ?? 0) * DEG); }
    if (d.patrol_kn) this.usv.patrolSpeed = Math.min(d.patrol_kn / 1.944, this.usv.maxSpeed);
    if (d.route?.length) this.usv.startMission(d.route.map(([lat, lon]) => this.fromLatLon(lat, lon)), d.loop !== false);
    for (const v of sc.ships || []) {
      const p = this.fromLatLon(v.lat, v.lon);
      const ship = this.traffic.addUser(v.kind, p.x, p.z, (v.heading_deg ?? 0) * DEG, (v.speed_kn ?? 0) / 1.944);
      if (v.route?.length) ship.setRoute(v.route.map(([lat, lon]) => this.fromLatLon(lat, lon)), !!v.loop);
    }
    this.hud?.syncSliders();
    this.hud?.alert(sc.title || 'Scénario', sc.description || '', 6000);
    return sc;
  }

  approach(v) {
    this.usv.target = v;
    this.usv.mode = 'approach';
    this.hud.alert(`Approche de ${v.spec.name}`, v.spec.label);
  }

  onCommand(m) {
    const u = this.usv;
    const pilotage = ['cmd', 'heading', 'goto', 'approach', 'stop', 'mission', 'route'].includes(m.type);
    if (pilotage && this.operatorOverride) return;
    switch (m.type) {
      case 'cmd': u.mode = 'manual'; u.throttle = THREE.MathUtils.clamp(m.throttle ?? u.throttle, -0.4, 1); u.rudder = THREE.MathUtils.clamp(m.rudder ?? u.rudder, -1, 1); break;
      case 'heading': u.mode = 'external'; u.cmdHeading = (m.heading_deg ?? 0) * DEG; u.cmdSpeed = m.speed_mps ?? (m.speed_kn ?? 0) / 1.944; break;
      case 'goto': { u.goal = m.lat !== undefined ? this.fromLatLon(m.lat, m.lon) : { x: m.x, z: m.z }; u.cmdSpeed = m.speed_mps ?? 4; u.mode = 'waypoint'; break; }
      case 'approach': {
        const v = this.traffic.vessels.find((q) => q.id === m.target_id || q.mmsi === m.mmsi);
        if (v) { u.standoff = m.standoff_m ?? 40; this.approach(v); }
        break;
      }
      case 'stop': u.mode = 'heading'; u.cmdHeading = u.heading; u.cmdSpeed = 0; break;
      // reprise de la route (fin d'approche) ; sans route, le drone garde son cap
      case 'mission': if (!u.resumeMission()) { u.mode = 'heading'; u.cmdHeading = u.heading; u.cmdSpeed = m.speed_mps ?? 1; } break;
      case 'route': {
        const pts = (m.points || []).map((p) => (p.lat !== undefined ? this.fromLatLon(p.lat, p.lon) : { x: p.x, z: p.z }));
        if (m.speed_mps) u.patrolSpeed = Math.min(m.speed_mps, u.maxSpeed);
        u.startMission(pts, m.loop !== false);
        break;
      }
      case 'manual': this.setManual(m.on !== false); break;
      case 'alert': this.hud.alert(m.text || 'Alerte', m.detail || '', m.duration_ms || 5000); break;
      case 'detections': this.detections = m.boxes || []; this.detT = performance.now(); break;
      default: break;
    }
  }

  bindInput() {
    addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT') return;
      const k = e.code;
      if (this.map?.open) {
        if (k === 'KeyC') this.map.toggle(false);
        else if (this.map.onKey(e)) e.preventDefault();
        return;
      }
      if (k === 'KeyC') { this.map.toggle(true); return; }
      this.keys.add(e.code);
      if (k === 'Digit1') this.setView('onboard');
      if (k === 'Digit2') this.setView('chase');
      if (k === 'Digit3') this.setView('free');
      if (k === 'KeyH') this.hud.toggleHidden();
      if (k === 'KeyB') this.hud.toggleGT();
      if (k === 'KeyF') this.toggleFullscreen();
      if (k === 'KeyP') this.wantShot = true;
      if (k === 'KeyM') this.setManual(this.usv.mode !== 'manual');
      if (k === 'Space') { this.usv.mode = 'heading'; this.usv.target = null; this.usv.cmdHeading = this.usv.heading; this.usv.cmdSpeed = 0; e.preventDefault(); }
    });
    addEventListener('keyup', (e) => this.keys.delete(e.code));
    let drag = false;
    this.canvas.addEventListener('pointerdown', (e) => { drag = true; this.canvas.setPointerCapture(e.pointerId); });
    this.canvas.addEventListener('pointerup', () => (drag = false));
    this.canvas.addEventListener('pointermove', (e) => {
      if (!drag) return;
      const dx = e.movementX * 0.0035, dy = e.movementY * 0.0035;
      if (this.view === 'onboard') {
        this.gimbal.yaw = THREE.MathUtils.clamp(this.gimbal.yaw + dx, -2.6, 2.6);
        this.gimbal.pitch = THREE.MathUtils.clamp(this.gimbal.pitch - dy, -0.6, 0.5);
      } else if (this.view === 'chase') {
        this.orbit.yaw += dx; this.orbit.pitch = THREE.MathUtils.clamp(this.orbit.pitch + dy, -0.05, 1.3);
      } else {
        this.free.yaw += dx; this.free.pitch = THREE.MathUtils.clamp(this.free.pitch - dy, -1.5, 1.5);
      }
    });
    this.canvas.addEventListener('dblclick', () => { this.gimbal.yaw = 0; this.gimbal.pitch = -0.035; });
    this.canvas.addEventListener('wheel', (e) => {
      if (this.view === 'chase') this.orbit.dist = THREE.MathUtils.clamp(this.orbit.dist * (e.deltaY > 0 ? 1.1 : 0.9), 1.5, 600);
    }, { passive: true });
  }

  setView(v) {
    if (v === 'free' && this.view !== 'free') {
      this.free.pos.copy(this.camera.position);
      const d = new THREE.Vector3(); this.camera.getWorldDirection(d);
      this.free.yaw = Math.atan2(d.x, -d.z); this.free.pitch = Math.asin(THREE.MathUtils.clamp(d.y, -1, 1));
    }
    if (v === 'chase') this._chaseInit = false;
    this.view = v;
  }

  toggleFullscreen() { if (!document.fullscreenElement) document.documentElement.requestFullscreen?.(); else document.exitFullscreen?.(); }

  manualControl(dt) {
    const k = this.keys, u = this.usv;
    const freeView = this.view === 'free';
    const up = k.has('ArrowUp') || (!freeView && (k.has('KeyW') || k.has('KeyZ')));
    const down = k.has('ArrowDown') || (!freeView && k.has('KeyS'));
    const left = k.has('ArrowLeft') || (!freeView && (k.has('KeyA') || k.has('KeyQ')));
    const right = k.has('ArrowRight') || (!freeView && k.has('KeyD'));
    if (up || down || left || right) {
      if (u.mode !== 'manual') this.setManual(true);
      if (up) u.throttle = Math.min(1, u.throttle + dt * 0.5);
      if (down) u.throttle = Math.max(-0.4, u.throttle - dt * 0.5);
      if (left) u.rudder = Math.max(-1, u.rudder - dt * 3);
      if (right) u.rudder = Math.min(1, u.rudder + dt * 3);
    }
    if (u.mode === 'manual' && !left && !right && !this.pad.active) u.rudder *= Math.exp(-dt * 4);
    if (freeView) {
      const f = this.free, sp = k.has('ShiftLeft') ? 150 : 15;
      const fwd = new THREE.Vector3(Math.sin(f.yaw) * Math.cos(f.pitch), Math.sin(f.pitch), -Math.cos(f.yaw) * Math.cos(f.pitch));
      const right3 = new THREE.Vector3(Math.cos(f.yaw), 0, Math.sin(f.yaw));
      if (k.has('KeyW') || k.has('KeyZ')) f.pos.addScaledVector(fwd, sp * dt);
      if (k.has('KeyS')) f.pos.addScaledVector(fwd, -sp * dt);
      if (k.has('KeyA') || k.has('KeyQ')) f.pos.addScaledVector(right3, -sp * dt);
      if (k.has('KeyD')) f.pos.addScaledVector(right3, sp * dt);
      if (k.has('KeyE')) f.pos.y += sp * dt;
      if (k.has('KeyX')) f.pos.y -= sp * dt;
      f.pos.y = Math.max(f.pos.y, 0.6);
    }
  }

  autoDemo(dt) {
    if (!this.settings.autoDemo) return;
    const d = this.demo, u = this.usv;
    if (d.target) {
      d.since += dt;
      const dist = Math.hypot(d.target.pos.x - u.pos.x, d.target.pos.y - u.pos.y);
      if (!this.traffic.vessels.includes(d.target) || d.since > 240 || (dist < u.standoff + 40 && d.since > 60)) {
        d.done.add(d.target.id);
        d.target = null; u.target = null; u.mode = 'heading'; u.cmdHeading = u.heading; u.cmdSpeed = 2;
      }
      return;
    }
    // stand-in for a detector: a vessel visible in the image, closer than 2.5 km
    const cand = this.lastGT
      .filter((g) => g.distance < 2500 && !d.done.has(g.id) && g.bbox[2] - g.bbox[0] > 6)
      .sort((a, b) => a.distance - b.distance)[0];
    if (cand) {
      const v = this.traffic.vessels.find((q) => q.id === cand.id);
      if (v) {
        d.target = v; d.since = 0;
        this.hud.alert(`Navire détecté : ${v.spec.label}`, `${Math.round(cand.distance)} m · ${Math.round(cand.bearing)}°`, 5000);
        setTimeout(() => { if (d.target === v) this.approach(v); }, 1500);
      }
    }
  }

  horizontalFov() { return (2 * Math.atan(Math.tan((this.camera.fov * DEG) / 2) * this.camera.aspect)) / DEG; }
  cameraYaw() { const d = new THREE.Vector3(); this.camera.getWorldDirection(d); return Math.atan2(d.x, -d.z); }

  updateCamera(dt) {
    const cam = this.camera, u = this.usv;
    cam.fov = this.settings.fov;
    if (this.view === 'onboard') {
      u.group.updateMatrixWorld(true);
      const m = u.spec.mount.matrixWorld;
      const pos = new THREE.Vector3().setFromMatrixPosition(m);
      const q = new THREE.Quaternion().setFromRotationMatrix(m);
      // the mount looks along the boat's +x, a camera looks along its -z
      let qc = q.clone().multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(0, -Math.PI / 2, 0)));
      if (this.settings.stabilize) {
        const level = new THREE.Quaternion().setFromEuler(new THREE.Euler(0, -u.heading, 0, 'YXZ'));
        qc.slerp(level, 0.85);
      }
      qc.multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(this.gimbal.pitch, -this.gimbal.yaw, 0, 'YXZ')));
      // engine and hull vibration
      const vib = 0.0006 * (0.2 + Math.abs(u.throttle));
      qc.multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.sin(this.time * 61.3) * vib, Math.sin(this.time * 47.1) * vib * 0.6, Math.sin(this.time * 53.7) * vib * 0.5)));
      cam.position.copy(pos);
      cam.position.y = Math.max(cam.position.y, u.waterY + 0.07);
      cam.quaternion.copy(qc);
      cam.near = 0.02;
    } else if (this.view === 'chase') {
      const o = this.orbit;
      const yaw = u.heading + Math.PI + o.yaw;
      const target = new THREE.Vector3(u.pos.x, u.group.position.y + 0.25, u.pos.y);
      const want = target.clone().add(new THREE.Vector3(Math.sin(yaw) * Math.cos(o.pitch), Math.sin(o.pitch), -Math.cos(yaw) * Math.cos(o.pitch)).multiplyScalar(o.dist));
      want.y = Math.max(want.y, u.waterY + 0.5);
      if (!this._chaseInit) { cam.position.copy(want); this._chaseInit = true; }
      cam.position.lerp(want, 1 - Math.exp(-dt * 4));
      cam.lookAt(target);
      cam.near = 0.1;
    } else {
      const f = this.free;
      cam.position.copy(f.pos);
      cam.quaternion.setFromEuler(new THREE.Euler(f.pitch, -f.yaw, 0, 'YXZ'));
      cam.near = 0.1;
    }
    cam.updateProjectionMatrix();
    cam.updateMatrixWorld();
  }

  adaptResolution(dt) {
    // dynamic resolution: keep the simulator fluid on any machine (not while the AI chain gets fixed-size frames)
    if (params.get('dpr') || this.bridge.enabled) return;
    this._fpsAcc = (this._fpsAcc || 0) + dt;
    this._fpsN = (this._fpsN || 0) + 1;
    if (this._fpsAcc < 1.5) return;
    const fps = this._fpsN / this._fpsAcc;
    this._fpsAcc = 0; this._fpsN = 0;
    this.fps = fps;
    const old = this.scale;
    if (fps < 38) this.scale = Math.max(0.5, this.scale * (fps < 28 ? 0.8 : 0.92));
    else if (fps > 57 && this.scale < 1) this.scale = Math.min(1, this.scale * 1.08);
    if (Math.abs(old - this.scale) > 0.01) this.resize();
  }

  resize() {
    this.scale = this.scale ?? 1;
    const dpr = params.get('dpr') ? Math.min(devicePixelRatio, +params.get('dpr')) : Math.min(devicePixelRatio, 1.5) * this.scale;
    let w = Math.max(64, Math.floor(innerWidth * dpr)), h = Math.max(64, Math.floor(innerHeight * dpr));
    // with the AI chain connected the camera has a fixed sensor size (4:3 like the IMX500), letterboxed on screen
    const cam = (params.get('cam') || '2028x1520').split('x').map(Number); // IMX500 default mode in camera_pi.py
    let rect = { x: 0, y: 0, w: innerWidth, h: innerHeight };
    if (this.bridge.enabled) {
      [w, h] = cam;
      const k = Math.min(innerWidth / w, innerHeight / h);
      rect = { w: w * k, h: h * k, x: (innerWidth - w * k) / 2, y: (innerHeight - h * k) / 2 };
    }
    this.viewRect = rect;
    Object.assign(this.canvas.style, { left: rect.x + 'px', top: rect.y + 'px', width: rect.w + 'px', height: rect.h + 'px' });
    this.renderer.setPixelRatio(1);
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.fx.setSize(w, h);
    this.sky.resize(w, h);
    this.renderSize = { w, h };
  }

  shipShadows() {
    const u = this.ocean.uniforms;
    const cp = this.camera.position;
    const list = [this.usv, ...this.traffic.vessels]
      .map((v) => ({ v, d: Math.hypot(v.pos.x - cp.x, v.pos.y - cp.z) }))
      .filter((p) => p.d < 1500)
      .sort((a, b) => a.d - b.d)
      .slice(0, 8);
    list.forEach(({ v }, i) => {
      const f = v.forward;
      u.uShipShadow.value[i].set(v.pos.x, v.pos.y, (v.spec.air ?? 5) * 0.6);
      u.uShipShadowDir.value[i].set(f.x, f.y, v.L * 0.5, v.B * 0.5);
    });
    u.uShipShadowCount.value = list.length;
    // the catamaran drone has open water between its floats: no dry zone
    u.uDry.value.set(1e7, 1e7, 1, 0);
    u.uDryExt.value.set(1, 1);
  }

  frame(dt) {
    this.adaptResolution(dt);
    this.time += dt;
    this.simSeconds += dt;
    const s = this.settings;
    this.pollGamepad(dt);
    this.manualControl(dt);
    this.autoDemo(dt);
    this.fft.update(dt);
    const sea = this.ocean.uniforms.uSeaLevel.value;
    this.sampler.update(sea);
    this.usv.update(dt, this.terrain);
    for (const v of this.traffic.vessels) v.update(dt);
    this.traffic.update(dt, { x: this.usv.pos.x, z: this.usv.pos.y }, this.sunPos.elevation);
    this.usv.spec.lights.visible = this.sunPos.elevation < 2;
    this.updateCamera(dt);
    // full-screen map: the simulation goes on, the 3D view is not drawn (unless the AI chain needs frames)
    if (this.map?.open) {
      this.map.draw(dt);
      if (this.bridge.status !== 'connected') return;
    }
    this.terrain.update(this.camera, sea);

    const emit = [];
    this.usv.wakeEmitters(emit);
    for (const v of this.traffic.vessels) v.wakeEmitters(emit);
    this.wake.update(dt, this.time, this.camera.position, emit);
    const ou = this.ocean.uniforms;
    ou.uWake.value = this.wake.texture;
    ou.uWakeRect.value.copy(this.wake.rect);
    this.shipShadows();
    this.ocean.update(this.camera, this.time);

    const windTo = (s.windDir + 180) * DEG;
    const env = this.sky.update(dt, this.camera, { cloudWind: new THREE.Vector2(Math.sin(windTo), -Math.cos(windTo)).multiplyScalar(s.wind * 0.0012) });
    if (env) this.scene.environment = env;
    const su = this.sky.uniforms.uSunDir.value;
    this.sunLight.position.copy(this.camera.position).addScaledVector(su, 800);
    this.sunLight.target.position.copy(this.camera.position);
    const overcast = THREE.MathUtils.smoothstep(s.clouds, 0.72, 1.0) * 0.85;
    const sc = this.sky.sunColor;
    this.sunLight.color.setRGB(sc.x, sc.y, sc.z).multiplyScalar(1 - overcast);
    this.sunLight.intensity = su.y > -0.03 ? 1 : 0;

    // drops on the camera dome
    this.drops.update(dt, this.view === 'onboard' ? this.usv.splash : 0, s.wind, s.drops && this.view === 'onboard', s.rain);
    const lum = Math.max(this.fx.avgLum, 0.02);
    const windTo2 = (s.windDir + 180) * DEG;
    this.rain.update(dt, this.camera, s.rain, windTo2, s.wind, new THREE.Vector3(lum, lum * 1.02, lum * 1.05), this.renderSize.h);
    const fu = this.fx.finalMat.uniforms;
    fu.uDropCount.value = this.drops.fill(fu.uDrops.value, this.renderSize.w / this.renderSize.h);
    fu.uWash.value = this.drops.wash;
    // rain on the dome and condensation (buée) only exist for the onboard camera
    const onboard = this.view === 'onboard';
    fu.uRainLens.value = onboard && s.drops ? s.rain : 0;
    fu.uFog.value = onboard ? s.fog : 0;

    const r = this.renderer;
    // ship shadows only matter close to the camera: refresh them every other frame
    r.shadowMap.needsUpdate = (this._shadowTick = (this._shadowTick || 0) + 1) % 2 === 0;
    r.setRenderTarget(this.fx.target);
    r.clear();
    r.render(this.scene, this.camera);
    this.fx.render(dt, this.time);

    const { w, h } = this.renderSize;
    this.lastGT = computeGroundTruth(this.camera, this.traffic.vessels, this.terrain, w, h, sea);
    if (this.detT && performance.now() - this.detT > 1500) this.detections = [];
    this.hud.drawOverlay(this.lastGT, this.detections);
    this.hud.update(dt);
    if (this.wantShot) {
      this.wantShot = false;
      const a = document.createElement('a');
      a.download = `iroise-${Date.now()}.png`;
      a.href = this.canvas.toDataURL('image/png');
      a.click();
    }
    // la chaîne ne reçoit que l'image de la caméra embarquée : en vue poursuite ou libre, elle verrait le drone lui-même
    if (this.view === 'onboard') this.bridge.maybeSend(this.canvas, performance.now(), () => this.frameMeta());
  }

  frameMeta() {
    const { w, h } = this.renderSize;
    const cam = this.camera, u = this.usv;
    const f = h / 2 / Math.tan((cam.fov * DEG) / 2);
    const ll = this.toLatLon(u.pos.x, u.pos.y);
    const q = cam.quaternion;
    const gt = this.lastGT.map((g) => {
      const [x0, y0] = this.hud.distortPoint(g.bbox[0], g.bbox[1], w, h);
      const [x1, y1] = this.hud.distortPoint(g.bbox[2], g.bbox[3], w, h);
      const v = this.traffic.vessels.find((t) => t.id === g.id);
      const tl = v ? this.toLatLon(v.pos.x, v.pos.y) : null;
      return { ...g, bbox: [x0, y0, x1, y1], lat: tl?.lat, lon: tl?.lon, cog_deg: v ? (v.heading / DEG + 360) % 360 : null, sog_mps: v?.speed };
    });
    return {
      type: 'frame', t: this.simSeconds, width: w, height: h,
      intrinsics: { fx: f, fy: f, cx: w / 2, cy: h / 2, radial_k: this.fx.finalMat.uniforms.uDistort.value },
      camera: { position: cam.position.toArray(), quaternion: [q.x, q.y, q.z, q.w], fov_deg: cam.fov, view: this.view },
      own: { lat: ll.lat, lon: ll.lon, x: u.pos.x, z: u.pos.y, heading_deg: (u.heading / DEG + 360) % 360, sog_mps: u.u, mode: u.mode },
      ground_truth: gt,
      ais: this.traffic.vessels.map((v) => {
        const l = this.toLatLon(v.pos.x, v.pos.y);
        return { id: v.id, mmsi: v.mmsi, name: v.spec.name, type: v.spec.type, lat: l.lat, lon: l.lon, cog_deg: (v.heading / DEG + 360) % 360, sog_mps: v.speed, length_m: v.L };
      }),
      env: { sun_elevation_deg: this.sunPos.elevation, wind_mps: this.settings.wind, wind_from_deg: this.settings.windDir, hs_m: this.seaHs, clouds: this.settings.clouds, haze: this.settings.haze, rain: this.settings.rain, lens_fog: this.settings.fog },
    };
  }
}

// --------------------------------------------------------------------- boot
const loading = document.createElement('div');
loading.id = 'loading';
loading.innerHTML = '<div style="text-align:center"><div class="t">Iroise</div><div class="s">Préparation de la scène</div><div class="bar"><i></i></div></div>';
document.body.appendChild(loading);
const progress = (p, label) => { loading.querySelector('i').style.width = `${p * 100}%`; loading.querySelector('.s').textContent = label; };

const app = new App();
window.__sim = app;
app.init(progress).then(() => {
  const timer = new THREE.Timer();
  timer.connect(document);
  let first = true;
  const loop = () => {
    timer.update();
    const dt = Math.min(timer.getDelta(), 0.05);
    app.frame(first ? 0.016 : dt);
    if (first) { first = false; setTimeout(() => loading.classList.add('done'), 700); }
    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
});
