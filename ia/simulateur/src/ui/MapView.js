// Carte : orthophoto IGN (vue satellite) avec les noms de lieux, le drone, les navires.
// On y téléporte le drone, on y pose des navires (cap, vitesse, route) et on les retire.
// La même fonction de dessin sert à la mini-carte du HUD.

const DEG = Math.PI / 180;
const KN = 1.944;

export const KIND_LABELS = {
  trawler: 'Chalutier', sailboat: 'Voilier', motorboat: 'Vedette', tug: 'Remorqueur',
  ferry: 'Passagers', container: 'Porte-conteneurs', bulk: 'Vraquier', frigate: 'Frégate',
};
const KIND_SPEED = { trawler: 7, sailboat: 5, motorboat: 14, tug: 9, ferry: 13, container: 12, bulk: 11, frigate: 14 };
const KIND_DEPTH = { trawler: 3, sailboat: 2, motorboat: 1.5, tug: 4, ferry: 5, container: 10, bulk: 10, frigate: 7 };

const FONT = '-apple-system, BlinkMacSystemFont, "Inter", "Helvetica Neue", sans-serif';
const STYLE = {
  city: { size: 16, weight: 600, color: '#ffffff', track: 0.4 },
  town: { size: 13, weight: 600, color: '#f4f2ec', track: 0.2 },
  locality: { size: 12, weight: 500, color: '#f4f2ec', track: 0.1 },
  point: { size: 11, weight: 500, color: '#efede6', dot: '#efede6' },
  landmark: { size: 11, weight: 500, color: '#efede6', dot: '#efede6' },
  beach: { size: 11, weight: 500, color: '#f2e3bf', dot: '#f2e3bf' },
  port: { size: 11, weight: 500, color: '#cfe7f3', dot: '#cfe7f3' },
  water: { size: 13, weight: 400, color: '#c4e2f1', italic: true, track: 1.2 },
  home: { size: 12, weight: 600, color: '#e9d08f', dot: '#d8b563' },
};
// zoom (CSS px per metre) from which each rank of names shows
const RANK_PPM = { 1: 0, 2: 0.07, 3: 0.17 };

const fmt = (v, d = 1) => (Number.isFinite(v) ? v.toFixed(d) : '–');
const dm = (v, pos, neg) => { const s = v >= 0 ? pos : neg; v = Math.abs(v); const d = Math.floor(v); return `${d}°${((v - d) * 60).toFixed(2).replace('.', ',')}′${s}`; };
const norm = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
}

// ---------------------------------------------------------------- drawing helpers (map + minimap)

/** satellite imagery: far orthophoto (8 m) everywhere, near one (2.5 m) on top when zoomed in */
export function drawImagery(ctx, W, H, cx, cz, ppm, terrain, fast = false) {
  ctx.fillStyle = '#0d1a23';
  ctx.fillRect(0, 0, W, H);
  if (!terrain?.ortho) return;
  const x0 = cx - W / 2 / ppm, z0 = cz - H / 2 / ppm;
  const layers = [terrain.ortho.far];
  if (ppm > 0.1) layers.push(terrain.ortho.near);
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = fast ? 'low' : ppm > 0.5 ? 'medium' : 'high';
  for (const L of layers) {
    const r = L.rect, img = L.img;
    if (!img || !img.width) continue;
    const wx0 = Math.max(x0, r.x), wz0 = Math.max(z0, r.y);
    const wx1 = Math.min(x0 + W / ppm, r.x + r.z), wz1 = Math.min(z0 + H / ppm, r.y + r.w);
    if (wx1 <= wx0 || wz1 <= wz0) continue;
    const sx = ((wx0 - r.x) / r.z) * img.width, sy = ((wz0 - r.y) / r.w) * img.height;
    const sw = ((wx1 - wx0) / r.z) * img.width, sh = ((wz1 - wz0) / r.w) * img.height;
    ctx.drawImage(img, sx, sy, sw, sh, (wx0 - x0) * ppm, (wz0 - z0) * ppm, (wx1 - wx0) * ppm, (wz1 - wz0) * ppm);
  }
}

/** place names, highest rank first, without overlaps */
export function drawLabels(ctx, W, H, cx, cz, ppm, dpr, labels, cssPpm, scale = 1) {
  const placed = [];
  const hit = (r) => placed.some((p) => r.x < p.x + p.w && r.x + r.w > p.x && r.y < p.y + p.h && r.y + r.h > p.y);
  ctx.textBaseline = 'middle';
  ctx.lineJoin = 'round';
  for (const l of labels) {
    if (cssPpm < RANK_PPM[l.rank] / scale) continue;
    const st = STYLE[l.home ? 'home' : l.cls] || STYLE.point;
    const x = (l.x - cx) * ppm + W / 2, y = (l.z - cz) * ppm + H / 2;
    if (x < -200 || y < -50 || x > W + 200 || y > H + 50) continue;
    const size = (l.cls === 'water' && l.rank === 1 ? 15 : st.size) * dpr * scale;
    ctx.font = `${st.italic ? 'italic ' : ''}${st.weight} ${size}px ${FONT}`;
    ctx.letterSpacing = `${(st.track || 0) * dpr * scale}px`;
    const tw = ctx.measureText(l.name).width;
    const dot = st.dot ? 3 * dpr * scale : 0;
    const angle = (l.angle || 0) * DEG;
    // a rotated label is tested with its axis-aligned bounds
    const bw = Math.abs(Math.cos(angle)) * tw + Math.abs(Math.sin(angle)) * size;
    const bh = Math.abs(Math.sin(angle)) * tw + Math.abs(Math.cos(angle)) * size;
    const pad = 4 * dpr * scale;
    const rect = dot ? { x: x - dot - pad, y: y - size / 2 - pad, w: tw + dot * 3 + pad * 2, h: size + pad * 2 }
      : { x: x - bw / 2 - pad, y: y - bh / 2 - pad, w: bw + pad * 2, h: bh + pad * 2 };
    if (hit(rect)) continue;
    placed.push(rect);
    ctx.save();
    ctx.translate(x, y);
    if (dot) {
      ctx.fillStyle = 'rgba(8,12,16,0.65)';
      ctx.beginPath(); ctx.arc(0, 0, dot + 1.2 * dpr * scale, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = st.dot;
      ctx.beginPath(); ctx.arc(0, 0, dot, 0, Math.PI * 2); ctx.fill();
      ctx.translate(dot * 2.2, 0);
      ctx.textAlign = 'left';
    } else {
      ctx.rotate(-angle);
      ctx.textAlign = 'center';
    }
    ctx.strokeStyle = l.cls === 'water' ? 'rgba(6,20,30,0.55)' : 'rgba(8,10,12,0.7)';
    ctx.lineWidth = (l.cls === 'water' ? 2.5 : 3.2) * dpr * scale;
    ctx.strokeText(l.name, 0, 0);
    ctx.fillStyle = st.color;
    ctx.fillText(l.name, 0, 0);
    ctx.restore();
  }
  ctx.letterSpacing = '0px';
}

// ---------------------------------------------------------------- map view

export class MapView {
  constructor(app) {
    this.app = app;
    this.open = false;
    this.view = { x: 0, z: 0, ppm: 0.05 };
    this.goal = { x: 0, z: 0, ppm: 0.05 };
    this.tool = 'explore';     // explore | teleport | ship | route
    this.kind = 'trawler';
    this.speedKn = KIND_SPEED.trawler;
    this.selected = null;
    this.labels = [];
    this.trail = [];
    this._trailT = 0;
    this.drag = null;
    this.hover = null;
    this.mouse = null;
    this.build();
    fetch('/data/labels.json').then((r) => (r.ok ? r.json() : null)).then((d) => {
      if (!d) return;
      const order = { city: 0, town: 1, locality: 2, water: 3, landmark: 4, port: 5, point: 6, beach: 7 };
      this.labels = d.labels
        .map((l) => ({ ...l, z: -l.n, home: /IMT Atlantique/.test(l.name) }))
        .sort((a, b) => a.rank - b.rank || (b.home ? 1 : 0) - (a.home ? 1 : 0) || order[a.cls] - order[b.cls]);
    }).catch(() => {});
  }

  // ------------------------------------------------------------ DOM
  build() {
    const root = (this.root = el('div', 'map'));
    root.innerHTML = `
      <canvas></canvas>
      <div class="map-bar">
        <div class="glass map-title"><span class="dot"></span><div><div class="t">Carte</div><div class="s">Orthophoto IGN · rade de Brest</div></div></div>
        <div class="glass seg">
          <button data-tool="explore">Explorer</button>
          <button data-tool="teleport">Téléporter le drone</button>
          <button data-tool="ship">Ajouter un navire</button>
        </div>
        <div class="map-right">
          <div class="glass search"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4 4"/></svg><input type="text" placeholder="Chercher un lieu" spellcheck="false"><div class="results"></div></div>
          <button class="icon-btn glass close" title="Fermer la carte (Échap)"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg></button>
        </div>
      </div>
      <div class="glass map-panel">
        <div class="h">Navire à poser</div>
        <div class="kinds"></div>
        <div class="row"><label>Vitesse</label><output></output><input type="range" min="0" max="20" step="0.5"></div>
        <p class="hint">Clique sur l’eau pour le poser. Garde le clic et glisse pour choisir son cap.</p>
        <div class="sep"></div>
        <div class="row"><label>Trafic automatique</label><button class="toggle on" data-k="auto"></button></div>
        <div class="links"><button data-k="clear-auto">Retirer le trafic automatique</button><button data-k="clear-user">Retirer mes navires</button></div>
      </div>
      <div class="glass map-card"></div>
      <div class="glass map-hint"></div>
      <div class="glass map-foot"><div class="scalebar"><i></i><span></span></div><div class="cursor"></div></div>
      <div class="glass map-zoom">
        <button data-z="in" title="Zoomer (+)"><svg viewBox="0 0 24 24"><path d="M12 6v12M6 12h12"/></svg></button>
        <button data-z="out" title="Dézoomer (−)"><svg viewBox="0 0 24 24"><path d="M6 12h12"/></svg></button>
        <button data-z="drone" title="Centrer sur le drone"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3"/></svg></button>
      </div>
      <div class="glass map-menu"></div>`;
    document.body.appendChild(root);
    this.canvas = root.querySelector('canvas');
    this.ctx = this.canvas.getContext('2d');
    this.panel = root.querySelector('.map-panel');
    this.card = root.querySelector('.map-card');
    this.hintEl = root.querySelector('.map-hint');
    this.menu = root.querySelector('.map-menu');
    this.cursorEl = root.querySelector('.cursor');
    this.scaleEl = root.querySelector('.scalebar');

    root.querySelectorAll('.seg button').forEach((b) => (b.onclick = () => this.setTool(b.dataset.tool)));
    root.querySelector('.close').onclick = () => this.toggle(false);
    root.querySelectorAll('.map-zoom button').forEach((b) => (b.onclick = () => {
      if (b.dataset.z === 'drone') this.flyTo(this.app.usv.pos.x, this.app.usv.pos.y, Math.max(this.goal.ppm, 0.12));
      else this.zoomAt(this.canvas.clientWidth / 2, this.canvas.clientHeight / 2, b.dataset.z === 'in' ? 1.8 : 1 / 1.8);
    }));

    // ship palette
    const kinds = this.panel.querySelector('.kinds');
    for (const k of Object.keys(KIND_LABELS)) {
      const c = el('button', 'chip', KIND_LABELS[k]);
      c.dataset.kind = k;
      c.onclick = () => { this.kind = k; this.setSpeed(KIND_SPEED[k]); this.syncPanel(); };
      kinds.appendChild(c);
    }
    const sp = this.panel.querySelector('input');
    sp.oninput = () => this.setSpeed(+sp.value);
    this.panel.querySelector('[data-k=auto]').onclick = (e) => {
      const t = this.app.traffic;
      t.auto = !t.auto;
      e.currentTarget.classList.toggle('on', t.auto);
      if (t.auto) t.populate({ x: this.app.usv.pos.x, z: this.app.usv.pos.y });
    };
    this.panel.querySelector('[data-k=clear-auto]').onclick = () => {
      const t = this.app.traffic;
      t.auto = false;
      this.panel.querySelector('[data-k=auto]').classList.remove('on');
      t.clearAuto();
      if (this.selected && !t.vessels.includes(this.selected)) this.select(null);
    };
    this.panel.querySelector('[data-k=clear-user]').onclick = () => {
      const t = this.app.traffic;
      for (const v of t.vessels.slice()) if (v.role === 'user') t.remove(v);
      if (this.selected && !t.vessels.includes(this.selected)) this.select(null);
    };
    this.setSpeed(this.speedKn);
    this.syncPanel();

    // search
    const input = root.querySelector('.search input');
    const results = root.querySelector('.results');
    const run = () => {
      const q = norm(input.value.trim());
      if (!q) { results.innerHTML = ''; results.classList.remove('open'); return; }
      const hits = this.labels.filter((l) => norm(l.name).includes(q)).slice(0, 7);
      results.innerHTML = hits.length ? hits.map((l, i) => `<div class="res" data-i="${i}"><span>${l.name}</span><small>${{ city: 'ville', town: 'commune', locality: 'lieu-dit', point: 'pointe', landmark: 'repère', beach: 'plage', port: 'port', water: 'plan d’eau' }[l.cls] || ''}</small><button title="Y emmener le drone">Y aller</button></div>`).join('') : '<div class="none">Aucun lieu trouvé</div>';
      results.classList.add('open');
      results.querySelectorAll('.res').forEach((r) => {
        const l = hits[+r.dataset.i];
        r.onclick = () => { this.flyTo(l.x, l.z, Math.max(this.goal.ppm, l.cls === 'city' || l.cls === 'town' ? 0.09 : 0.2)); this.flash = { x: l.x, z: l.z, t: 0 }; results.classList.remove('open'); input.blur(); };
        r.querySelector('button').onclick = (e) => { e.stopPropagation(); results.classList.remove('open'); input.blur(); this.teleportNear(l.x, l.z, l.name); };
      });
    };
    input.oninput = run;
    input.onkeydown = (e) => {
      e.stopPropagation();
      if (e.key === 'Enter') results.querySelector('.res')?.click();
      if (e.key === 'Escape') { input.value = ''; run(); input.blur(); }
    };
    input.onfocus = run;
    this.searchInput = input;

    // canvas interaction
    const cv = this.canvas;
    cv.addEventListener('pointerdown', (e) => this.onDown(e));
    cv.addEventListener('pointermove', (e) => this.onMove(e));
    cv.addEventListener('pointerup', (e) => this.onUp(e));
    cv.addEventListener('pointerleave', () => { this.mouse = null; this.hover = null; });
    cv.addEventListener('dblclick', (e) => { if (this.tool === 'route') { e.preventDefault(); this.setTool('explore'); } });
    cv.addEventListener('wheel', (e) => {
      e.preventDefault();
      const k = Math.exp(-e.deltaY * (e.ctrlKey ? 0.012 : 0.0022));
      this.zoomAt(e.offsetX, e.offsetY, k);
    }, { passive: false });
    cv.addEventListener('contextmenu', (e) => { e.preventDefault(); this.openMenu(e.offsetX, e.offsetY); });
    root.addEventListener('pointerdown', (e) => { if (!this.menu.contains(e.target)) this.menu.classList.remove('open'); if (!e.target.closest('.search')) results.classList.remove('open'); });
  }

  setSpeed(kn) {
    this.speedKn = kn;
    const sp = this.panel.querySelector('input');
    sp.value = kn;
    this.panel.querySelector('output').textContent = kn < 0.25 ? 'à l’arrêt' : `${fmt(kn, kn < 10 ? 1 : 0)} nd`;
  }

  syncPanel() {
    this.panel.querySelectorAll('.chip').forEach((c) => c.classList.toggle('on', c.dataset.kind === this.kind));
    this.panel.querySelector('[data-k=auto]').classList.toggle('on', this.app.traffic?.auto !== false);
  }

  setTool(t) {
    if (t === 'route' && !this.selected) t = 'explore';
    this.tool = t;
    this.root.querySelectorAll('.seg button').forEach((b) => b.classList.toggle('on', b.dataset.tool === t || (t === 'route' && b.dataset.tool === 'explore')));
    this.root.classList.toggle('tool-ship', t === 'ship');
    this.root.classList.toggle('crosshair', t !== 'explore');
    const hints = {
      explore: 'Glisser pour se déplacer · molette pour zoomer · clic sur un navire pour le choisir · clic droit pour les raccourcis',
      teleport: 'Clique sur l’eau pour y placer le drone · garde le clic et glisse pour choisir son cap',
      ship: '',
      route: 'Clique pour ajouter des points de route · double-clic ou Entrée pour finir · Échap pour annuler',
    };
    this.hintEl.textContent = hints[t];
    this.hintEl.classList.toggle('show', !!hints[t]);
    this.syncPanel();
    this.renderCard();
  }

  toggle(on = !this.open) {
    if (on === this.open) return;
    this.open = on;
    this.root.classList.toggle('open', on);
    if (on) {
      const u = this.app.usv;
      // open around the drone, wide enough to recognise the place
      if (!this._opened) { this.view.ppm = this.goal.ppm = 0.09; this._opened = true; }
      this.view.x = this.goal.x = u.pos.x; this.view.z = this.goal.z = u.pos.y;
      this.app.keys.clear();
      this.setTool(this.tool === 'route' ? 'explore' : this.tool);
      this.syncPanel();
    } else {
      this.menu.classList.remove('open');
      if (this.tool === 'route') this.setTool('explore');
    }
  }

  onKey(e) {
    if (e.code === 'Escape') {
      if (this.menu.classList.contains('open')) this.menu.classList.remove('open');
      else if (this.tool === 'route') { if (this.selected) this.selected.setRoute(this._routeBackup || []); this.setTool('explore'); }
      else if (this.tool !== 'explore') this.setTool('explore');
      else this.toggle(false);
      return true;
    }
    if (e.code === 'Enter' && this.tool === 'route') { this.setTool('explore'); return true; }
    if (e.key === '+' || e.key === '=') { this.zoomAt(this.canvas.clientWidth / 2, this.canvas.clientHeight / 2, 1.6); return true; }
    if (e.key === '-' || e.key === '_') { this.zoomAt(this.canvas.clientWidth / 2, this.canvas.clientHeight / 2, 1 / 1.6); return true; }
    if ((e.code === 'Delete' || e.code === 'Backspace') && this.selected) { this.removeSelected(); return true; }
    return false;
  }

  // ------------------------------------------------------------ coordinates
  toWorld(px, py, v = this.view) { const W = this.canvas.clientWidth, H = this.canvas.clientHeight; return { x: v.x + (px - W / 2) / v.ppm, z: v.z + (py - H / 2) / v.ppm }; }
  toScreen(x, z, v = this.view) { const W = this.canvas.clientWidth, H = this.canvas.clientHeight; return [(x - v.x) * v.ppm + W / 2, (z - v.z) * v.ppm + H / 2]; }

  clampGoal() {
    const r = this.app.terrain.far?.rect;
    const g = this.goal;
    g.ppm = Math.min(4, Math.max(0.028, g.ppm));
    if (r) { g.x = Math.min(r.x + r.z, Math.max(r.x, g.x)); g.z = Math.min(r.y + r.w, Math.max(r.y, g.z)); }
  }

  zoomAt(px, py, k) {
    // keep the point under the cursor fixed while zooming
    const before = this.toWorld(px, py, this.goal);
    this.goal.ppm *= k;
    this.clampGoal();
    const after = this.toWorld(px, py, this.goal);
    this.goal.x += before.x - after.x; this.goal.z += before.z - after.z;
    this.clampGoal();
  }

  flyTo(x, z, ppm) { this.goal.x = x; this.goal.z = z; if (ppm) this.goal.ppm = ppm; this.clampGoal(); }

  depthAt(x, z) { return this.app.terrain.ready ? -this.app.terrain.heightAt(x, z) : 50; }

  /** nearest point with at least `depth` m of water, searching outwards */
  nearestWater(x, z, depth = 0.6, maxR = 3000) {
    if (this.depthAt(x, z) >= depth) return { x, z, moved: 0 };
    for (let r = 10; r <= maxR; r += Math.max(10, r * 0.08)) {
      const n = Math.max(12, Math.floor((2 * Math.PI * r) / 12));
      let best = null;
      for (let i = 0; i < n; i++) {
        const a = (i / n) * Math.PI * 2;
        const q = { x: x + Math.cos(a) * r, z: z + Math.sin(a) * r };
        const d = this.depthAt(q.x, q.z);
        if (d >= depth && (!best || d > best.d)) best = { ...q, d };
      }
      if (best) return { x: best.x, z: best.z, moved: r };
    }
    return null;
  }

  nearestName(x, z) {
    let best = null, bd = Infinity;
    for (const l of this.labels) {
      if (l.cls === 'water' || l.cls === 'city') continue;
      const d = Math.hypot(l.x - x, l.z - z);
      if (d < bd) { bd = d; best = l; }
    }
    return best && bd < 2500 ? best : null;
  }

  // ------------------------------------------------------------ actions
  teleportNear(x, z, name) {
    const p = this.nearestWater(x, z, 0.8);
    if (!p) { this.app.hud.alert('Pas d’eau à proximité', 'choisis un point en mer', 2500); return; }
    this.teleport(p.x, p.z, null, name);
  }

  teleport(x, z, heading, name) {
    const p = this.nearestWater(x, z, 0.8);
    if (!p) { this.app.hud.alert('Pas d’eau à proximité', 'choisis un point en mer', 2500); return; }
    this.app.teleport(p.x, p.z, heading);
    const near = name ? this.labels.find((l) => l.name === name) : this.nearestName(p.x, p.z);
    const d = near ? Math.hypot(near.x - p.x, near.z - p.z) : 0;
    const where = near ? (d < 300 ? near.name : `${d > 1852 ? fmt(d / 1852, 1) + ' nq' : Math.round(d / 10) * 10 + ' m'} de ${near.name}`) : 'position choisie';
    this.app.hud.alert('Drone téléporté', `${where} · fond ${Math.round(this.depthAt(p.x, p.z))} m`, 3500);
    this.trail = [];
    this.flash = { x: p.x, z: p.z, t: 0 };
    // show the result: back to the camera after a short beat
    clearTimeout(this._closeT);
    this._closeT = setTimeout(() => this.toggle(false), 650);
  }

  addShip(x, z, heading) {
    const need = KIND_DEPTH[this.kind] || 3;
    const p = this.nearestWater(x, z, need, 1500);
    if (!p) { this.app.hud.alert('Pas assez d’eau ici', `un ${KIND_LABELS[this.kind].toLowerCase()} demande ${need} m de fond`, 3000); return; }
    const t = this.app.traffic;
    const v = t.addUser(this.kind, p.x, p.z, heading, this.speedKn / KN);
    if (p.moved > 20) this.app.hud.alert('Navire déplacé vers l’eau profonde', `${Math.round(p.moved)} m plus loin, ${need} m de fond au moins`, 3000);
    this.select(v);
  }

  removeSelected() {
    const v = this.selected;
    if (!v) return;
    if (this.app.usv.target === v) { this.app.usv.target = null; this.app.usv.mode = 'heading'; this.app.usv.cmdHeading = this.app.usv.heading; }
    this.app.traffic.remove(v);
    this.select(null);
  }

  select(v) {
    this.selected = v;
    if (!v && this.tool === 'route') this.setTool('explore');
    this.renderCard();
  }

  renderCard() {
    const v = this.selected;
    const c = this.card;
    if (!v || !this.app.traffic.vessels.includes(v)) { c.classList.remove('open'); this.selected = null; return; }
    const user = v.role === 'user';
    const kn = (user ? v.userSpeed : v.speed) * KN;
    c.innerHTML = `
      <div class="h"><div><div class="n">${v.spec.name}</div><div class="t">${v.spec.label} · ${Math.round(v.L)} m${user ? ' · ajouté par toi' : ' · trafic automatique'}</div></div><button class="x" title="Fermer"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg></button></div>
      <div class="stats"><div><span>Cap</span><b data-s="hdg"></b></div><div><span>Vitesse</span><b data-s="sog"></b></div><div><span>Distance</span><b data-s="dist"></b></div></div>
      ${user ? `<div class="row"><label>Vitesse demandée</label><output>${kn < 0.25 ? 'à l’arrêt' : fmt(kn, 1) + ' nd'}</output><input type="range" min="0" max="20" step="0.5" value="${kn}"></div>
      <div class="row"><label>Cap</label><output>${Math.round((v.heading / DEG + 360) % 360)}°</output><input type="range" data-k="hdg" min="0" max="359" step="1" value="${Math.round((v.heading / DEG + 360) % 360)}"></div>
      <div class="route">${v.route.length ? `Route de ${v.route.length} point${v.route.length > 1 ? 's' : ''}${v.loop ? ' en boucle' : ''}` : 'Cap constant, s’arrête avant la côte'}</div>
      <div class="acts">
        <button data-a="route" class="${this.tool === 'route' ? 'on' : ''}">${this.tool === 'route' ? 'Terminer la route' : v.route.length ? 'Ajouter des points' : 'Tracer une route'}</button>
        ${v.route.length ? `<button data-a="loop" class="${v.loop ? 'on' : ''}">Boucle</button><button data-a="clear">Effacer la route</button>` : ''}
      </div>` : ''}
      <div class="acts main">
        <button data-a="approach">Approcher avec le drone</button>
        <button data-a="delete" class="danger">Supprimer</button>
      </div>`;
    c.classList.add('open');
    c.querySelector('.x').onclick = () => this.select(null);
    const sp = c.querySelector('input:not([data-k])');
    if (sp) sp.oninput = () => { v.userSpeed = +sp.value / KN; sp.previousElementSibling.textContent = +sp.value < 0.25 ? 'à l’arrêt' : `${fmt(+sp.value, 1)} nd`; };
    const hd = c.querySelector('input[data-k=hdg]');
    if (hd) hd.oninput = () => {
      v.heading = +hd.value * DEG; v.turnRate = 0; v.prevStern = null;
      if (v.route.length) v.setRoute([]);
      hd.previousElementSibling.textContent = `${hd.value}°`;
    };
    c.querySelectorAll('[data-a]').forEach((b) => (b.onclick = () => {
      const a = b.dataset.a;
      if (a === 'route') {
        if (this.tool === 'route') this.setTool('explore');
        else { this._routeBackup = v.route.slice(); this.setTool('route'); }
      }
      if (a === 'loop') { v.loop = !v.loop; v.done = false; this.renderCard(); }
      if (a === 'clear') { v.setRoute([]); v.turnRate = 0; if (this.tool === 'route') this.setTool('explore'); else this.renderCard(); }
      if (a === 'approach') { this.app.approach(v); this.toggle(false); }
      if (a === 'delete') this.removeSelected();
    }));
    this.updateCardStats();
  }

  updateCardStats() {
    const v = this.selected;
    if (!v || !this.card.classList.contains('open')) return;
    const s = (k) => this.card.querySelector(`[data-s=${k}]`);
    const d = Math.hypot(v.pos.x - this.app.usv.pos.x, v.pos.y - this.app.usv.pos.y);
    s('hdg').textContent = `${String(Math.round((v.heading / DEG + 360) % 360)).padStart(3, '0')}°`;
    s('sog').textContent = `${fmt(v.speed * KN, 1)} nd${v.halted ? ' · stoppé' : ''}`;
    s('dist').textContent = d > 1852 ? `${fmt(d / 1852, 1)} nq` : `${Math.round(d)} m`;
  }

  openMenu(px, py) {
    const w = this.toWorld(px, py);
    const v = this.pickShip(px, py);
    const items = [];
    if (v) {
      this.select(v);
      items.push(['Approcher avec le drone', () => { this.app.approach(v); this.toggle(false); }]);
      items.push(['Supprimer ce navire', () => this.removeSelected()]);
    } else {
      items.push(['Téléporter le drone ici', () => this.teleport(w.x, w.z, null)]);
      items.push([`Poser un ${KIND_LABELS[this.kind].toLowerCase()} ici`, () => this.addShip(w.x, w.z, this.app.usv.heading + Math.PI / 2)]);
      items.push(['Centrer ici', () => this.flyTo(w.x, w.z)]);
    }
    this.menu.innerHTML = '';
    for (const [label, fn] of items) {
      const b = el('button', '', label);
      b.onclick = () => { this.menu.classList.remove('open'); fn(); };
      this.menu.appendChild(b);
    }
    const W = this.canvas.clientWidth, H = this.canvas.clientHeight;
    this.menu.style.left = `${Math.min(px, W - 230)}px`;
    this.menu.style.top = `${Math.min(py, H - 140)}px`;
    this.menu.classList.add('open');
  }

  // ------------------------------------------------------------ pointer
  pickShip(px, py) {
    let best = null, bd = Infinity;
    for (const v of this.app.traffic.vessels) {
      const [x, y] = this.toScreen(v.pos.x, v.pos.y);
      const d = Math.hypot(x - px, y - py);
      const r = Math.max(12, v.L * this.view.ppm * 0.55);
      if (d < r && d < bd) { bd = d; best = v; }
    }
    return best;
  }

  onDown(e) {
    if (e.button !== 0) return;
    this.canvas.setPointerCapture(e.pointerId);
    const w = this.toWorld(e.offsetX, e.offsetY);
    const d = { x0: e.offsetX, y0: e.offsetY, w0: w, moved: false, gx: this.goal.x, gz: this.goal.z };
    if (this.tool === 'explore') {
      const v = this.pickShip(e.offsetX, e.offsetY);
      if (v) { d.ship = v; d.off = { x: v.pos.x - w.x, z: v.pos.y - w.z }; this.select(v); }
    }
    this.drag = d;
  }

  onMove(e) {
    this.mouse = { x: e.offsetX, y: e.offsetY };
    const d = this.drag;
    if (!d) { this.hover = this.tool === 'explore' ? this.pickShip(e.offsetX, e.offsetY) : null; return; }
    if (Math.hypot(e.offsetX - d.x0, e.offsetY - d.y0) > 4) d.moved = true;
    if (!d.moved) return;
    if (this.tool === 'explore') {
      if (d.ship) {
        // drag a ship to move it
        const w = this.toWorld(e.offsetX, e.offsetY);
        d.ship.pos.set(w.x + d.off.x, w.z + d.off.z);
        d.ship.prevStern = null;
      } else {
        this.goal.x = d.gx - (e.offsetX - d.x0) / this.goal.ppm;
        this.goal.z = d.gz - (e.offsetY - d.y0) / this.goal.ppm;
        this.clampGoal();
        this.view.x = this.goal.x; this.view.z = this.goal.z;
      }
    }
  }

  onUp(e) {
    const d = this.drag;
    this.drag = null;
    if (!d) return;
    const w = this.toWorld(e.offsetX, e.offsetY);
    const dragged = Math.hypot(e.offsetX - d.x0, e.offsetY - d.y0) > 10;
    const heading = dragged ? Math.atan2(w.x - d.w0.x, -(w.z - d.w0.z)) : null;
    if (this.tool === 'explore') {
      if (d.ship) {
        if (d.moved) {
          // a ship dropped on land goes back to the nearest water
          const p = this.nearestWater(d.ship.pos.x, d.ship.pos.y, Math.min(KIND_DEPTH[d.ship.spec.kind] || 2, 3), 2000);
          if (p) d.ship.pos.set(p.x, p.z);
        }
      } else if (!d.moved) this.select(null);
    } else if (this.tool === 'teleport') {
      this.teleport(d.w0.x, d.w0.z, heading);
      this.setTool('explore');
    } else if (this.tool === 'ship') {
      this.addShip(d.w0.x, d.w0.z, heading ?? this.app.usv.heading + Math.PI / 2);
    } else if (this.tool === 'route' && this.selected) {
      const v = this.selected;
      const p = this.nearestWater(d.w0.x, d.w0.z, Math.min(KIND_DEPTH[v.spec.kind] || 2, 4), 800);
      if (p) { v.route.push({ x: p.x, z: p.z }); v.done = false; if (v.route.length === 1) v.wp = 0; this.renderCard(); }
    }
  }

  // ------------------------------------------------------------ frame
  draw(dt) {
    if (!this.open) return;
    const cv = this.canvas, ctx = this.ctx;
    const dpr = Math.min(devicePixelRatio || 1, 2);
    const Wc = cv.clientWidth, Hc = cv.clientHeight;
    if (cv.width !== Math.round(Wc * dpr) || cv.height !== Math.round(Hc * dpr)) { cv.width = Math.round(Wc * dpr); cv.height = Math.round(Hc * dpr); }
    const W = cv.width, H = cv.height;
    if (W !== this._lastW) {
      this._lastW = W;
      const bottom = Math.max(...[...this.root.querySelectorAll('.map-bar > *, .map-bar .seg')].map((e) => e.getBoundingClientRect().bottom));
      this.root.style.setProperty('--bar-bottom', `${Math.round(bottom)}px`);
    }
    // smooth zoom and fly-to
    const v = this.view, g = this.goal;
    const k = 1 - Math.exp(-dt * 12);
    v.ppm = Math.exp(Math.log(v.ppm) + (Math.log(g.ppm) - Math.log(v.ppm)) * k);
    v.x += (g.x - v.x) * k; v.z += (g.z - v.z) * k;
    // settle exactly on the goal (sub-pixel), so that the cached layer stops being redrawn
    if (Math.abs(Math.log(v.ppm / g.ppm)) < 1e-3 && Math.hypot(g.x - v.x, g.z - v.z) * v.ppm < 0.2) { v.ppm = g.ppm; v.x = g.x; v.z = g.z; }
    const ppm = v.ppm * dpr;
    const a = this.app, u = a.usv;
    const S = (x, z) => [(x - v.x) * ppm + W / 2, (z - v.z) * ppm + H / 2];

    // imagery, lanes and names only change with the view: drawn once into a cached layer
    const key = `${v.x.toFixed(2)},${v.z.toFixed(2)},${v.ppm.toPrecision(6)},${W},${H},${this.labels.length}`;
    // while the view moves the layer is redrawn every frame at a cheaper quality, then once more when it settles
    const moving = key !== this._baseKey;
    if (moving || this._baseFast) {
      this._baseKey = key;
      this._baseFast = moving;
      const base = (this._base ??= document.createElement('canvas'));
      if (base.width !== W || base.height !== H) { base.width = W; base.height = H; }
      const bc = base.getContext('2d');
      drawImagery(bc, W, H, v.x, v.z, ppm, a.terrain, moving);
      // slight veil so that names and symbols read on bright fields
      bc.fillStyle = 'rgba(6,10,14,0.14)';
      bc.fillRect(0, 0, W, H);
      // shipping lanes, faint
      if (a.traffic?.lanes) {
        bc.save();
        bc.strokeStyle = 'rgba(196,226,241,0.22)';
        bc.lineWidth = 1.2 * dpr;
        bc.setLineDash([6 * dpr, 6 * dpr]);
        for (const l of a.traffic.lanes) {
          bc.beginPath();
          l.pts.forEach((p, i) => { const [x, y] = S(p.x, p.z); if (i) bc.lineTo(x, y); else bc.moveTo(x, y); });
          bc.stroke();
        }
        bc.restore();
      }
      drawLabels(bc, W, H, v.x, v.z, ppm, dpr, this.labels, v.ppm);
    }
    ctx.drawImage(this._base, 0, 0);

    // drone trail
    this._trailT += dt;
    if (this._trailT > 1) {
      this._trailT = 0;
      const last = this.trail[this.trail.length - 1];
      if (!last || Math.hypot(last.x - u.pos.x, last.z - u.pos.y) > 3) this.trail.push({ x: u.pos.x, z: u.pos.y });
      if (this.trail.length > 600) this.trail.shift();
    }

    // ships
    for (const s of a.traffic.vessels) this.drawShip(ctx, s, S, ppm, dpr);

    // drone: trail, field of view, arrow
    if (this.trail.length > 1) {
      ctx.strokeStyle = 'rgba(240,106,29,0.55)';
      ctx.lineWidth = 1.5 * dpr;
      ctx.beginPath();
      this.trail.forEach((p, i) => { const [x, y] = S(p.x, p.z); if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y); });
      const [ux, uy] = S(u.pos.x, u.pos.y);
      ctx.lineTo(ux, uy);
      ctx.stroke();
    }
    const [ux, uy] = S(u.pos.x, u.pos.y);
    const yaw = a.cameraYaw(), half = (a.horizontalFov() * DEG) / 2;
    // field of view as a short cone (about 1.5 km, kept readable at every zoom)
    const R = Math.min(Math.max(70 * dpr, 1500 * ppm), 240 * dpr);
    const grad = ctx.createRadialGradient(ux, uy, 0, ux, uy, R);
    grad.addColorStop(0, 'rgba(216,181,99,0.32)');
    grad.addColorStop(1, 'rgba(216,181,99,0)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.moveTo(ux, uy);
    for (let i = 0; i <= 16; i++) { const an = yaw - half + (2 * half * i) / 16; ctx.lineTo(ux + Math.sin(an) * R, uy - Math.cos(an) * R); }
    ctx.closePath();
    ctx.fill();
    ctx.save();
    ctx.translate(ux, uy);
    ctx.rotate(u.heading);
    const s = 9 * dpr;
    ctx.fillStyle = '#f06a1d';
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 1.8 * dpr;
    ctx.beginPath(); ctx.moveTo(0, -s * 1.3); ctx.lineTo(s * 0.8, s); ctx.lineTo(0, s * 0.5); ctx.lineTo(-s * 0.8, s); ctx.closePath();
    ctx.fill(); ctx.stroke();
    ctx.restore();
    ctx.font = `600 ${11 * dpr}px ${FONT}`;
    ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    ctx.lineWidth = 3 * dpr; ctx.strokeStyle = 'rgba(8,10,12,0.7)';
    ctx.strokeText('Drone', ux + 14 * dpr, uy + 1);
    ctx.fillStyle = '#ffb27f';
    ctx.fillText('Drone', ux + 14 * dpr, uy + 1);

    // highlight after a search or a teleport
    if (this.flash) {
      this.flash.t += dt;
      const [fx, fy] = S(this.flash.x, this.flash.z);
      const t = this.flash.t;
      ctx.strokeStyle = `rgba(216,181,99,${Math.max(0, 1 - t / 1.6)})`;
      ctx.lineWidth = 2 * dpr;
      ctx.beginPath(); ctx.arc(fx, fy, (8 + t * 40) * dpr, 0, Math.PI * 2); ctx.stroke();
      if (t > 1.6) this.flash = null;
    }

    // placement preview (teleport / new ship): heading arrow while dragging
    const d = this.drag;
    if (d && (this.tool === 'teleport' || this.tool === 'ship') && this.mouse) {
      const [x0, y0] = S(d.w0.x, d.w0.z);
      const mx = this.mouse.x * dpr, my = this.mouse.y * dpr;
      ctx.strokeStyle = this.tool === 'ship' ? '#d8b563' : '#f06a1d';
      ctx.fillStyle = ctx.strokeStyle;
      ctx.lineWidth = 2 * dpr;
      ctx.beginPath(); ctx.arc(x0, y0, 6 * dpr, 0, Math.PI * 2); ctx.stroke();
      if (Math.hypot(mx - x0, my - y0) > 10 * dpr) {
        const an = Math.atan2(my - y0, mx - x0);
        ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(mx, my); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(mx, my);
        ctx.lineTo(mx - Math.cos(an - 0.45) * 10 * dpr, my - Math.sin(an - 0.45) * 10 * dpr);
        ctx.lineTo(mx - Math.cos(an + 0.45) * 10 * dpr, my - Math.sin(an + 0.45) * 10 * dpr);
        ctx.closePath(); ctx.fill();
      }
    }
    if (this.tool === 'route' && this.selected && this.mouse && this.selected.route.length) {
      const last = this.selected.route[this.selected.route.length - 1];
      const [x0, y0] = S(last.x, last.z);
      ctx.strokeStyle = 'rgba(216,181,99,0.6)'; ctx.lineWidth = 1.5 * dpr; ctx.setLineDash([4 * dpr, 4 * dpr]);
      ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(this.mouse.x * dpr, this.mouse.y * dpr); ctx.stroke();
      ctx.setLineDash([]);
    }

    this.drawFoot();
    this._statT = (this._statT || 0) + dt;
    if (this._statT > 0.25) { this._statT = 0; this.updateCardStats(); }
    if (this.selected && !a.traffic.vessels.includes(this.selected)) this.select(null);
  }

  drawShip(ctx, v, S, ppm, dpr) {
    const [x, y] = S(v.pos.x, v.pos.y);
    const W = this.canvas.width, H = this.canvas.height;
    if (x < -60 || y < -60 || x > W + 60 || y > H + 60) return;
    const user = v.role === 'user', sel = this.selected === v, hov = this.hover === v;
    const target = this.app.usv.target === v;
    // route of the operator's ships
    if (user && v.route.length) {
      ctx.save();
      ctx.strokeStyle = 'rgba(216,181,99,0.75)';
      ctx.lineWidth = 1.5 * dpr;
      ctx.setLineDash([5 * dpr, 4 * dpr]);
      ctx.beginPath();
      ctx.moveTo(x, y);
      for (let i = v.done ? v.route.length - 1 : v.wp; i < v.route.length; i++) { const [px, py] = S(v.route[i].x, v.route[i].z); ctx.lineTo(px, py); }
      if (v.loop) for (let i = 0; i < Math.min(v.wp, v.route.length); i++) { const [px, py] = S(v.route[i].x, v.route[i].z); ctx.lineTo(px, py); }
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = '#d8b563';
      v.route.forEach((p) => { const [px, py] = S(p.x, p.z); ctx.beginPath(); ctx.arc(px, py, 3 * dpr, 0, Math.PI * 2); ctx.fill(); });
      ctx.restore();
    }
    // course over one minute
    if (v.speed > 0.2) {
      const f = v.forward;
      const [ex, ey] = S(v.pos.x + f.x * v.speed * 60, v.pos.y + f.y * v.speed * 60);
      ctx.strokeStyle = user ? 'rgba(216,181,99,0.6)' : 'rgba(240,238,232,0.45)';
      ctx.lineWidth = 1.2 * dpr;
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(ex, ey); ctx.stroke();
    }
    const fill = user || target ? '#d8b563' : 'rgba(244,242,236,0.95)';
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(v.heading);
    const Lp = v.L * ppm, Bp = Math.max(v.B * ppm, 1);
    ctx.fillStyle = fill;
    ctx.strokeStyle = 'rgba(8,10,12,0.75)';
    ctx.lineWidth = 1.3 * dpr;
    ctx.beginPath();
    if (Lp > 14 * dpr) {
      // hull outline at true scale
      const hl = Lp / 2, hb = Bp / 2, bow = Math.min(Lp * 0.3, Bp * 1.6);
      ctx.moveTo(0, -hl); ctx.quadraticCurveTo(hb, -hl + bow * 0.4, hb, -hl + bow); ctx.lineTo(hb, hl * 0.92);
      ctx.quadraticCurveTo(hb, hl, hb * 0.6, hl); ctx.lineTo(-hb * 0.6, hl); ctx.quadraticCurveTo(-hb, hl, -hb, hl * 0.92);
      ctx.lineTo(-hb, -hl + bow); ctx.quadraticCurveTo(-hb, -hl + bow * 0.4, 0, -hl);
    } else {
      const s = (v.L > 60 ? 7 : v.L > 20 ? 6 : 5) * dpr;
      ctx.moveTo(0, -s * 1.25); ctx.lineTo(s * 0.7, s); ctx.lineTo(-s * 0.7, s); ctx.closePath();
    }
    ctx.fill(); ctx.stroke();
    ctx.restore();
    if (sel || hov) {
      ctx.strokeStyle = sel ? '#d8b563' : 'rgba(244,242,236,0.7)';
      ctx.lineWidth = 1.5 * dpr;
      ctx.beginPath(); ctx.arc(x, y, Math.max(13 * dpr, Lp * 0.6), 0, Math.PI * 2); ctx.stroke();
    }
    if (this.view.ppm > 0.1 || user || sel || hov) {
      const name = v.spec.name + (hov || sel ? ` · ${fmt(v.speed * KN, 1)} nd` : '');
      ctx.font = `500 ${10.5 * dpr}px ${FONT}`;
      ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
      const ox = Math.max(11 * dpr, Lp * 0.5 + 6 * dpr);
      ctx.lineWidth = 3 * dpr; ctx.strokeStyle = 'rgba(8,10,12,0.72)';
      ctx.strokeText(name, x + ox, y);
      ctx.fillStyle = user ? '#ecd596' : 'rgba(244,242,236,0.92)';
      ctx.fillText(name, x + ox, y);
    }
  }

  drawFoot() {
    const v = this.view;
    // scale bar: a round length close to 110 px
    const target = 110 / v.ppm;
    const steps = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000];
    const len = steps.find((s) => s >= target * 0.6) || 20000;
    this.scaleEl.querySelector('i').style.width = `${len * v.ppm}px`;
    this.scaleEl.querySelector('span').textContent = len >= 1000 ? `${len / 1000} km` : `${len} m`;
    let txt = '';
    if (this.mouse) {
      const w = this.toWorld(this.mouse.x, this.mouse.y);
      const ll = this.app.toLatLon(w.x, w.z);
      const h = this.app.terrain.ready ? this.app.terrain.heightAt(w.x, w.z) : 0;
      txt = `${dm(ll.lat, 'N', 'S')}  ${dm(ll.lon, 'E', 'O')}  ·  ${h < 0 ? `fond ${fmt(-h, -h < 10 ? 1 : 0)} m` : `terre ${Math.round(h)} m`}`;
    }
    if (txt !== this._cursorTxt) { this.cursorEl.textContent = txt; this._cursorTxt = txt; }
  }
}
