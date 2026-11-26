// Heads-up display: telemetry, camera switch, targets, chart, settings,
// ground-truth boxes. Small type, glass panels, one accent colour.
import { drawImagery, drawLabels } from './MapView.js';

const ICONS = {
  eye: '<svg viewBox="0 0 24 24"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>',
  box: '<svg viewBox="0 0 24 24"><path d="M4 8V4h4M16 4h4v4M20 16v4h-4M8 20H4v-4"/></svg>',
  sliders: '<svg viewBox="0 0 24 24"><path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/></svg>',
  link: '<svg viewBox="0 0 24 24"><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/></svg>',
  full: '<svg viewBox="0 0 24 24"><path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5"/></svg>',
  map: '<svg viewBox="0 0 24 24"><path d="M9 4L3 6.5v13.5l6-2.5 6 2.5 6-2.5V4l-6 2.5L9 4z"/><path d="M9 4v13.5M15 6.5V20"/></svg>',
};

const fmt = (v, d = 1) => (Number.isFinite(v) ? v.toFixed(d) : '–');
const pad = (n) => String(n).padStart(2, '0');

function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
}

export class HUD {
  constructor(app) {
    this.app = app;
    this.root = document.getElementById('ui');
    this.overlay = document.createElement('canvas');
    this.overlay.id = 'overlay';
    document.body.insertBefore(this.overlay, this.root);
    this.octx = this.overlay.getContext('2d');
    this.showGT = false;
    this.selected = null;
    this._t = 0;
    this.build();
  }

  build() {
    const a = this.app;
    const R = this.root;
    // brand
    const brand = el('div', 'hud glass brand', `<span class="dot"></span><div><div class="title">Iroise</div><div class="sub">Goulet de Brest · drone USV-IA</div></div><div class="rec"><i></i><span id="clock">00:00:00</span></div>`);
    R.appendChild(brand);
    // view switch
    const views = el('div', 'hud glass views');
    [['onboard', 'Caméra', '1'], ['chase', 'Poursuite', '2'], ['free', 'Libre', '3']].forEach(([k, label, key]) => {
      const b = el('button', '', `${label}<kbd>${key}</kbd>`);
      b.dataset.view = k;
      b.onclick = () => a.setView(k);
      views.appendChild(b);
    });
    R.appendChild(views);
    this.viewsEl = views;
    // icons
    const icons = el('div', 'hud icons');
    const mk = (name, title, fn) => { const b = el('button', 'icon-btn glass', ICONS[name]); b.title = title; b.onclick = fn; icons.appendChild(b); return b; };
    this.mapBtn = mk('map', 'Carte : se téléporter, ajouter des navires (C)', () => a.map.toggle(true));
    this.gtBtn = mk('box', 'Boîtes vérité terrain (B)', () => this.toggleGT());
    this.bridgeBtn = mk('link', 'Pont pipeline ws://127.0.0.1:8765', () => { a.bridge.enable(!a.bridge.enabled); });
    this.setBtn = mk('sliders', 'Réglages', () => this.toggleDrawer());
    mk('full', 'Plein écran (F)', () => a.toggleFullscreen());
    mk('eye', 'Masquer l’interface (H)', () => this.toggleHidden());
    R.appendChild(icons);
    // telemetry
    const tel = el('div', 'hud glass telemetry');
    tel.innerHTML = `
      <div><div class="k">Cap</div><div class="v" id="t-hdg">–</div></div>
      <div><div class="k">Vitesse</div><div class="v" id="t-sog">–</div></div>
      <div><div class="k">Mer</div><div class="v" id="t-sea">–</div></div>
      <div><div class="k">Latitude</div><div class="v" id="t-lat">–</div></div>
      <div><div class="k">Longitude</div><div class="v" id="t-lon">–</div></div>
      <div><div class="k">Vent</div><div class="v" id="t-wind">–</div></div>
      <div class="mode"><span>Pilote</span><b id="t-mode">manuel</b><div class="bar"><i id="t-rud"></i></div><span id="t-thr" style="font-family:var(--mono)">0 %</span></div>
      <div class="takeover"><button class="take" id="t-take">Prendre la main</button><span class="hint" id="t-hint">M · manette</span></div>`;
    R.appendChild(tel);
    tel.querySelector('#t-take').onclick = () => a.setManual(a.usv.mode !== 'manual');
    // minimap
    const mm = el('div', 'hud glass minimap', '<canvas width="480" height="480"></canvas><div class="north">N</div><div class="scale">2 km</div><div class="open">Ouvrir la carte · C</div>');
    R.appendChild(mm);
    this.mm = mm.querySelector('canvas');
    this.mmScale = mm.querySelector('.scale');
    this.mmRange = 4000;
    mm.addEventListener('click', () => a.map.toggle(true));
    mm.addEventListener('wheel', (e) => { e.preventDefault(); this.mmRange = Math.min(24000, Math.max(800, this.mmRange * (e.deltaY > 0 ? 1.15 : 0.87))); }, { passive: false });
    // targets
    this.targetsEl = el('div', 'hud glass targets');
    R.appendChild(this.targetsEl);
    // alert
    this.alertEl = el('div', 'hud glass alert', '<i></i><span></span><small></small>');
    R.appendChild(this.alertEl);
    // settings drawer
    this.drawer = el('div', 'hud glass drawer');
    R.appendChild(this.drawer);
    this.buildDrawer();
  }

  buildDrawer() {
    const a = this.app, s = a.settings;
    const d = this.drawer;
    d.innerHTML = '<h3>Réglages</h3>';
    const sec = (t) => d.appendChild(el('div', 'sec', t));
    const slider = (label, key, min, max, step, fmtFn, onInput) => {
      const r = el('div', 'row');
      r.innerHTML = `<label>${label}</label><output></output><input type="range" min="${min}" max="${max}" step="${step}" value="${s[key]}">`;
      const inp = r.querySelector('input'), out = r.querySelector('output');
      out.textContent = fmtFn(s[key]);
      inp.oninput = () => { s[key] = +inp.value; out.textContent = fmtFn(s[key]); onInput && onInput(s[key]); };
      d.appendChild(r);
      return { inp, out, set: (v) => { inp.value = v; out.textContent = fmtFn(v); } };
    };
    const toggle = (label, key, fn) => {
      const r = el('div', 'row');
      r.innerHTML = `<label>${label}</label>`;
      const t = el('button', 'toggle' + (s[key] ? ' on' : ''));
      t.onclick = () => { s[key] = !s[key]; t.classList.toggle('on', s[key]); fn && fn(s[key]); };
      r.appendChild(t);
      d.appendChild(r);
    };
    sec('Météo');
    const chips = el('div', 'chips');
    Object.keys(a.weatherPresets).forEach((name) => {
      const c = el('button', 'chip' + (s.weather === name ? ' on' : ''), name);
      c.onclick = () => { a.applyWeather(name); chips.querySelectorAll('.chip').forEach((x) => x.classList.toggle('on', x === c)); this.syncSliders(); };
      chips.appendChild(c);
    });
    d.appendChild(chips);
    this.sl = {};
    this.sl.hour = slider('Heure', 'hour', 4, 23, 0.05, (v) => `${pad(Math.floor(v))}h${pad(Math.floor((v % 1) * 60))}`, () => a.updateSun());
    this.sl.month = slider('Mois', 'month', 1, 12, 1, (v) => ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'][v - 1], () => a.updateSun());
    this.sl.wind = slider('Vent', 'wind', 1, 22, 0.5, (v) => `${fmt(v * 1.944, 0)} nd`, () => a.applySea());
    this.sl.windDir = slider('Vent de', 'windDir', 0, 359, 1, (v) => `${Math.round(v)}°`, () => a.applySea());
    this.sl.swell = slider('Houle', 'swell', 0, 3, 0.05, (v) => `${fmt(v, 1)} m`, () => a.applySea());
    this.sl.clouds = slider('Nuages', 'clouds', 0, 1, 0.01, (v) => `${Math.round(v * 100)} %`, () => a.applyAtmosphere());
    this.sl.haze = slider('Brume', 'haze', 0, 1, 0.01, (v) => `${Math.round(v * 100)} %`, () => a.applyAtmosphere());
    this.sl.rain = slider('Pluie', 'rain', 0, 1, 0.01, (v) => (v < 0.02 ? 'aucune' : v < 0.35 ? 'faible' : v < 0.75 ? 'modérée' : 'forte'), () => a.applyAtmosphere());
    this.sl.fog = slider('Buée sur l’objectif', 'fog', 0, 1, 0.01, (v) => (v < 0.02 ? 'aucune' : `${Math.round(v * 100)} %`));
    this.sl.tide = slider('Marée', 'tide', -3, 3, 0.1, (v) => `${v > 0 ? '+' : ''}${fmt(v, 1)} m`, () => a.applyTide());
    sec('Trafic et caméra');
    slider('Densité du trafic', 'traffic', 0, 1, 0.05, (v) => `${Math.round(v * 100)} %`, (v) => { a.traffic.density = v; });
    slider('Champ de vision', 'fov', 30, 100, 1, (v) => `${v}°`, () => a.applyCamera());
    slider('Exposition', 'ev', -2, 2, 0.1, (v) => `${v > 0 ? '+' : ''}${fmt(v, 1)} EV`, () => a.applyCamera());
    toggle('Stabilisation de la caméra', 'stabilize');
    toggle('Grain et défauts d’optique', 'lens', () => a.applyCamera());
    toggle('Gouttes sur l’objectif', 'drops');
    toggle('Démo autonome (détection simulée)', 'autoDemo');
    sec('Pipeline');
    const info = el('div', 'hint', 'Le simulateur envoie les images de la caméra embarquée, la vérité terrain et l’AIS sur <kbd>ws://127.0.0.1:8765</kbd>, et reçoit les consignes de cap, de vitesse ou d’approche. Voir <kbd>bridge/README.md</kbd>.');
    d.appendChild(info);
    const keys = el('div', 'hint', '<kbd>M</kbd> prendre la main · <kbd>Z</kbd> <kbd>S</kbd> gaz · <kbd>Q</kbd> <kbd>D</kbd> cap · <kbd>Espace</kbd> stop · manette : stick gauche, <kbd>A</kbd> prendre/rendre la main · <kbd>C</kbd> carte (téléportation, navires) · <kbd>1</kbd> <kbd>2</kbd> <kbd>3</kbd> vues · glisser pour orienter la caméra · <kbd>B</kbd> boîtes · <kbd>H</kbd> interface · <kbd>P</kbd> capture');
    d.appendChild(keys);
    import('../ships/ShipFactory.js').then(({ modelInfo }) => {
      if (!modelInfo.length) return;
      const seen = new Set();
      const list = modelInfo.filter((m) => !seen.has(m.name) && seen.add(m.name)).map((m) => `${m.name} : ${m.author} (${m.licence})`).join('<br>');
      d.appendChild(el('div', 'sec', 'Modèles 3D'));
      d.appendChild(el('div', 'hint', `${list}<br>Détails : <kbd>public/models/ATTRIBUTION.md</kbd>`));
    });
  }

  syncSliders() { const s = this.app.settings; for (const k of Object.keys(this.sl)) this.sl[k].set(s[k]); }
  toggleDrawer() { this.drawer.classList.toggle('open'); this.targetsEl.style.display = this.drawer.classList.contains('open') ? 'none' : ''; this.setBtn.classList.toggle('on', this.drawer.classList.contains('open')); }
  toggleHidden() { this.root.classList.toggle('hidden'); }
  toggleGT() { this.showGT = !this.showGT; this.gtBtn.classList.toggle('on', this.showGT); }

  alert(text, sub = '', ms = 4000) {
    this.alertEl.querySelector('span').textContent = text;
    this.alertEl.querySelector('small').textContent = sub;
    this.alertEl.classList.add('show');
    clearTimeout(this._alertT);
    this._alertT = setTimeout(() => this.alertEl.classList.remove('show'), ms);
  }

  update(dt) {
    this._t += dt;
    if (this._t < 0.1) return;
    this._t = 0;
    const a = this.app, u = a.usv;
    this.viewsEl.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.view === a.view));
    const st = a.bridge.status;
    this.bridgeBtn.classList.toggle('on', st === 'connected');
    this.bridgeBtn.title = st === 'connected' ? `Chaîne IA connectée (${a.bridge.sent} images envoyées)` : st === 'connecting' ? 'Connexion à la chaîne IA…' : 'Brancher la chaîne IA (ws://127.0.0.1:8765)';
    const hdg = ((u.heading * 180) / Math.PI + 360) % 360;
    document.getElementById('t-hdg').innerHTML = `${fmt(hdg, 0).padStart(3, '0')}<small>°</small>`;
    document.getElementById('t-sog').innerHTML = `${fmt(Math.abs(u.u) * 1.944, 1)}<small>nd</small>`;
    const ll = a.toLatLon(u.pos.x, u.pos.y);
    const dm = (v, pos, neg) => { const s = v >= 0 ? pos : neg; v = Math.abs(v); const d = Math.floor(v); return `${d}°${fmt((v - d) * 60, 3)}′${s}`; };
    document.getElementById('t-lat').textContent = dm(ll.lat, 'N', 'S');
    document.getElementById('t-lon').textContent = dm(ll.lon, 'E', 'O');
    document.getElementById('t-sea').innerHTML = `${fmt(a.seaHs, 1)}<small>m Hs</small>`;
    document.getElementById('t-wind').innerHTML = `${fmt(a.settings.wind * 1.944, 0)}<small>nd ${Math.round(a.settings.windDir)}°</small>`;
    const modes = { manual: 'manuel', heading: 'cap', waypoint: 'point', mission: 'route', approach: 'approche', external: 'chaîne IA' };
    const manual = u.mode === 'manual';
    document.getElementById('t-mode').textContent = (u.grounded ? 'échoué · ' : '') + modes[u.mode];
    const take = document.getElementById('t-take');
    take.textContent = manual ? 'Rendre la main' : 'Prendre la main';
    take.classList.toggle('on', manual);
    document.getElementById('t-hint').textContent = a.pad.active || (navigator.getGamepads && [...navigator.getGamepads()].some((p) => p)) ? 'manette connectée' : 'M · Z Q S D';
    const rud = document.getElementById('t-rud');
    const rv = Math.max(-1, Math.min(1, u.rudder));
    rud.style.left = rv < 0 ? `${50 + rv * 50}%` : '50%';
    rud.style.width = `${Math.abs(rv) * 50}%`;
    document.getElementById('t-thr').textContent = `${Math.round(u.throttle * 100)} %`;
    const t = a.simClock();
    document.getElementById('clock').textContent = `${pad(t.h)}:${pad(t.m)}:${pad(t.s)}`;
    this.drawTargets();
    this.drawMap();
  }

  drawTargets() {
    const a = this.app;
    const list = a.traffic.vessels
      .map((v) => ({ v, d: Math.hypot(v.pos.x - a.usv.pos.x, v.pos.y - a.usv.pos.y) }))
      .sort((p, q) => p.d - q.d)
      .slice(0, 7);
    const seen = new Set((a.lastGT || []).map((g) => g.id));
    const html = list.map(({ v, d }) => {
      const brg = ((Math.atan2(v.pos.x - a.usv.pos.x, -(v.pos.y - a.usv.pos.y)) * 180) / Math.PI + 360) % 360;
      const sel = a.usv.target === v ? ' sel' : '';
      return `<div class="target${sel}" data-id="${v.id}"><div class="n">${v.spec.name}</div><div class="d">${d > 1852 ? fmt(d / 1852, 1) + ' nq' : Math.round(d) + ' m'}</div><div class="t">${v.spec.label}${seen.has(v.id) ? ' · <span class="seen">en vue</span>' : ''}</div><div class="b">${Math.round(brg).toString().padStart(3, '0')}° · ${fmt(v.speed * 1.944, 1)} nd</div></div>`;
    }).join('');
    this.targetsEl.innerHTML = `<h4><span>Cibles AIS</span><span>clic : approcher</span></h4>${html}`;
    this.targetsEl.querySelectorAll('.target').forEach((n) => {
      n.onclick = () => {
        const v = a.traffic.vessels.find((x) => x.id === +n.dataset.id);
        if (v) a.approach(v);
      };
    });
  }

  drawMap() {
    const a = this.app, c = this.mm, ctx = c.getContext('2d');
    const W = c.width, H = c.height;
    const range = this.mmRange; // metres across
    const ppm = W / range;
    const cx = a.usv.pos.x, cz = a.usv.pos.y;
    drawImagery(ctx, W, H, cx, cz, ppm, a.terrain);
    ctx.fillStyle = 'rgba(6,10,14,0.18)';
    ctx.fillRect(0, 0, W, H);
    // names at the minimap scale (canvas is 2x its CSS size)
    if (a.map?.labels) drawLabels(ctx, W, H, cx, cz, ppm, 2, a.map.labels, ppm / 2 * 1.6, 0.82);
    const toPx = (x, z) => [(x - cx) * ppm + W / 2, (z - cz) * ppm + H / 2];
    // camera field of view
    const camYaw = a.cameraYaw();
    const half = (a.horizontalFov() * Math.PI) / 360;
    const R = W * 0.7;
    const grad = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, R);
    grad.addColorStop(0, 'rgba(216,181,99,0.3)');
    grad.addColorStop(1, 'rgba(216,181,99,0)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.moveTo(W / 2, H / 2);
    for (let i = 0; i <= 12; i++) {
      const ang = camYaw - half + (2 * half * i) / 12;
      ctx.lineTo(W / 2 + Math.sin(ang) * R, H / 2 - Math.cos(ang) * R);
    }
    ctx.closePath();
    ctx.fill();
    for (const v of a.traffic.vessels) {
      const [x, y] = toPx(v.pos.x, v.pos.y);
      if (x < -20 || y < -20 || x > W + 20 || y > H + 20) continue;
      const s = Math.max(5, Math.min(14, v.L * ppm * 0.6 + 4));
      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(v.heading);
      ctx.fillStyle = a.usv.target === v || v.role === 'user' ? '#d8b563' : 'rgba(244,242,236,0.95)';
      ctx.strokeStyle = 'rgba(8,10,12,0.7)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(0, -s); ctx.lineTo(s * 0.55, s * 0.75); ctx.lineTo(-s * 0.55, s * 0.75); ctx.closePath();
      ctx.fill(); ctx.stroke();
      ctx.restore();
    }
    // own ship
    ctx.save();
    ctx.translate(W / 2, H / 2);
    ctx.rotate(a.usv.heading);
    ctx.fillStyle = '#f06a1d';
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(0, -12); ctx.lineTo(8, 10); ctx.lineTo(0, 5); ctx.lineTo(-8, 10); ctx.closePath();
    ctx.fill(); ctx.stroke();
    ctx.restore();
    const km = range / 2 / 1000;
    this.mmScale.textContent = `${km >= 1 ? fmt(km, km < 3 ? 1 : 0) + ' km' : Math.round(km * 1000) + ' m'}`;
  }

  /** maps a point of the undistorted render to the displayed (distorted) image */
  distortPoint(x, y, w, h) {
    const k = this.app.fx.finalMat.uniforms.uDistort.value;
    const aspect = w / h;
    const sx = x / w - 0.5, sy = y / h - 0.5;
    let ox = sx, oy = sy;
    for (let i = 0; i < 4; i++) {
      const r2 = (ox * aspect) ** 2 + oy ** 2;
      const f = (1 + k * r2) / (1 + k * 0.25);
      ox = sx / f; oy = sy / f;
    }
    return [(ox + 0.5) * w, (oy + 0.5) * h];
  }

  drawOverlay(gt, detections) {
    const c = this.overlay, ctx = this.octx;
    const W = innerWidth, H = innerHeight, dpr = Math.min(devicePixelRatio, 2);
    if (c.width !== Math.round(W * dpr) || c.height !== Math.round(H * dpr)) { c.width = Math.round(W * dpr); c.height = Math.round(H * dpr); }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    // draw in the displayed image rectangle (letterboxed when the camera has a fixed size)
    const vr = this.app.viewRect || { x: 0, y: 0, w: W, h: H };
    ctx.setTransform(dpr, 0, 0, dpr, vr.x * dpr, vr.y * dpr);
    const w = vr.w, h = vr.h;
    const draw = (b, color, label, dash) => {
      const [x0, y0] = this.distortPoint(b[0], b[1], w, h), [x1, y1] = this.distortPoint(b[2], b[3], w, h);
      ctx.strokeStyle = color; ctx.lineWidth = 1.2; ctx.setLineDash(dash || []);
      ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);
      ctx.setLineDash([]);
      if (label) {
        ctx.font = '11px ui-monospace, Menlo, monospace';
        const tw = ctx.measureText(label).width + 10;
        ctx.fillStyle = 'rgba(14,15,17,0.62)';
        ctx.fillRect(x0, y0 - 18, tw, 16);
        ctx.fillStyle = color;
        ctx.fillText(label, x0 + 5, y0 - 6);
      }
    };
    if (this.showGT && gt) {
      const sx = w / this.app.renderSize.w, sy = h / this.app.renderSize.h;
      for (const g of gt) {
        const b = [g.bbox[0] * sx, g.bbox[1] * sy, g.bbox[2] * sx, g.bbox[3] * sy];
        draw(b, 'rgba(216,181,99,0.95)', `VT · ${g.label} · ${g.distance > 1852 ? (g.distance / 1852).toFixed(1) + ' nq' : Math.round(g.distance) + ' m'}`);
      }
    }
    // legend: what the simulator knows vs what the AI chain sees
    const showDet = detections && detections.length;
    if ((this.showGT && gt) || showDet || this.app.bridge.status === 'connected') {
      const items = [];
      if (this.showGT) items.push(['rgba(216,181,99,0.95)', 'Vérité terrain (le simulateur sait où sont les navires)']);
      if (this.app.bridge.status === 'connected') items.push(['rgba(120,200,255,0.95)', 'Chaîne IA (ce que voit votre détection)']);
      ctx.font = '11px -apple-system, Inter, sans-serif';
      const wTot = items.reduce((a, [, t]) => a + ctx.measureText(t).width + 30, 0);
      let x = w / 2 - wTot / 2;
      const y = h - 18;
      for (const [c, t] of items) {
        ctx.fillStyle = 'rgba(14,15,17,0.55)';
        ctx.fillRect(x - 6, y - 13, ctx.measureText(t).width + 26, 19);
        ctx.fillStyle = c; ctx.fillRect(x, y - 7, 8, 8);
        ctx.fillStyle = 'rgba(235,232,225,0.92)'; ctx.fillText(t, x + 14, y);
        x += ctx.measureText(t).width + 30;
      }
    }
    if (detections && detections.length) {
      const sx = w / this.app.renderSize.w, sy = h / this.app.renderSize.h;
      for (const d of detections) {
        const b = d.bbox_display ? d.bbox : [d.bbox[0] * sx, d.bbox[1] * sy, d.bbox[2] * sx, d.bbox[3] * sy];
        const [x0, y0] = [b[0], b[1]], [x1, y1] = [b[2], b[3]];
        ctx.strokeStyle = 'rgba(120,200,255,0.95)'; ctx.lineWidth = 1.5;
        ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);
        if (d.label) { ctx.fillStyle = 'rgba(120,200,255,0.95)'; ctx.font = '11px ui-monospace, Menlo, monospace'; ctx.fillText(`${d.label} ${d.score ? Math.round(d.score * 100) + '%' : ''}`, x0 + 2, y1 + 13); }
      }
    }
  }
}
